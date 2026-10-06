"""Operational updates can be partial; certification remains a separate gate.

Collect into a staged SQLite copy. Publish only after structural checks; retain
all prior source events and explicitly carry the last complete source window.
No collector is omitted and a stale source is never relabelled as refreshed.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,shutil,sqlite3,subprocess,sys,uuid
from contextlib import closing
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO=Path(__file__).resolve().parents[1]
IMMUTABLE=('source_code','external_id','publication_date','title','url','raw_text')

def atomic_json(path:Path,data:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)

def utcnow()->str:return datetime.now(timezone.utc).isoformat()

def event_fingerprints(conn)->dict:
    result={}
    for row in conn.execute('SELECT '+','.join(IMMUTABLE)+' FROM events'):
        values=tuple(row)
        result[values[:2]]=hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()
    return result

def validate_database(conn,before:dict)->None:
    if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('SQLite structural integrity failed')
    after=event_fingerprints(conn)
    if any(after.get(key)!=digest for key,digest in before.items()):
        raise ValueError('An existing immutable source event disappeared or changed')
    missing=conn.execute('''SELECT COUNT(*) FROM events e LEFT JOIN projects p USING(project_key)
        WHERE p.project_key IS NULL OR e.source_code IS NULL OR e.external_id IS NULL
        OR e.url IS NULL OR e.url='' OR e.publication_date IS NULL OR e.title IS NULL
        OR e.raw_text IS NULL OR e.raw_text='' ''').fetchone()[0]
    if missing:raise ValueError('Missing event provenance or project identity')
    if conn.execute('SELECT source_code,external_id FROM events GROUP BY 1,2 HAVING COUNT(*)>1').fetchone():
        raise ValueError('Duplicate source event identity')

def assess_coverage(rows:list[dict],requested:list[str],configured:list[str],start:date,end:date,previous:dict|None=None)->dict:
    """Every requested day must be accounted for, including failed days."""
    if not requested or len(requested)!=len(set(requested)) or set(requested)-set(configured):
        raise ValueError('Invalid operational source scope')
    days={(start+timedelta(days=n)).isoformat() for n in range((end-start).days+1)}
    if not days or len(days)>366:raise ValueError('Invalid bounded date window')
    previous=previous or {};by_source={}
    for code in configured:
        old=previous.get(code,{})
        entry={'source_code':code,'status':'NOT_REQUESTED','successful_days':0,'failed_days':[],
               'last_complete_window_start':old.get('last_complete_window_start'),
               'last_complete_window_end':old.get('last_complete_window_end'),
               'last_complete_run_id':old.get('last_complete_run_id'),
               'last_complete_observed_at':old.get('last_complete_observed_at')}
        if code in requested:
            own=[r for r in rows if r.get('source_code')==code]
            if len(own)!=len(days) or {r.get('date') for r in own}!=days:
                raise ValueError('Missing or duplicated source-day coverage: '+code)
            if any(r.get('status') not in ('OK','ERROR') for r in own):raise ValueError('Unrecognized coverage state: '+code)
            failed=[{'date':r['date'],'error':r.get('error','')} for r in own if r['status']=='ERROR']
            entry.update(status='COMPLETE' if not failed else ('PARTIAL' if len(failed)<len(days) else 'UNAVAILABLE'),
                         successful_days=len(days)-len(failed),failed_days=failed,
                         requested_window_start=str(start),requested_window_end=str(end))
            if not failed:
                entry.update(last_complete_window_start=str(start),last_complete_window_end=str(end),
                             last_complete_run_id=os.getenv('GITHUB_RUN_ID'),last_complete_observed_at=utcnow())
        by_source[code]=entry
    enrichment_failures=[r for r in rows if r.get('source_code') not in configured and r.get('status')=='ERROR']
    complete=sum(r['status']=='COMPLETE' for r in by_source.values())
    any_success=any(r['successful_days'] for r in by_source.values())
    state='COMPLETE' if complete==len(configured) and not enrichment_failures else ('PARTIAL' if any_success else 'FAILED')
    return {'state':state,'sources':by_source,'complete_sources':complete,'configured_sources':len(configured),
            'enrichment_failures':enrichment_failures,'full_certification':False,
            'note':'Operational coverage only. Full certification is a separate strict workflow.'}

def read_state(conn)->dict:
    table=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='operational_source_state'").fetchone()
    return {r[0]:json.loads(r[1]) for r in conn.execute('SELECT source_code,payload FROM operational_source_state')} if table else {}

def save_state(conn,status:dict)->None:
    conn.execute('CREATE TABLE IF NOT EXISTS operational_source_state(source_code TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS operational_runs(run_key TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    for code,value in status['sources'].items():
        conn.execute('INSERT OR REPLACE INTO operational_source_state VALUES (?,?)',(code,json.dumps(value,ensure_ascii=False)))
    conn.execute('INSERT OR REPLACE INTO operational_runs VALUES (?,?)',(status['run_key'],json.dumps(status,ensure_ascii=False)))
    conn.commit()

def run_update(database:Path,output:Path,*,days:int,until:date,sources:list[str]|None=None,
               pipeline_runner=subprocess.run,cache_root:Path|None=None)->dict:
    from app.run_pipeline import COLLECTOR_CLASSES
    from app.db import connect
    configured=list(COLLECTOR_CLASSES);sources=sources or configured
    if not 1<=days<=366 or until>=datetime.now(ZoneInfo('Europe/Madrid')).date():
        raise ValueError('Use 1–366 complete Spanish calendar days, ending before today')
    database=database.resolve();output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    database.parent.mkdir(parents=True,exist_ok=True)
    lock=database.with_suffix(database.suffix+'.operational.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    run_key=utcnow().replace(':','')+'-'+uuid.uuid4().hex[:8]
    work=output/'runs'/run_key;work.mkdir(parents=True);staged=work/'staged.sqlite'
    status={'run_key':run_key,'started_at':utcnow(),'run_id':os.getenv('GITHUB_RUN_ID'),
            'head_sha':os.getenv('GITHUB_SHA'),'window_start':str(until-timedelta(days=days-1)),
            'window_end':str(until),'state':'RUNNING','full_certification':False,'database_promoted':False}
    before={};previous={};baseline_dump=None
    try:
        if database.exists():
            with closing(sqlite3.connect(f'file:{database}?mode=ro',uri=True)) as old,closing(sqlite3.connect(staged)) as new:
                old.backup(new);before=event_fingerprints(old);previous=read_state(old)
                baseline_dump=hashlib.sha256('\n'.join(old.iterdump()).encode()).hexdigest()
                with closing(sqlite3.connect(work/'before.sqlite')) as preserved:old.backup(preserved)
        else:
            c=connect(str(staged));c.close()
        shutil.copytree(REPO/'config',work/'config')
        if cache_root and cache_root.is_dir():shutil.copytree(cache_root,work/'data'/'sabia_cache')
        env=os.environ.copy();env['PYTHONPATH']=str(REPO)+os.pathsep+env.get('PYTHONPATH','')
        env['PYTHONUNBUFFERED']='1';env['BORM_RUN_SNAPSHOT_SCOPE']=run_key
        env['BORM_RUN_SNAPSHOT_DIR']=str(work/'data'/'run_snapshots')
        # No global GVA preflight: the ordinary pipeline tries every source.
        cmd=[sys.executable,'-m','app.run_pipeline','--days',str(days),'--until',str(until),
             '--db',str(staged),'--sources',','.join(sources)]
        with (work/'pipeline.log').open('w',encoding='utf-8') as log:
            result=pipeline_runner(cmd,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
        if result.returncode:raise RuntimeError('Pipeline structural/runtime failure; see pipeline.log')
        with (work/'reports/coverage_latest.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        status.update(assess_coverage(rows,sources,configured,until-timedelta(days=days-1),until,previous))
        status['message']=(f"Finestra tentata: {status['window_start']} – {status['window_end']}. "
            f"{status['complete_sources']}/{status['configured_sources']} fonti acquisite completamente. "
            'Gli atti precedenti delle fonti con errori restano datati e consultabili. Non è una certificazione integrata.')
        if status['state']=='FAILED':raise RuntimeError('No requested source-day completed')
        with (work/'reports/quality_issues_latest.csv').open(encoding='utf-8-sig',newline='') as stream:issues=list(csv.DictReader(stream))
        if any(i.get('severity')=='ERROR' for i in issues):raise ValueError('Structural quality error; no publication')
        c=connect(str(staged))
        try:
            validate_database(c,before)
            status.update(quality={s:sum(i['severity']==s for i in issues) for s in ('ERROR','WARN','INFO')},
                          projects=c.execute('SELECT count(*) FROM projects').fetchone()[0],
                          events=c.execute('SELECT count(*) FROM events').fetchone()[0],
                          completed_at=utcnow(),database_promoted=True)
            save_state(c,status)
            temporary=database.with_name(database.name+'.'+uuid.uuid4().hex+'.tmp')
            with closing(sqlite3.connect(temporary)) as dest:c.backup(dest)
            # The baseline backup includes its committed WAL; do not publish over another writer.
            if database.exists():
                with closing(sqlite3.connect(database)) as current:
                    if hashlib.sha256('\n'.join(current.iterdump()).encode()).hexdigest()!=baseline_dump:
                        temporary.unlink(missing_ok=True)
                        raise ValueError('Concurrent database update detected; staged result not promoted')
                    current.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            os.replace(temporary,database)
        finally:c.close()
    except Exception as exc:
        status.update(state='FAILED',error_type=type(exc).__name__,error=str(exc),database_promoted=False,completed_at=utcnow())
        status.setdefault('sources',{k:dict(v,status='NOT_REQUESTED',successful_days=0) for k,v in previous.items()})
        raise
    finally:
        try:
            atomic_json(work/'status.json',status);atomic_json(output/'latest.json',status)
        finally:lock.unlink(missing_ok=True)
    return status

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default='data/spain_renewables.sqlite');p.add_argument('--output',default='reports/operational')
    p.add_argument('--days',type=int,default=7);p.add_argument('--until');p.add_argument('--sources')
    p.add_argument('--cache-root',default='data/sabia_cache');args=p.parse_args()
    today=datetime.now(ZoneInfo('Europe/Madrid')).date()
    status=run_update(Path(args.db),Path(args.output),days=args.days,
        until=date.fromisoformat(args.until) if args.until else today-timedelta(days=1),
        sources=args.sources.split(',') if args.sources else None,cache_root=Path(args.cache_root))
    print('OPERATIONAL_RESULT',json.dumps(status,ensure_ascii=False))

if __name__=='__main__':main()
