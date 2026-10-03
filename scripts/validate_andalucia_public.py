"""Isolated official-source validation. Does not activate a default collector."""
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.collectors.andalucia_public import AndaluciaPublicCollector, document_links
from app.db import connect
from app.store import save_event
from app.reporting import write_quality_issues, write_changes


def main():
    collector = AndaluciaPublicCollector()
    end = datetime.now(ZoneInfo('Europe/Madrid')).date() - timedelta(days=1)
    conn = connect('data/andalucia_public_validation.sqlite')
    days=[]; events=[]
    for offset in range(29,-1,-1):
        day = end - timedelta(days=offset)
        found = collector.collect_day(day)
        days.append({'date':day.isoformat(),'candidates':len(found),'status':'OK'})
        for event in found:
            save_event(conn,event)
            events.append(event)
            print('AND_EVENT',json.dumps(event.asdict(),ensure_ascii=False),flush=True)
    before=conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    for event in events:
        save_event(conn,event)
    after=conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    if before != after:
        raise SystemExit('Andalucia replay created duplicate events')
    issues,_,_ = write_quality_issues(conn, 'reports/andalucia_public')
    write_changes(events, 'reports/andalucia_public/changes')
    metrics = {
        'snapshot':collector.audit,
        'window_start':days[0]['date'], 'window_end':end.isoformat(),
        'source_days':len(days), 'events_30d':len(events),
        'events_smoke_3d':sum(e.publication_date >= (end-timedelta(days=2)).isoformat() for e in events),
        'projects':conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0],
        'quality':dict(Counter(i['severity'] for i in issues)),
        'idempotent_replay': before==after,
        'source_day_errors':0,
    }
    print('AND_CERTIFICATION',json.dumps(metrics,ensure_ascii=False),flush=True)
    for issue in issues:
        if issue['severity']!='INFO': print('AND_QUALITY',json.dumps(issue,ensure_ascii=False),flush=True)
    Path('reports/andalucia_public/certification.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    conn.close()
    if not events or not collector.audit['complete'] or metrics['quality'].get('ERROR',0):
        raise SystemExit('Andalucia certification failed: empty backfill, incomplete source or quality error')

if __name__=='__main__':
    main()
