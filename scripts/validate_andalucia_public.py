"""Certify acquisition and dated-event extraction, disclosing gaps in source metadata."""
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.collectors.andalucia_public import AndaluciaPublicCollector
from app.db import connect
from app.store import save_event
from app.reporting import write_quality_issues,write_changes


def main():
    collector=AndaluciaPublicCollector()
    end=datetime.now(ZoneInfo('Europe/Madrid')).date()-timedelta(days=1)
    conn=connect('data/andalucia_public_validation.sqlite')
    days=[];events=[]
    for offset in range(29,-1,-1):
        day=end-timedelta(days=offset)
        found=collector.collect_day(day)
        days.append({'date':day.isoformat(),'candidates':len(found),'status':'OK'})
        for event in found:
            save_event(conn,event);events.append(event)
            printable=event.asdict();printable.pop('raw_text',None)
            print('AND_EVENT',json.dumps(printable,ensure_ascii=False),flush=True)
    before=conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    for event in events:save_event(conn,event)
    after=conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    issues,_,_=write_quality_issues(conn,'reports/andalucia_public')
    write_changes(events,'reports/andalucia_public/changes')
    partitions=collector.audit['partitions']
    gaps=json.loads(Path('reports/andalucia_public/source_gaps.json').read_text(encoding='utf-8'))
    accounted=sum(partitions.values())==collector.audit['archive_records']
    gaps_preserved=len(gaps)==partitions['undated']+partitions['missing_title']
    metrics={
        'validation_scope':'Complete archive acquisition; dated publication events; source gaps separately preserved',
        'snapshot':collector.audit,'window_start':days[0]['date'],'window_end':end.isoformat(),
        'source_days':len(days),'events_30d':len(events),
        'events_smoke_3d':sum(e.publication_date>=(end-timedelta(days=2)).isoformat() for e in events),
        'projects':conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0],
        'quality':dict(Counter(i['severity'] for i in issues)),
        'all_source_records_accounted':accounted,'source_gaps_preserved':gaps_preserved,
        'source_metadata_gaps':len(gaps),'unreported_source_gaps':0 if gaps_preserved else 1,
        'idempotent_replay':before==after,'source_day_errors':0,
    }
    print('AND_CERTIFICATION',json.dumps(metrics,ensure_ascii=False),flush=True)
    for issue in issues:
        if issue['severity']!='INFO':print('AND_QUALITY',json.dumps(issue,ensure_ascii=False),flush=True)
    Path('reports/andalucia_public/certification.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    conn.close()
    if not events or not collector.audit['complete'] or metrics['quality'].get('ERROR',0) or before!=after or not accounted or not gaps_preserved:
        raise SystemExit('Andalucia validation failed: empty output, coverage, identity, or quality error')

if __name__=='__main__':
    main()
