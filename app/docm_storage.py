"""Scope a DOCM battery addition without borrowing its existing PV capacity.

The parser is source-wording based. The one reviewed legacy correction is
separately hash-locked, backed up and audited; it is not a quality-flag repair.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

RULE = 'DOCM_BATTERY_ADDITION_V1'
REVIEWED_ID = 'DOCM-2026-7037'
REVIEWED_RAW_SHA = 'ba5450fe79437e90326a3082f63b76b0ed0af7a887c099bc833c9a6143019a65'
SUBJECT = re.compile(r'hibridaci[oó]n\s+con\s+un\s+sistema\s+de\s+almacenamiento\s+mediante\s+bater[ií]as', re.I)
HEADING = re.compile(r'Las\s+caracter[ií]sticas\s+principales\s+del\s+sistema\s+de\s+almacenamiento\s+de\s+energ[ií]a\s+mediante\s+bater[ií]as\s+denominado\s+[“«"](?P<name>[^”»"\n]{3,100})[”»"]\s+se\s+resumen\s+a\s+continuaci[oó]n\s*:', re.I)
END = re.compile(r'(?:\n|^)(?:A\s+los\s+efectos|Lo\s+que\s+se\s+hace\s+p[uú]blico)\b', re.I)
ACTIVE_TOTAL = re.compile(r'\(\s*potencia\s+instalada\s+total\s+de\s+(\d+(?:,\d+)?)\s*(MW|kW)\s*\)', re.I)
QUANTITY = re.compile(r'(?<![\w.,])\d+(?:[.,]\d+)*\s*(?:MWh|MWp|MWn|MW|kWh|kVA|MVA|kW|W)\b', re.I)
SOURCE_FIELDS = ('id','source_code','external_id','publication_date','title','url','raw_text','created_at','project_key')


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def storage_evidence(title, raw_text):
    """Narrow, explicit battery-addition scope; missing body never falls back to PV."""
    if not SUBJECT.search(title):
        return None
    headings = list(HEADING.finditer(raw_text))
    flags = []
    name, power, span = None, None, None
    if len(headings) == 1:
        h = headings[0]
        candidate = ' '.join(h['name'].split())
        # Exact named component must also occur in the source title.
        if candidate.casefold() in ' '.join(title.split()).casefold():
            name = candidate
        end = END.search(raw_text, h.end())
        if end:
            block = raw_text[h.end():end.start()]
            matches = list(ACTIVE_TOTAL.finditer(block))
            values = {float(m[1].replace(',', '.')) / (1000 if m[2].casefold() == 'kw' else 1) for m in matches}
            if len(values) == 1:
                power = next(iter(values))
                m = matches[0]
                start, stop = h.end() + m.start(), h.end() + m.end()
                span = {'start': start, 'end': stop, 'quote': raw_text[start:stop]}
            elif len(values) > 1:
                flags.append({'severity':'WARN','code':'DOCM_BATTERY_POWER_CONFLICT'})
    if power is None:
        flags.append({'severity':'WARN','code':'DOCM_BATTERY_POWER_UNRESOLVED'})
    if name is None:
        flags.append({'severity':'WARN','code':'DOCM_BATTERY_NAME_UNRESOLVED'})
    flags.append({'severity':'INFO','code':'DOCM_BATTERY_SCOPE_SEPARATES_EXISTING_PV_ACCESS_AND_HYBRID_TOTAL'})
    return {'rule': RULE, 'project_name': name, 'technology': 'BESS', 'power_mw': power,
            'power_scope':'battery_module_active_power', 'hybridization_context':True,
            'source_raw_text_sha256':digest(raw_text), 'power_evidence':span,
            'source_quantities':[{'start':m.start(),'end':m.end(),'quote':m[0]} for m in QUANTITY.finditer(raw_text)],
            'quantity_aggregation_performed':False, 'quality_flags':flags}


def project_storage(event):
    evidence = storage_evidence(event.title, event.raw_text) if event.source_code == 'DOCM' else None
    if evidence is None:
        return event
    from app.parser import build_project_key
    return replace(event, project_name=evidence['project_name'], technology='BESS', power_mw=evidence['power_mw'],
                   project_key=build_project_key(evidence['project_name'],'BESS',event.province,event.external_id,event.expediente))


def source_fingerprint(conn):
    rows = [tuple(r) for r in conn.execute('SELECT '+','.join(SOURCE_FIELDS)+' FROM events ORDER BY id')]
    return digest(json.dumps(rows, ensure_ascii=False, separators=(',',':')))


def repair_and_record(conn, report_dir='reports/docm_storage'):
    """Record interpreted evidence and migrate the reviewed stale single-event projection.

    Unknown prior projections or shared projects stop for review. No identity,
    lifecycle, source text, timestamp or evidence from another collector changes.
    """
    if conn.in_transaction:
        raise ValueError('DOCM repair requires a clean transaction boundary')
    from app.parser import parse_event
    records, changes = [], []
    for source in conn.execute("SELECT * FROM events WHERE source_code='DOCM'"):
        row = dict(source)
        evidence = storage_evidence(row['title'], row['raw_text'] or '')
        if evidence is None:
            continue
        original = parse_event(**{k:row[k] for k in ('source_code','external_id','publication_date','title','url','raw_text')})
        projected = project_storage(original)
        if projected.project_key != row['project_key']:
            raise ValueError('DOCM storage identity requires separate review')
        project = dict(conn.execute('SELECT * FROM projects WHERE project_key=?',(row['project_key'],)).fetchone())
        one = conn.execute('SELECT COUNT(*) FROM events WHERE project_key=?',(row['project_key'],)).fetchone()[0] == 1
        expected = {'project_name':projected.project_name,'technology':projected.technology,'power_mw':projected.power_mw}
        stale = any(row[k] != expected[k] for k in ('technology','power_mw')) or (one and any(project[k] != v for k,v in expected.items()))
        if stale:
            if (row['external_id'] != REVIEWED_ID or digest(row['raw_text']) != REVIEWED_RAW_SHA or not one
                    or row['technology'] != 'HYBRID' or row['power_mw'] != 7.4
                    or project['project_name'] != 'mediante baterías BESS Almagro I'
                    or project['technology'] != 'HYBRID' or project['power_mw'] != 7.4
                    or projected.power_mw != 7.2 or projected.project_name != 'BESS Almagro I'):
                raise ValueError('Unreviewed DOCM legacy projection; no automatic correction')
            changes.append((row, project, expected))
        records.append((row, evidence))
    if not records:
        return {'status':'NOT_NEEDED','corrected_events':0,'evidence_records':0}
    out = Path(report_dir); out.mkdir(parents=True, exist_ok=True)
    backup = None
    if changes:
        backup = out / ('before_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite')
        with sqlite3.connect(backup) as destination:
            conn.backup(destination)
    before = source_fingerprint(conn)
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TABLE IF NOT EXISTS docm_projection_repairs (
            source_code TEXT, external_id TEXT, rule TEXT, repaired_at TEXT, source_sha256 TEXT,
            original_event_json TEXT, original_project_json TEXT, projection_json TEXT, backup_path TEXT,
            PRIMARY KEY(source_code,external_id,rule))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS regional_public_metadata (
            source_code TEXT NOT NULL,external_id TEXT NOT NULL,project_key TEXT NOT NULL,
            web_publication_date TEXT NOT NULL,source_url TEXT NOT NULL,evidence_json TEXT NOT NULL,
            PRIMARY KEY(source_code,external_id),FOREIGN KEY(project_key) REFERENCES projects(project_key))''')
        for row,project,expected in changes:
            conn.execute('INSERT INTO docm_projection_repairs VALUES (?,?,?,?,?,?,?,?,?)',
                         ('DOCM',row['external_id'],RULE,datetime.now(timezone.utc).isoformat(),digest(row['raw_text']),
                          json.dumps(row,ensure_ascii=False),json.dumps(project,ensure_ascii=False),json.dumps(expected),str(backup)))
            conn.execute('UPDATE events SET technology=?,power_mw=? WHERE id=?',(expected['technology'],expected['power_mw'],row['id']))
            conn.execute('UPDATE projects SET project_name=?,technology=?,power_mw=? WHERE project_key=?',
                         (expected['project_name'],expected['technology'],expected['power_mw'],row['project_key']))
        for row,evidence in records:
            previous = conn.execute('SELECT * FROM regional_public_metadata WHERE source_code=? AND external_id=?',('DOCM',row['external_id'])).fetchone()
            payload = {'extraction':evidence,'quality_flags':evidence['quality_flags'],'legal_documents':[]}
            serialized = json.dumps(payload,ensure_ascii=False,sort_keys=True)
            if previous and (previous['project_key'] != row['project_key'] or previous['source_url'] != row['url'] or
                             previous['web_publication_date'] != row['publication_date'] or previous['evidence_json'] != serialized):
                raise ValueError('Previously stored DOCM evidence differs; review required')
            conn.execute('INSERT OR IGNORE INTO regional_public_metadata VALUES (?,?,?,?,?,?)',
                         ('DOCM',row['external_id'],row['project_key'],row['publication_date'],row['url'],serialized))
        if source_fingerprint(conn) != before or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('DOCM repair violated immutable source or relational integrity')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    result = {'status':'REPAIRED' if changes else 'VERIFIED','corrected_events':len(changes),'evidence_records':len(records),
              'immutable_source_fingerprint':before,'source_fields_preserved':True,'backup_path':str(backup) if backup else None}
    (out/'latest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def validate_docm_storage(conn):
    """Read-only gate: replay the source interpretation and its persisted evidence."""
    checked = []
    for source in conn.execute("SELECT * FROM events WHERE source_code='DOCM'"):
        row = dict(source); evidence = storage_evidence(row['title'], row['raw_text'] or '')
        if evidence is None:
            continue
        meta = conn.execute('SELECT * FROM regional_public_metadata WHERE source_code=? AND external_id=?',('DOCM',row['external_id'])).fetchone()
        if (meta is None or meta['project_key'] != row['project_key'] or meta['source_url'] != row['url']
                or meta['web_publication_date'] != row['publication_date'] or json.loads(meta['evidence_json'])['extraction'] != evidence
                or row['power_mw'] != evidence['power_mw'] or row['technology'] != 'BESS'):
            raise ValueError('DOCM storage projected fields or provenance differ from original evidence')
        project = conn.execute('SELECT * FROM projects WHERE project_key=?',(row['project_key'],)).fetchone()
        if conn.execute('SELECT COUNT(*) FROM events WHERE project_key=?',(row['project_key'],)).fetchone()[0] == 1:
            if any(project[k] != evidence[k] for k in ('project_name','power_mw','technology')):
                raise ValueError('DOCM storage project differs from its source-scoped event')
        checked.append({'external_id':row['external_id'],'project_name':evidence['project_name'],
                        'power_mw':evidence['power_mw'],'power_scope':evidence['power_scope'],
                        'project_key':row['project_key'],'source_raw_text_sha256':evidence['source_raw_text_sha256']})
    return {'source_scoped_events':len(checked),'original_interpretation_replayed':True,'events':checked}
