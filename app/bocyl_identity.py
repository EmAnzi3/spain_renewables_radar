"""Repair edition-level BOCYL ids from their own official document URL, with backup."""
from __future__ import annotations
import json,re,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from app.collectors.bocyl import ID_RE


def repair_bocyl_external_ids(conn):
    rows=[dict(r) for r in conn.execute("SELECT * FROM events WHERE source_code='BOCYL'")]
    changes=[]
    for row in rows:
        if not re.fullmatch(r'BOCYL-D-\d{8}-\d+',row['external_id']):continue
        if urlparse(row['url']).hostname!='bocyl.jcyl.es':
            raise RuntimeError('Cannot resolve old BOCYL identity without official source URL')
        match=ID_RE.search(row['url'])
        if not match or not match[1].startswith(row['external_id']+'-'):
            raise RuntimeError('Cannot resolve truncated BOCYL identity from source URL')
        new=match[1].upper()
        if conn.execute("SELECT 1 FROM events WHERE source_code='BOCYL' AND external_id=?",(new,)).fetchone():
            raise RuntimeError('Conflicting BOCYL identity: migration will not discard either event')
        changes.append((row,new))
    if not changes:return {'changed':0}
    if conn.in_transaction:raise RuntimeError('BOCYL repair requires a clean transaction boundary')
    filename=conn.execute('PRAGMA database_list').fetchone()['file']
    out=(Path(filename).parent if filename else Path('data'))/'migrations';out.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=out/f'pre_bocyl_document_ids_{stamp}.sqlite'
    target=sqlite3.connect(backup)
    try:conn.backup(target)
    finally:target.close()
    before_count=conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TABLE IF NOT EXISTS source_identity_repair (
            source_code TEXT NOT NULL,old_external_id TEXT NOT NULL,new_external_id TEXT NOT NULL,
            repaired_at TEXT NOT NULL,original_payload_json TEXT NOT NULL,backup_path TEXT NOT NULL,
            PRIMARY KEY(source_code,old_external_id))''')
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for original,new in changes:
            conn.execute('INSERT INTO source_identity_repair VALUES (?,?,?,?,?,?)',
                         ('BOCYL',original['external_id'],new,stamp,json.dumps(original,ensure_ascii=False),str(backup)))
            conn.execute('UPDATE events SET external_id=? WHERE id=?',(new,original['id']))
            for table in ('project_identity_aliases','event_source_metadata'):
                if table in tables:
                    conn.execute(f"UPDATE {table} SET external_id=? WHERE source_code='BOCYL' AND external_id=?",(new,original['external_id']))
            after=dict(conn.execute('SELECT * FROM events WHERE id=?',(original['id'],)).fetchone())
            expected=dict(original,external_id=new)
            if after!=expected:raise RuntimeError('BOCYL source payload changed during id repair')
        if conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]!=before_count:raise RuntimeError('BOCYL event accounting mismatch')
        if conn.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('BOCYL reference integrity failure')
        conn.commit()
    except Exception:
        conn.rollback();raise
    return {'changed':len(changes),'backup_path':str(backup)}
