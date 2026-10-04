"""Backed-up repair of legacy identities derived from prose, preserving source payloads."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.identifiers import valid_expediente
from app.lifecycle import STAGE_RANK
from app.parser import parse_event, extract_project_name
from app.store import PROJECT_FIELDS

PROJECT_COLUMNS=('project_key',*PROJECT_FIELDS,'commercial_stage','first_seen','last_seen',
                 'latest_event_type','latest_source_code','latest_source_url')


def excluded_reason(row: dict) -> str | None:
    from app.collectors.boa import EXCLUDE as BOA_EXCLUDE
    from app.collectors.bocm import EXCLUDE as BOCM_EXCLUDE
    rule={'BOA':BOA_EXCLUDE,'BOCM':BOCM_EXCLUDE}.get(row['source_code'])
    if rule and rule.search(row['title']):return 'OUTSIDE_COLLECTOR_SCOPE_AFTER_SOURCE_REVIEW'
    return None


def _source_fingerprint(row: dict) -> str:
    immutable={k:row.get(k) for k in ('id','source_code','external_id','publication_date','title','url','raw_text',
                                     'technology','power_mw','promoter','province','ccaa','event_type','commercial_stage','created_at')}
    return hashlib.sha256(json.dumps(immutable,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def repair_legacy_identities(conn, *, report_dir='reports/identity_repair', backup_dir=None):
    rows=[dict(r) for r in conn.execute('SELECT * FROM events ORDER BY publication_date,id')]
    invalid_keys={r['project_key'] for r in rows if r['source_code'] in {'BOE','BOCYL','BOA','BOJA','DOCM','DOE','BORM','BOCM'} and r['expediente'] and not valid_expediente(r['expediente'])}
    excluded={r['id']:excluded_reason(r) for r in rows if excluded_reason(r)}
    if not invalid_keys and not excluded:return {'status':'NOT_NEEDED','events':len(rows)}
    if conn.in_transaction:raise RuntimeError('Identity repair requires a clean transaction boundary')
    out=Path(report_dir);out.mkdir(parents=True,exist_ok=True)
    db_name=conn.execute('PRAGMA database_list').fetchone()['file']
    backup_root=Path(backup_dir) if backup_dir else (Path(db_name).parent/'migrations' if db_name else out)
    backup_root.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=backup_root/f'pre_identity_v2_{stamp}.sqlite'
    target=sqlite3.connect(backup)
    try:conn.backup(target)
    finally:target.close()
    original_projects={r['project_key']:dict(r) for r in conn.execute('SELECT * FROM projects')}
    changed=[];kept=[];mapping=defaultdict(set);groups=defaultdict(list)
    for source in rows:
        row=dict(source)
        if row['id'] in excluded:continue
        if row['source_code'] in {'BOE','BOCYL','BOA','BOJA','DOCM','DOE','BORM','BOCM'}:
            parsed=parse_event(source_code=row['source_code'],external_id=row['external_id'],
                               publication_date=row['publication_date'],title=row['title'],url=row['url'],raw_text=row['raw_text'] or '')
            row['project_key']=parsed.project_key;row['expediente']=parsed.expediente;name=parsed.project_name
            if row['project_key']!=source['project_key'] or row['expediente']!=source['expediente']:
                changed.append({'source_code':row['source_code'],'external_id':row['external_id'],
                                'old_key':source['project_key'],'new_key':row['project_key'],
                                'old_expediente':source['expediente'],'new_expediente':row['expediente']})
        else:
            old=original_projects.get(row['project_key'],{})
            name=old.get('project_name') or extract_project_name(row['title'])
        row['_project_name']=name
        mapping[source['project_key']].add(row['project_key'])
        kept.append(row);groups[row['project_key']].append(row)
    projections={}
    for key,events in groups.items():
        p={column:None for column in PROJECT_COLUMNS};p['project_key']=key
        p['commercial_stage']='EARLY';p['first_seen']=events[0]['publication_date']
        for event in events:
            for field in PROJECT_FIELDS:
                value=event['_project_name'] if field=='project_name' else event[field]
                if value is not None:p[field]=value
            stage=event['commercial_stage']
            p['commercial_stage']='BLOCKED' if 'BLOCKED' in (p['commercial_stage'],stage) else max((p['commercial_stage'],stage),key=lambda x:STAGE_RANK.get(x,0))
            p.update(last_seen=event['publication_date'],latest_event_type=event['event_type'],
                     latest_source_code=event['source_code'],latest_source_url=event['url'])
        original=original_projects.get(key)
        if original:
            for field in ('province','ccaa'):
                if p[field] is None:p[field]=original[field]
        projections[key]=p
    summary={'status':'REPAIRED','backup_path':str(backup),'projects_before':len(original_projects),
             'projects_after':len(projections),'events_before':len(rows),'events_after':len(kept),
             'quarantined_source_events':len(excluded),'identity_changes':changed,
             'split_groups':{k:sorted(v) for k,v in mapping.items() if len(v)>1},'enrichment_rows_quarantined':0}
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TABLE IF NOT EXISTS identity_repair_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, repaired_at TEXT NOT NULL,
            original_table TEXT NOT NULL, old_key TEXT, reason TEXT NOT NULL, payload_json TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS quarantined_source_events (
            source_code TEXT NOT NULL, external_id TEXT NOT NULL, reason TEXT NOT NULL,
            payload_json TEXT NOT NULL, quarantined_at TEXT NOT NULL,
            PRIMARY KEY(source_code,external_id))''')
        for original in original_projects.values():
            conn.execute('INSERT INTO identity_repair_audit VALUES (NULL,?,?,?,?,?)',
                         (stamp,'projects',original['project_key'],'PROJECT_PROJECTION_BEFORE_REPAIR',json.dumps(original,ensure_ascii=False)))
        sql='INSERT INTO projects ('+','.join(PROJECT_COLUMNS)+') VALUES ('+','.join('?' for _ in PROJECT_COLUMNS)+') ON CONFLICT(project_key) DO UPDATE SET '+','.join(c+'=excluded.'+c for c in PROJECT_COLUMNS if c!='project_key')
        for p in projections.values():conn.execute(sql,tuple(p[c] for c in PROJECT_COLUMNS))
        for original in rows:
            if original['id'] in excluded:
                conn.execute('INSERT OR REPLACE INTO quarantined_source_events VALUES (?,?,?,?,?)',
                             (original['source_code'],original['external_id'],excluded[original['id']],json.dumps(original,ensure_ascii=False),stamp))
                conn.execute('DELETE FROM events WHERE id=?',(original['id'],))
        for row in kept:
            conn.execute('UPDATE events SET project_key=?,expediente=? WHERE id=?',(row['project_key'],row['expediente'],row['id']))
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('project_geo_enrichment','project_epc_evidence','project_identity_aliases'):
            if table not in tables:continue
            for old_key in original_projects:
                if old_key in projections:continue
                related=[dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE project_key=?',(old_key,))]
                targets=mapping.get(old_key,set())
                for row in related:
                    conn.execute('INSERT INTO identity_repair_audit VALUES (NULL,?,?,?,?,?)',
                                 (stamp,table,old_key,'REFERENCE_BEFORE_IDENTITY_REPAIR',json.dumps(row,ensure_ascii=False)))
                if len(targets)==1:
                    new_key=next(iter(targets))
                    try:
                        conn.execute(f'UPDATE {table} SET project_key=? WHERE project_key=?',(new_key,old_key))
                        continue
                    except sqlite3.IntegrityError:pass
                # A falsely merged group cannot donate its EPC/geography to one arbitrary plant.
                summary['enrichment_rows_quarantined']+=len(related)
                conn.execute(f'DELETE FROM {table} WHERE project_key=?',(old_key,))
        for old_key in original_projects:
            if old_key not in projections:conn.execute('DELETE FROM projects WHERE project_key=?',(old_key,))
        after={r['id']:dict(r) for r in conn.execute('SELECT * FROM events')}
        for original in rows:
            if original['id'] in excluded:continue
            if _source_fingerprint(original)!=_source_fingerprint(after[original['id']]):
                raise RuntimeError('Source payload changed during identity repair')
        if len(after)+len(excluded)!=len(rows):raise RuntimeError('Event accounting mismatch')
        if conn.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('Foreign-key violation after identity repair')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    (out/'latest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary
