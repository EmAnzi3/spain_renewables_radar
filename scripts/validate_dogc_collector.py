"""DOGC live smoke/backfill and original-byte integration gate.

No event count is inferred from run success. Rebuild indexes, each PDF, semantic
classification and each projected field, then compare immutable database events.
Municipal leads, corrections and excluded acts are independently accounted for.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from app.catalunya_inventory import atomic_json
from app.collectors.dogc import DOGCCollector
from app.db import connect
from app.dogc_projection import events_from_record
from app.dogc_semantics import classify_document
from app.enrichment.ine_municipalities import INE_MUNICIPALITIES_URL, parse_ine_municipalities
from app.reporting import write_changes, write_coverage, write_quality_issues, write_province_view, export_dashboard
from app.dashboard import write_dashboard
from app.store import save_event
from scripts.acquire_dogc_bodies import extract_pages
from scripts.audit_dogc_index import ENERGY, parse_calendar, parse_summary
from scripts.reconcile_dogc_daily import daily_parameters, parse_complete_day, require_same_index
from scripts.recheck_dogc_bodies import safe_file, source_identity
from scripts.classify_dogc_documents import check_review_fixture


def validate_dogc_integration(conn, output='reports/dogc', expected_days=30):
    root=Path(output);audit=json.loads((root/'coverage.json').read_text());g=root/audit['generation']
    if not audit['complete'] or len(audit['days'])!=expected_days or any(s['status']!='OK' or not s['complete_calendar_day'] for s in audit['days'].values()):
        raise ValueError('DOGC coverage is incomplete or contains open calendar days')
    days=sorted(date.fromisoformat(s) for s in audit['days'])
    if days!=[days[0]+timedelta(days=n) for n in range(expected_days)]:raise ValueError('DOGC day coverage has gaps')
    manifest=json.loads((g/'index_raw/acquisitions.json').read_text());originals={}
    for item in manifest:
        label=item['label'];raw=safe_file(g/'index_raw',item['sha256']+'.bin').read_bytes()
        if label in originals or hashlib.sha256(raw).hexdigest()!=item['sha256'] or len(raw)!=item['bytes'] or item['status']!=200:
            raise ValueError('DOGC index original integrity failure')
        originals[label]=(item,raw)
    def source(label,route,parameters):
        meta,raw=originals[label]
        if meta['method']!='POST' or meta['parameters']!=parameters or meta['url']!='https://portaldogc.gencat.cat/eadop-rest/api/dogc/'+route:
            raise ValueError('DOGC index request provenance differs from requested day')
        return json.loads(raw)
    calendars={}
    for year,month in {(d.year,d.month) for d in days}:
        calendars.update(parse_calendar(source(f'calendar:{year}:{month}','calendarDOGC',{'year':year,'month':month,'language':'ca'}),year,month))
    candidates={};dispositions=0
    for day in days:
        edition=calendars[day];entries={}
        if edition:
            entries=parse_summary(source('edition:'+str(day),'summaryDOGC',{'numDOGC':edition,'language':'ca'}),edition,day)
        daily=parse_complete_day(source('daily:'+str(day),'searchDOGC',daily_parameters(day)),day)
        require_same_index(entries,daily);dispositions+=len(entries)
        if len(entries)!=audit['days'][str(day)]['index_dispositions']:raise ValueError('DOGC published disposition count changed')
        for r in entries.values():
            if ENERGY.search(r['title']):
                if r['document_id'] in candidates:raise ValueError('Duplicated DOGC candidate in dated window')
                candidates[r['document_id']]=r
    documents=json.loads((g/'documents.json').read_text());actual={d['candidate']['document_id']:d for d in documents}
    if len(actual)!=len(documents) or set(actual)!=set(candidates):raise ValueError('DOGC candidate inventory incomplete')
    catalog=[];cat=audit.get('source_catalog')
    if cat:
        raw=(g/'ine_municipalities.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=cat['sha256'] or cat['url']!=INE_MUNICIPALITIES_URL:raise ValueError('INE geography source changed')
        catalog=parse_ine_municipalities(json.loads(raw))
        if len(catalog)!=cat['records']:raise ValueError('INE geography catalogue count changed')
    classifications=[];expected_events=[];page_count=0;geo_counts=Counter();capacity_counts=Counter()
    for identity,original in candidates.items():
        doc=actual[identity];candidate=doc['candidate']
        for field in ('document_id','publication_date','title','edition','base_edition','source_url'):
            if candidate[field]!=original[field]:raise ValueError('DOGC candidate changed original index field '+field)
        source_identity(original,doc['acquisition'])
        raw=safe_file(g,doc['pdf_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=candidate['pdf_sha256'] or candidate['pdf_sha256']!=doc['acquisition']['sha256']:
            raise ValueError('DOGC original PDF digest changed')
        parsed=extract_pages(raw,candidate)
        if not parsed['publication_evidence_complete'] or parsed['empty_text_pages']:raise ValueError('DOGC original page evidence incomplete')
        if parsed!=json.loads(safe_file(g,doc['pages_file']).read_text()):raise ValueError('DOGC exact original page replay differs')
        record=classify_document(candidate,parsed['pages']);page_count+=len(parsed['pages'])
        if record!=doc['classification']:raise ValueError('DOGC semantic original replay differs')
        projections=events_from_record(record,parsed['pages'],catalog);classifications.append(record)
        observation=conn.execute('SELECT * FROM dogc_document_observations WHERE external_id=?',(identity,)).fetchone()
        if not observation or observation['pdf_sha256']!=candidate['pdf_sha256'] or json.loads(observation['record_json'])!=record:
            raise ValueError('DOGC document observation missing or altered')
        if not projections:
            if conn.execute("SELECT 1 FROM events WHERE source_code='DOGC' AND external_id=?",(identity,)).fetchone():
                raise ValueError('A local lead/correction/excluded document became an energy permit')
            continue
        for event,evidence in projections:
            expected_events.append(event);geo_counts[evidence['extraction']['geography']['status']]+=1
            capacity_counts[evidence['extraction']['capacity_selection']['status']]+=1
            row=conn.execute("SELECT * FROM events WHERE source_code='DOGC' AND external_id=?",(event.external_id,)).fetchone()
            if not row:raise ValueError('DOGC expected event missing from database')
            for field,value in asdict(event).items():
                if field in ('project_name','project_key'):continue
                if row[field]!=value:raise ValueError(f'DOGC source field changed: {identity}/{field}')
            if row['project_key']!=event.project_key:
                alias=conn.execute('SELECT project_key FROM project_identity_aliases WHERE alias_key=?',(event.project_key,)).fetchone()
                if not alias or alias['project_key']!=row['project_key']:raise ValueError('DOGC event identity lacks exact alias provenance')
            meta=conn.execute("SELECT * FROM regional_public_metadata WHERE source_code='DOGC' AND external_id=?",(event.external_id,)).fetchone()
            if not meta or json.loads(meta['evidence_json'])!=dict(evidence,geographic_catalog=cat):raise ValueError('DOGC event metadata differs from originals')
    total=conn.execute("SELECT count(*) FROM events WHERE source_code='DOGC' AND publication_date BETWEEN ? AND ?",(str(days[0]),str(days[-1]))).fetchone()[0]
    if total!=len(expected_events):raise ValueError('Unexpected DOGC events in audited date window')
    categories=Counter(r['category'] for r in classifications)
    observed=(dispositions,len(classifications),len(expected_events),categories['MUNICIPAL_PROJECT'],categories['CORRECTION'],categories['OUT_OF_SCOPE'])
    expected=tuple(audit['totals'][k] for k in ('index_dispositions','title_candidates','energy_events','municipal_leads','corrections','excluded'))
    if audit['totals'].get('energy_documents',len(expected_events))!=categories['ENERGY_PROJECT']:
        raise ValueError('DOGC energy source-document count differs from classified documents')
    if observed!=expected or categories['REVIEW_REQUIRED']:raise ValueError('DOGC outcome accounting failed')
    fixture=Path('tests/fixtures/dogc_review_20261004.json');review=None
    if days[0]==date(2026,9,5) and days[-1]==date(2026,10,4):
        review=check_review_fixture(classifications,json.loads(fixture.read_text()))
    before=conn.execute('SELECT count(*) FROM projects').fetchone()[0]
    for event in expected_events:
        if save_event(conn,event)!=(False,False):raise ValueError('DOGC replay inserted a duplicate event')
    if conn.execute('SELECT count(*) FROM projects').fetchone()[0]!=before:raise ValueError('DOGC replay changed project count')
    if conn.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('DOGC database foreign-key violation')
    result={'head_sha':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID'),'window_start':str(days[0]),'window_end':str(days[-1]),
        'source_days':len(days),'source_day_errors':0,'index_dispositions':dispositions,'candidate_documents':len(classifications),
        'pdf_pages':page_count,'energy_documents':categories['ENERGY_PROJECT'],'energy_events':len(expected_events),'unique_energy_project_keys':len({e.project_key for e in expected_events}),
        'municipal_leads':categories['MUNICIPAL_PROJECT'],'corrections':categories['CORRECTION'],'out_of_scope':categories['OUT_OF_SCOPE'],
        'event_types':dict(Counter(e.event_type for e in expected_events)),'stages':dict(Counter(e.commercial_stage for e in expected_events)),
        'geography':dict(geo_counts),'power_selection':dict(capacity_counts),'missing_power_events':sum(e.power_mw is None for e in expected_events),
        'source_integrity_verified':True,'exact_pdf_and_semantic_replay':True,'all_projected_event_fields_verified':True,'idempotent_replay':True,
        'local_leads_are_not_energy_permits':True,'frozen_semantic_review':review}
    atomic_json(root/'integration_metrics.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--until',default='2026-10-04');parser.add_argument('--db',default='data/dogc_validation.sqlite')
    args=parser.parse_args();end=date.fromisoformat(args.until);start=end-timedelta(days=29)
    if end>=datetime.now(ZoneInfo('Europe/Madrid')).date():raise ValueError('Only complete days may be certified')
    if Path(args.db).exists():raise ValueError('Dedicated validation requires a fresh database, not deletion of an existing one')
    smoke=DOGCCollector(output='reports/dogc_smoke')
    try:
        for offset in range(2,-1,-1):smoke.collect_day(end-timedelta(days=offset))
        if not smoke.audit['complete']:raise ValueError('DOGC smoke failed')
    finally:smoke.close()
    collector=DOGCCollector();conn=connect(args.db);events=[];coverage=[]
    try:
        for offset in range(30):
            day=start+timedelta(days=offset);found=collector.collect_day(day)
            for event in found:save_event(conn,event)
            events.extend(found);stats=collector.audit['days'][str(day)]
            coverage.append({'source_code':'DOGC','date':str(day),'status':'OK','candidates':len(found),'inserted':len(found),'new_projects':len(found),'error':''})
            print('DOGC_COLLECTOR_DAY',str(day),json.dumps(stats,ensure_ascii=False),flush=True)
        collector.persist_metadata(conn)
        result=validate_dogc_integration(conn)
        write_changes(events);write_coverage(coverage);issues,_,_=write_quality_issues(conn)
        write_province_view(conn);export_dashboard(conn);write_dashboard()
        quality=Counter(q['severity'] for q in issues);result['quality']={key:quality[key] for key in ('ERROR','WARN','INFO')}
        if quality['ERROR']:raise ValueError('DOGC structural quality gate failed')
        result['smoke_live_passed']=True;result['collector_validated']=True
        atomic_json(Path('reports/dogc/integration_metrics.json'),result)
        print('DOGC_COLLECTOR_CERTIFIED',json.dumps(result,ensure_ascii=False),flush=True)
    finally:collector.close();conn.close()


if __name__=='__main__':main()
