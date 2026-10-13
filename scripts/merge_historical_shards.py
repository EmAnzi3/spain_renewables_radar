"""Deterministic merge of individually certified official-source historical shards.

Never turn failed/unattempted region/month coverage into zero projects.
Identical source-event IDs must agree on immutable evidence. Conflicting
multi-project identities are held for review, not forcibly merged. Source
provenance is preserved byte-for-byte in events.
"""
from __future__ import annotations
import argparse
from collections import defaultdict,Counter
import csv
import hashlib
import html
import json
import sqlite3
from pathlib import Path
from app.db import connect
from app.parser import ParsedEvent,normalize_text
from app.store import save_event
from scripts.historical_month import month_bounds,source_summary,coverage_summary,RANGE_START,RANGE_END

IMMUTABLE=('source_code','external_id','publication_date','title','url','raw_text')
EVENT_FIELDS=('source_code','external_id','publication_date','title','url','raw_text',
              'technology','power_mw','project_name','promoter','expediente',
              'province','ccaa','event_type','commercial_stage','project_key')

def original_signature(row):
    return hashlib.sha256(json.dumps([row[k] for k in IMMUTABLE],ensure_ascii=False).encode()).hexdigest()

def load_shard(folder):
    folder=Path(folder)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('certified') or manifest.get('source_days_failed') or manifest.get('quality',{}).get('ERROR'):
        raise ValueError('Uncertified or incomplete historical month: '+str(folder))
    source=manifest['source'];first,last=month_bounds(manifest['month'])
    if (manifest['window_start'],manifest['window_end'])!=(str(first),str(last)):
        raise ValueError('Historical date range differs from manifest')
    path=folder/'historical.sqlite'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['database_sha256']:
        raise ValueError('Historical database digest mismatch')
    observed=source_summary(path,source)
    if any(observed[k]!=manifest[k] for k in ('events','source_scoped_projects','original_evidence_digest')):
        raise ValueError('Historical event inventory differs from certified manifest')
    coverage=coverage_summary(folder/'workspace/reports/coverage_latest.csv',source,first,last)
    if coverage['source_days_failed'] or any(coverage[k]!=manifest[k] for k in (
        'source_days_expected','source_days_ok','source_days_failed','discovered_candidates',
        'newly_inserted_source_events')):
        raise ValueError('Source-day coverage differs from certified manifest')
    with sqlite3.connect(f'file:{path.resolve()}?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        rows=[dict(r) for r in db.execute('SELECT e.*,p.project_name FROM events e JOIN projects p USING(project_key) ORDER BY e.publication_date,e.source_code,e.external_id')]
    for row in rows:
        if not first <= __import__('datetime').date.fromisoformat(row['publication_date']) <=last:
            raise ValueError('An event is outside its certified source month')
    return manifest,rows

def convert(row):
    return ParsedEvent(*(row[k] for k in EVENT_FIELDS))

def merge(shards,out_db,report_dir,*,prior_db=None):
    shards=[Path(s) for s in shards]
    if not shards:raise ValueError('No historic evidence supplied')
    report_dir=Path(report_dir);report_dir.mkdir(parents=True,exist_ok=True)
    out_db=Path(out_db)
    if out_db.exists():raise ValueError('Historical output already exists; never overwrite it')
    loaded=[load_shard(folder) for folder in shards]
    scope=[(m['source'],m['month']) for m,_ in loaded]
    if len(set(scope))!=len(scope):raise ValueError('Duplicate historical source/month')
    event_rows=[]
    for m,rows in loaded:event_rows.extend(rows)
    event_rows.sort(key=lambda r:(r['publication_date'],r['source_code'],r['external_id']))
    out=connect(str(out_db))
    conflicts=[]
    try:
        if prior_db:
            prior=Path(prior_db)
            if not prior.exists():raise ValueError('Baseline DB missing')
            with sqlite3.connect(f'file:{prior.resolve()}?mode=ro',uri=True) as existing:
                existing.backup(out)
        before_count=out.execute('SELECT count(*) FROM events').fetchone()[0]
        before_projects=out.execute('SELECT count(*) FROM projects').fetchone()[0]
        added=0
        for row in event_rows:
            existing=out.execute('SELECT * FROM events WHERE source_code=? AND external_id=?',
                    (row['source_code'],row['external_id'])).fetchone()
            if existing:
                if original_signature(dict(existing)) != original_signature(row):
                    conflicts.append({'kind':'SOURCE_EVENT_CONFLICT','source':row['source_code'],
                                      'external_id':row['external_id']})
                continue
            duplicate=out.execute('SELECT project_name,technology FROM projects WHERE project_key=?',
                                  (row['project_key'],)).fetchone()
            if duplicate and row['project_name'] and duplicate['project_name'] and (
                    normalize_text(row['project_name'])!=normalize_text(duplicate['project_name'])
                    or (row['technology'] and duplicate['technology'] and row['technology']!=duplicate['technology'])):
                conflicts.append({'kind':'PROJECT_ID_COLLISION','source':row['source_code'],
                                  'external_id':row['external_id'],'project_key':row['project_key']})
                continue
            inserted,_=save_event(out,convert(row))
            added+=int(inserted)
        if conflicts:
            (report_dir/'identity_conflicts.json').write_text(json.dumps(conflicts,ensure_ascii=False,indent=2))
            raise ValueError(str(len(conflicts))+' source/project identity conflicts; output not publishable')
        all_events=out.execute('SELECT count(*) FROM events').fetchone()[0]
        if all_events!=before_count+added:raise ValueError('Merged event count mismatch')
        if out.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or out.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Merged database integrity failed')
        summary={'state':'EVIDENCE_MERGE_NOT_NATIONAL_CERTIFICATION',
                 'source_month_shards_supplied':len(loaded),
                 'source_months':sorted([{'source':s,'month':m} for s,m in scope],key=lambda x:(x['month'],x['source'])),
                 'source_count':len(set(x[0] for x in scope)),
                 'observed_project_count':out.execute('SELECT count(*) FROM projects').fetchone()[0],
                 'observed_event_count':all_events,'new_events_from_supplied_shards':added,
                 'new_project_rows':out.execute('SELECT count(*) FROM projects').fetchone()[0]-before_projects,
                 'complete_17_regions_claim':False,'nationwide_historical_24_months_complete':False,
                 'source_event_conflicts':0,'original_event_records_preserved':True,
                 'database_sha256':None}
        out.commit()
    except:
        out.close()
        out_db.unlink(missing_ok=True)
        raise
    out.close()
    summary['database_sha256']=hashlib.sha256(out_db.read_bytes()).hexdigest()
    (report_dir/'merge_manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows=''.join('<tr><td>'+html.escape(x['month'])+'</td><td>'+html.escape(x['source'])+'</td></tr>' for x in summary['source_months'])
    (report_dir/'index.html').write_text('<!doctype html><html lang="it"><meta charset="utf-8"><title>Radar Spagna · Backfill storico</title><style>body{font:16px system-ui;max-width:1000px;margin:auto;padding:24px}th,td{padding:10px;border-bottom:1px solid #ccc;text-align:left}</style><h1>Backfill storico · copertura effettiva</h1><p>Solo fonti e mesi presenti negli originali certificati. Regioni non coperte non equivalgono a zero progetti.</p><p>Eventi totali: '+str(all_events)+'; progetti nel DB: '+str(summary['observed_project_count'])+'</p><table><tr><th>Mese</th><th>Fonte</th></tr>'+rows+'</table></html>',encoding='utf-8')
    print('HISTORICAL_MERGE_VERIFIED',json.dumps(summary,ensure_ascii=False),flush=True)
    return summary
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--shard',action='append',required=True)
    p.add_argument('--baseline')
    p.add_argument('--db',default='data/historical_merged.sqlite')
    p.add_argument('--output',default='reports/historical_merged')
    a=p.parse_args()
    merge(a.shard,a.db,a.output,prior_db=a.baseline)
if __name__=='__main__':main()
