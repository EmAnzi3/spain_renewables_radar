"""Independent live GVA gate; no activation before a reconciled 30-day run."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timedelta
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from app.collectors.gva_public import GVAPublicCollector
from app.db import connect
from app.reporting import write_quality_issues,write_changes,export_dashboard,write_province_view
from app.dashboard import write_dashboard
from app.store import save_event


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--until');args=parser.parse_args()
    end=datetime.strptime(args.until,'%Y-%m-%d').date() if args.until else datetime.now(ZoneInfo('Europe/Madrid')).date()-timedelta(days=1)
    start=end-timedelta(days=29);collector=GVAPublicCollector();smoke=[]
    for offset in (2,1,0):smoke.extend(collector.collect_day(end-timedelta(days=offset)))
    positive=[];positive_day=None
    sample_dates=sorted({r['publication_date'] for r in collector.inventory if start.isoformat()<=r['publication_date']<=end.isoformat()},reverse=True)
    for day_text in sample_dates:
        positive=collector.collect_day(datetime.strptime(day_text,'%Y-%m-%d').date())
        if positive:positive_day=day_text;break
    assert positive,'No live target publication to certify extraction'
    print('GVA_SMOKE',json.dumps({'recent_3_days_events':len(smoke),'positive_sample_day':positive_day,'positive_sample_events':len(positive)},ensure_ascii=False),flush=True)
    con=connect('data/gva_validation.sqlite')
    assert con.execute('SELECT count(*) FROM events').fetchone()[0]==0,'Certification requires a clean DB'
    events=[]
    for offset in range(30):
        day=start+timedelta(days=offset);found=collector.collect_day(day)
        for event in found:save_event(con,event);events.append(event)
        print('GVA_DAY',day.isoformat(),len(found),flush=True)
    collector.persist_metadata(con)
    expected=[r for r in collector.inventory if start.isoformat()<=r['publication_date']<=end.isoformat()]
    assert len(collector.records)==len(expected),'Every source publication needs a documented outcome'
    assert {r['external_id'] for r in expected}==set(collector.records)
    assert len(collector.audit['processed_days'])==30 and not collector.audit['detail_errors']
    assert collector.audit['complete'] and collector.audit['archive_records']==collector.audit['declared_records']==collector.audit['distinct_ids']
    assert con.execute('SELECT count(*) FROM regional_public_metadata').fetchone()[0]==len(events)
    assert not con.execute('PRAGMA foreign_key_check').fetchall()
    for event in events:
        raw=json.loads(event.raw_text)
        assert raw['publication_date']==event.publication_date and raw['url']==event.url
        assert raw['title']==event.title and raw['external_id']==event.external_id
        assert save_event(con,event)==(False,False),'Replay generated duplicate event/project'
    for acquisition in collector.audit['acquisitions']:
        raw=(collector.output/acquisition['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==acquisition['sha256']
    issues,_,_=write_quality_issues(con)
    write_changes(events);write_province_view(con);export_dashboard(con);write_dashboard()
    counts=Counter(i['severity'] for i in issues)
    flags=Counter(f['code'] for r in collector.records.values() for f in r.get('quality_flags',[]))
    rows=[dict(row) for row in con.execute('SELECT * FROM projects')]
    result={'run_id':os.getenv('GITHUB_RUN_ID'),'head_sha':os.getenv('GITHUB_SHA'),
            'window_start':start.isoformat(),'window_end':end.isoformat(),
            'archive_records':len(collector.inventory),'archive_pages':collector.audit['pages'],
            'source_publications':len(expected),'events':len(events),'projects':len(rows),
            'by_event':dict(Counter(e.event_type for e in events)),
            'by_stage':dict(Counter(r['commercial_stage'] for r in rows)),
            'excluded_dispositions':dict(Counter(r['extraction']['disposition'] for r in collector.records.values() if r['extraction']['disposition']!='TARGET')),
            'quality':{s:counts[s] for s in ('ERROR','WARN','INFO')},'source_quality_flags':dict(flags),
            'missing':{k:sum(r[k] is None for r in rows) for k in ('project_name','power_mw','province','expediente')},
            'recent_3_days_events':len(smoke),'positive_sample_day':positive_day,
            'positive_sample_events':len(positive),'source_day_errors':len(collector.audit['detail_errors']),
            'idempotent_replay':True,'event_provenance_complete':True,
            'legal_pdf_extraction_scope':'first 2 pages; original full PDF and hashes retained; no OCR',
            'registry_activation':'pending full integration'}
    (collector.output/'validation_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for e in events:print('GVA_EVENT',json.dumps({'id':e.external_id,'name':e.project_name,'mw':e.power_mw,'province':e.province,'reference':e.expediente,'type':e.event_type,'categories':collector.records[e.external_id]['categories']},ensure_ascii=False),flush=True)
    print('GVA_CERTIFICATION',json.dumps(result,ensure_ascii=False),flush=True);con.close()
    assert not flags.get('SOURCE_LIFECYCLE_UNMAPPED'),'Unmapped current administrative decision'
    assert counts['ERROR']==0,'Structural project errors must be fixed, not waived'


if __name__=='__main__':main()
