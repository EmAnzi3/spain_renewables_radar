"""Bounded monthly official-source backfill shard with auditable, resumable outputs.

Each shard has one source and one calendar month. A success means the shard's
source-day coverage and structural quality gates passed, NOT that every historic
plant in a region has been discovered. Source omissions remain explicit.
No paid sources, synthetic projects, database merge or invented dates.
"""
from __future__ import annotations
import argparse
import calendar
import csv
from datetime import date,datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import traceback

from app.run_pipeline import COLLECTOR_CLASSES
from app.db import connect

ROOT=Path(__file__).resolve().parents[1]
RANGE_START=date(2024,10,1)
RANGE_END=date(2026,9,30)
INVENTORY_SOURCES={'MITECO_SABIA','AND_PUBLIC','GVA_PUBLIC'}
# Historical month/edition certification is valid only for date-partitionable
# bulletins. Archive inventories must be scanned once per source with their
# own timeline and receipts, never redated as 24 monthly discoveries.
SUPPORTED=tuple(code for code in COLLECTOR_CLASSES if code not in INVENTORY_SOURCES)
FIELDS=('source_code','external_id','publication_date','title','url','raw_text',
        'project_key','event_type','commercial_stage')
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def month_bounds(month):
    if not isinstance(month,str) or len(month)!=7 or month[4]!='-':
        raise ValueError('Month must be YYYY-MM')
    year,number=int(month[:4]),int(month[5:])
    first=date(year,number,1)
    last=date(year,number,calendar.monthrange(year,number)[1])
    if first<RANGE_START or last>RANGE_END:
        raise ValueError('Month outside the approved 2024-10 .. 2026-09 historical window')
    return first,last
def validate_source(code):
    if code in INVENTORY_SOURCES:
        raise ValueError('Archive inventory cannot be certified as an independent monthly bulletin: '+code)
    if code not in SUPPORTED:
        raise ValueError('Unimplemented source: '+str(code))
    return code
def source_summary(db,source):
    c=sqlite3.connect(db);c.row_factory=sqlite3.Row
    try:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('SQLite integrity check failed')
        events=[dict(r) for r in c.execute('SELECT '+','.join(FIELDS)+' FROM events ORDER BY source_code,external_id')]
        if any(x['source_code']!=source for x in events):
            raise ValueError('Source shard unexpectedly contains other sources')
        if len({(x['source_code'],x['external_id']) for x in events})!=len(events):
            raise ValueError('Duplicate source identities in shard')
        if any(not x['external_id'] or not x['url'] or not x['title'] or not x['raw_text'] or not x['publication_date'] for x in events):
            raise ValueError('Missing immutable source evidence')
        projs=c.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
        if c.execute('SELECT COUNT(*) FROM events e LEFT JOIN projects p USING(project_key) WHERE p.project_key IS NULL').fetchone()[0]:
            raise ValueError('Orphan source event')
        return {'events':len(events),'source_scoped_projects':projs,
            'original_evidence_digest':hashlib.sha256(
                json.dumps([tuple(x.get(k) for k in FIELDS) for x in events],ensure_ascii=False).encode()).hexdigest()}
    finally:c.close()
def coverage_summary(path,source,first,last):
    if not path.exists():raise ValueError('Missing source/day coverage CSV')
    with path.open(encoding='utf-8-sig',newline='') as f:allrows=list(csv.DictReader(f))
    rows=[r for r in allrows if r.get('source_code')==source]
    expected={(first.fromordinal(first.toordinal()+x)).isoformat()
              for x in range((last-first).days+1)}
    observed=[r.get('date') for r in rows]
    if len(observed)!=len(expected) or set(observed)!=expected:
        raise ValueError('Missing or duplicate source-day coverage')
    if any(r.get('status') not in ('OK','ERROR') for r in rows):
        raise ValueError('Unrecognized source-day state')
    failures=[{'date':r['date'],'error':r.get('error','')} for r in rows if r['status']=='ERROR']
    return {'source_days_expected':len(expected),'source_days_ok':len(expected)-len(failures),
            'source_days_failed':len(failures),'source_failures':failures,
            'discovered_candidates':sum(int(r['candidates']) for r in rows),
            'newly_inserted_source_events':sum(int(r['inserted']) for r in rows)}
def validate_annual_index_scope(audit,first,last):
    earliest=audit.get('min_publication_date')
    latest=audit.get('max_publication_date')
    if not earliest or not latest or earliest>str(first) or latest<str(last):
        raise ValueError('BORM_CURRENT_ANNUAL_INDEX_DOES_NOT_COVER_REQUESTED_HISTORICAL_MONTH')
    return {'earliest':earliest,'latest':latest}

