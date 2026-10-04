"""Live DOG smoke and 30 calendar days; certify acquisitions, not an entire market."""
from __future__ import annotations
import argparse,csv,hashlib,html,json,os,sys
from collections import Counter
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.collectors.dog import DOGCollector,ASSET_RE,events_from_notice
from app.db import connect
from app.store import save_event
from app.reporting import write_quality_issues


def run_phase(days,end,root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    db=root/'dog.sqlite'
    if db.exists():raise ValueError('Validation requires a fresh database')
    conn=connect(str(db));collector=DOGCollector(output_dir=str(root),timeout=45)
    events=[]
    for offset in range(days):
        day=end-timedelta(days=days-1-offset);batch=collector.collect_day(day)
        for event in batch:
            save_event(conn,event);events.append(event)
        print('DOG_DAY',day.isoformat(),json.dumps(collector.audit['days'][day.isoformat()],ensure_ascii=False),flush=True)
    collector.persist_metadata(conn)
    for review in collector.audit['review']:
        if ASSET_RE.search(review['title']):raise ValueError('Named renewable project not resolved: '+json.dumps(review,ensure_ascii=False))
    issues,_,_=write_quality_issues(conn,out_dir=str(root))
    if any(i['severity']=='ERROR' for i in issues):raise ValueError('DOG structural quality error')
    for acquisition in collector.audit['acquisitions']:
        if not acquisition.get('sha256'):continue
        raw=(root/'raw'/(acquisition['sha256']+'.bin')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=acquisition['sha256'] or len(raw)!=acquisition['bytes']:raise ValueError('DOG raw acquisition hash mismatch')
    before=list(conn.execute('SELECT * FROM events ORDER BY id'))
    for event in events:
        if save_event(conn,event)!=(False,False):raise ValueError('Duplicate on idempotent replay')
    if before!=list(conn.execute('SELECT * FROM events ORDER BY id')):raise ValueError('Original source events changed on replay')
    if conn.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Foreign key error')
    evidence_count=conn.execute("SELECT count(*) FROM regional_public_metadata WHERE source_code='DOG'").fetchone()[0]
    if evidence_count!=len(events):raise ValueError('Missing DOG event evidence')
    links=json.loads((root/'galicia_links.json').read_text())
    result=dict(head_sha=os.getenv('GITHUB_SHA'),run_id=os.getenv('GITHUB_RUN_ID'),
        window_start=str(end-timedelta(days=days-1)),window_end=str(end),source_days=len(collector.audit['days']),
        publication_editions=sum(d['editions'] for d in collector.audit['days'].values()),
        index_notices=sum(d['index_notices'] for d in collector.audit['days'].values()),
        candidate_publications=len(collector.notices),events=len(events),projects=conn.execute('SELECT count(*) FROM projects').fetchone()[0],
        known_mw=conn.execute('SELECT SUM(power_mw) FROM projects').fetchone()[0],
        missing=dict(conn.execute('SELECT SUM(project_name IS NULL) no_name,SUM(power_mw IS NULL) no_mw,SUM(province IS NULL) no_province,SUM(expediente IS NULL) no_expediente FROM projects').fetchone()),
        by_event=dict(Counter(e.event_type for e in events)),quality=dict(Counter(i['severity'] for i in issues)),source_day_errors=0,
        explicit_reviews=len(collector.audit['review']),idempotent_replay=True,original_provenance_verified=True,
        archive_link_status=links['status'],archive_links=len(links['matches']),
        scope='Official dated DOG Spanish editions and target titles; archive links are evidence, not new or merged projects; durations are not work dates.')
    (root/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    columns=['project_name','technology','power_mw','province','expediente','promoter','event_type','publication_date','url','execution_duration_months','power_scope']
    records=[]
    for notice in collector.notices.values():
        for row in notice['records']:
            record={**row,'publication_date':notice['publication_date'],'url':notice['url']};records.append({k:record.get(k) for k in columns})
    with (root/'projects.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(records)
    cells=lambda r:''.join('<td>'+html.escape(str(r[k]) if r[k] is not None else 'n.d.')+'</td>' for k in columns)
    report='<html><meta charset="utf-8"><title>DOG Galicia</title><style>body{font:14px Arial;margin:24px}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}table{border-collapse:collapse}</style><h1>Galicia — pubblicazioni DOG verificate</h1><p>Durata di esecuzione dichiarata: non è una data di inizio o fine lavori. Per ampliamenti, la capacità finale non è la potenza aggiuntiva.</p><p>'+html.escape(json.dumps(result,ensure_ascii=False))+'</p><table><tr>'+''.join('<th>'+k+'</th>' for k in columns)+'</tr>'+''.join('<tr>'+cells(r)+'</tr>' for r in records)+'</table></html>'
    (root/'index.html').write_text(report,encoding='utf-8')
    print('DOG_VALIDATION',json.dumps(result,ensure_ascii=False),flush=True)
    for row in records:print('DOG_PROJECT',json.dumps(row,ensure_ascii=False),flush=True)
    conn.close();return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--until');args=p.parse_args()
    end=date.fromisoformat(args.until) if args.until else datetime.now(ZoneInfo('Europe/Madrid')).date()-timedelta(days=1)
    smoke=run_phase(3,end,'reports/dog_smoke');full=run_phase(30,end,'reports/dog_validation')
    if full['source_days']!=30:raise ValueError('Incomplete thirty-day window')
    print('DOG_CERTIFIED',json.dumps(dict(smoke=smoke,backfill=full),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
