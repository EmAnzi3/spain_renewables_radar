"""Replay immutable official artifacts to certify a safe legacy migration and source join."""
import copy
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.collectors.andalucia_public import event_from_record,publication_date
from app.db import connect
from app.identity_migration import repair_legacy_identities,_source_fingerprint
from app.reporting import write_quality_issues
from app.store import save_event


def main():
    out=Path('reports/identity_replay');out.mkdir(parents=True,exist_ok=True)
    Path('data').mkdir(exist_ok=True)
    baseline=Path('replay-input/baseline/data/spain_renewables.sqlite')
    shutil.copy2(baseline,'data/identity_replay.sqlite')
    conn=connect('data/identity_replay.sqlite')
    originals={r['id']:dict(r) for r in conn.execute('SELECT * FROM events')}
    repair=repair_legacy_identities(conn,report_dir=out)
    assert repair['projects_before']==106 and repair['events_before']==128,repair
    assert repair['projects_after']==124 and repair['events_after']==125,repair
    assert len(repair['split_groups'])==8 and repair['quarantined_source_events']==3,repair
    assert Path(repair['backup_path']).exists()
    kept={r['id']:dict(r) for r in conn.execute('SELECT * FROM events')}
    for ident,row in kept.items():assert _source_fingerprint(row)==_source_fingerprint(originals[ident])
    for row in conn.execute('SELECT payload_json FROM quarantined_source_events'):
        payload=json.loads(row[0]);assert payload==originals[payload['id']]
    assert repair_legacy_identities(conn)['status']=='NOT_NEEDED'
    records=json.loads(Path('replay-input/andalucia/reports/andalucia_public/source_records.json').read_text(encoding='utf-8'))
    events=[];new_projects=0
    for record in records:
        when=publication_date(record.get('publication_date'))
        if when and '2026-09-04'<=when<='2026-10-03':
            event=event_from_record(record)
            if event:events.append(event)
    for event in sorted(events,key=lambda e:(e.publication_date,e.external_id)):
        inserted,new=save_event(conn,event);new_projects+=int(new)
        assert inserted
    before=conn.execute('SELECT count(*) FROM events').fetchone()[0]
    for event in events:assert save_event(conn,event)==(False,False)
    after=conn.execute('SELECT count(*) FROM events').fetchone()[0]
    issues,_,_=write_quality_issues(conn,out)
    metrics={
        'baseline_run':37158247411,'andalucia_snapshot_run':37159334281,
        'split_groups':len(repair['split_groups']),'quarantined_false_positives':repair['quarantined_source_events'],
        'source_payloads_unchanged':True,'backup_verified':True,'rollback_unit_test':True,
        'new_andalucia_events':len(events),'new_andalucia_projects':new_projects,
        'linked_existing_projects':len(events)-new_projects,
        'projects':conn.execute('SELECT count(*) FROM projects').fetchone()[0],
        'events':after,'idempotent_replay':before==after,
        'quality':dict(Counter(i['severity'] for i in issues)),
    }
    assert metrics['projects']==130 and metrics['events']==133,metrics
    assert new_projects==6 and len(events)==8 and before==after,metrics
    assert not metrics['quality'].get('ERROR'),metrics
    assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    (out/'certification.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    print('IDENTITY_REPLAY_CERTIFIED',json.dumps(metrics,ensure_ascii=False))
    conn.close()

if __name__=='__main__':main()
