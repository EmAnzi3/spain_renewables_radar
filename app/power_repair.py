"""Re-read stored power with the current generic rule (projection-only, audited, idempotent).

Fixes values produced by the pre-2026-10-16 extractor: thousands separators read as decimals
('4.900 kW' -> 0.0049 MW), the first MW figure winning over the labelled installed capacity
(an inverter limit of 0,99 MW instead of 4.990 kW), turbine-unit or access values.
Source text, title, URL, dates and lifecycle are untouched. Acts projected by a reviewed
source-specific rule (DOCM / BOCYL storage, DOGC, DOG, SABIA, GVA) are never touched. A value
the current rule cannot attribute to the plant becomes None ("MW not available"), never a guess.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.parser import extract_power_mw

GENERIC_SOURCES = ('BOE', 'BOCYL', 'BOA', 'BOJA', 'DOCM', 'DOE', 'BORM', 'BOCM', 'DOGV', 'AND_PUBLIC')
RULE = 'POWER_RULE_2026_10_16'


def _reviewed_projection(row: dict) -> bool:
    if row['source_code'] == 'DOCM':
        from app.docm_storage import storage_evidence
        return storage_evidence(row['title'], row['raw_text'] or '') is not None
    if row['source_code'] == 'BOCYL':
        from app.bocyl_storage import battery_projection
        return battery_projection(row['title'], row['raw_text'] or '') is not None
    return False


def current_power(title: str, raw_text: str) -> float | None:
    value = extract_power_mw(title)
    return extract_power_mw(raw_text or '') if value is None else value


def _same(a, b) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)


def repair_power(conn) -> dict:
    conn.execute("""CREATE TABLE IF NOT EXISTS power_reparse_repairs (
        source_code TEXT NOT NULL, external_id TEXT NOT NULL, project_key TEXT NOT NULL,
        previous_power_mw REAL, power_mw REAL, rule TEXT NOT NULL, repaired_at TEXT NOT NULL)""")
    marks = ','.join('?' for _ in GENERIC_SOURCES)
    rows = [dict(r) for r in conn.execute(
        f"SELECT id,source_code,external_id,project_key,title,raw_text,power_mw FROM events WHERE source_code IN ({marks})",
        GENERIC_SOURCES)]
    stamp = datetime.now(timezone.utc).isoformat()
    changed, keys = 0, set()
    for row in rows:
        new = current_power(row['title'], row['raw_text'])
        if _same(new, row['power_mw']) or _reviewed_projection(row):
            continue
        conn.execute('UPDATE events SET power_mw=? WHERE id=?', (new, row['id']))
        conn.execute('INSERT INTO power_reparse_repairs VALUES (?,?,?,?,?,?,?)',
                     (row['source_code'], row['external_id'], row['project_key'], row['power_mw'], new, RULE, stamp))
        changed += 1
        keys.add(row['project_key'])
    projects = 0
    for key in keys:
        # Same rule as app.store.save_event: the most recent non-null act value wins.
        latest = conn.execute('SELECT power_mw FROM events WHERE project_key=? AND power_mw IS NOT NULL '
                              'ORDER BY publication_date DESC, id DESC LIMIT 1', (key,)).fetchone()
        value = latest[0] if latest else None
        current = conn.execute('SELECT power_mw FROM projects WHERE project_key=?', (key,)).fetchone()
        if current is not None and not _same(current[0], value):
            conn.execute('UPDATE projects SET power_mw=? WHERE project_key=?', (value, key))
            projects += 1
    conn.commit()
    return {'events_changed': changed, 'projects_changed': projects, 'rule': RULE}