def main(argv=None):
    a=argparse.ArgumentParser()
    a.add_argument('--source',required=True)
    a.add_argument('--month',required=True)
    a.add_argument('--output',default='reports/historical_shards')
    a.add_argument('--timeout-seconds',type=int,default=2400)
    args=a.parse_args(argv)
    source=validate_source(args.source);first,last=month_bounds(args.month)
    if not 120<=args.timeout_seconds<=3600:raise ValueError('Invalid bounded timeout')
    root=Path(args.output).resolve()/source/args.month
    root.mkdir(parents=True,exist_ok=True)
    db=root/'historical.sqlite';metrics=root/'manifest.json'
    if db.exists():
        raise ValueError('Shard SQLite already exists; never silently overwrite historical evidence')
    result={'schema':1,'source':source,'month':args.month,'window_start':str(first),
        'window_end':str(last),'mode':'ONE_SOURCE_ONE_MONTH_OFFICIAL_ONLY',
        'completeness_claim':'IMPLEMENTED_SOURCE_ONLY_NOT_ALL_SPANISH_REGIONS',
        'non_implemented_regions_are_not_zero_opportunities':True,
        'inventory_source_warning':source in INVENTORY_SOURCES,
        'run_id':os.getenv('GITHUB_RUN_ID'),'head_sha':os.getenv('GITHUB_SHA'),
        'started_at':datetime.now(timezone.utc).isoformat(),'certified':False}
    try:
        command=[sys.executable,'-m','app.run_pipeline','--since',str(first),
                 '--until',str(last),'--sources',source,'--db',str(db),
                 '--skip-ree','--skip-miteco']
        result['command_scope']={'source':source,'since':str(first),'until':str(last),
                                 'skip_live_network_enrichments':True}
        # The runner's collector workdir is isolated, so reports/raw receipts
        # cannot collide with another source-month shard.
        work=root/'workspace';work.mkdir(exist_ok=True)
        env=os.environ.copy();env['PYTHONPATH']=str(ROOT)+os.pathsep+env.get('PYTHONPATH','')
        env['BORM_RUN_SNAPSHOT_DIR']=str((root/'run_snapshots').resolve())
        env['BORM_RUN_SNAPSHOT_SCOPE']=f"historical:{source}:{args.month}:{os.getenv('GITHUB_RUN_ID','local')}"
        with (root/'collector.log').open('w',encoding='utf-8') as output:
            p=subprocess.run(command,cwd=work,env=env,stdout=output,
                             stderr=subprocess.STDOUT,timeout=args.timeout_seconds)
        result['pipeline_return_code']=p.returncode
        # The subprocess sees its db at the absolute path passed below.
        actual=db
        if not actual.exists():raise ValueError('Collector produced no SQLite shard')
        result.update(source_summary(actual,source))
        result.update(coverage_summary(work/'reports/coverage_latest.csv',source,first,last))
        quality=work/'reports/quality_issues_latest.csv'
        if not quality.exists():raise ValueError('Missing quality report')
        with quality.open(encoding='utf-8-sig',newline='') as f:
            issues=list(csv.DictReader(f))
        result['quality']={s:sum(x.get('severity')==s for x in issues) for s in ('ERROR','WARN','INFO')}
        result['structural_errors']=[{'code':x.get('code'),'project_key':x.get('project_key')}
                                   for x in issues if x.get('severity')=='ERROR']
        result['database_sha256']=sha(actual)
        # The current BORM annual JSON is not a historical archive.
        # A 2024/2025 month outside its observed min/max cannot become a
        # certified zero-project result just because collect_day returns [].
        if source=='BORM':
            audit_file=work/'reports/borm/index_acquisition.json'
            if not audit_file.exists():
                raise ValueError('BORM annual-index source-date evidence is missing')
            borm_audit=json.loads(audit_file.read_text(encoding='utf-8'))
            result['source_index_window']=validate_annual_index_scope(borm_audit,first,last)
        if source=='BOE':
            review=work/'reports/boe/review_leads.json'
            if not review.exists():
                raise ValueError('Missing BOE grouped/unnamed official-review ledger')
            payload=json.loads(review.read_text(encoding='utf-8'))
            leads=payload.get('leads')
            if (payload.get('mode')!='UNRESOLVED_LEADS_NOT_PROJECTS'
                or not isinstance(leads,list) or payload.get('lead_count')!=len(leads)
                or len({(x.get('source_code'),x.get('external_id')) for x in leads})!=len(leads)):
                raise ValueError('Invalid/duplicate official BOE review ledger')
            if any(x.get('added_to_projects') is not False or not x.get('raw_text')
                   or not x.get('title') or not x.get('url') for x in leads):
                raise ValueError('BOE review lead is missing original evidence or has an invalid status')
            result['multi_or_unnamed_official_review_leads']=len(leads)
            result['review_leads_original_sha256']=sha(review)
        result['original_report_sha256']={str(path.relative_to(work)):sha(path)
                    for path in (work/'reports').rglob('*') if path.is_file()}
        result['certified']=(p.returncode==0 and result['source_days_failed']==0
                             and not result['structural_errors'])
        if result['certified']:
            print('HISTORICAL_SHARD_CERTIFIED',json.dumps({
                k:v for k,v in result.items() if k not in ('original_report_sha256','source_failures')},ensure_ascii=False))
        else:
            print('HISTORICAL_SHARD_INCOMPLETE',json.dumps({
                k:v for k,v in result.items() if k not in ('original_report_sha256','source_failures')},ensure_ascii=False))
            raise RuntimeError('Shard quality or source-day coverage incomplete')
    except Exception as exc:
        result['error_type']=type(exc).__name__;result['error']=str(exc)
        print('HISTORICAL_SHARD_FAILED',json.dumps({
            k:v for k,v in result.items() if k not in ('original_report_sha256','source_failures')},ensure_ascii=False),flush=True)
        raise
    finally:
        result['completed_at']=datetime.now(timezone.utc).isoformat()
        metrics.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
