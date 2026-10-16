"""Merge project cards that are the same plant seen in different acts (projection-only, audited).

A plant gets two cards when one act carries its file number and another does not, or when the
same file is written differently. Cards merge only if: same normalised name (>= 4 chars), same
technology, same power to 0.001 MW, and nothing contradicts: one province at most, promoters
compatible, file numbers compatible (the same file written differently, or files of different
administrations such as INAGA environmental vs G-Z energy). Conflicts stay apart. Events,
evidence rows and aliases move to the canonical card; source events are never edited.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from app.identifiers import valid_expediente
from app.lifecycle import STAGE_RANK
from app.parser import normalize_text

LEGAL = re.compile(r"\b(?:s ?l ?u?|s ?a ?u?|sl|slu|sa|sau|s coop|scl|sociedad limitada|sociedad anonima|unipersonal)\b")
GENERIC = {'del','las','los','para','con','por','planta','parque','proyecto','instalacion','solar','fotovoltaica',
           'fotovoltaico','eolico','almacenamiento','hibridacion','energia','mediante','baterias'}
MOVE_TABLES = ('regional_public_metadata', 'project_epc_evidence', 'project_identity_aliases', 'manual_field_overrides')


def _promoter_core(value):
    if not value:
        return None
    value = re.split(r"[(\[]|\bn[uú]mero\b|\bcon (?:cif|nif|domicilio)\b", value, flags=re.I)[0]
    tokens = [t for t in LEGAL.sub(' ', normalize_text(value)).split() if len(t) > 1]
    return tuple(tokens) or None


def promoters_compatible(values) -> bool:
    cores = {c for c in (_promoter_core(v) for v in values) if c}
    for a in cores:
        for b in cores:
            if a == b or a[:len(b)] == b or b[:len(a)] == a:
                continue
            sa, sb = set(a), set(b)
            if len(sa & sb) / max(1, len(sa | sb)) < 0.6:
                return False
    return True


def _file_family(value):
    n = normalize_text(value)
    return n.split()[0] if n else ''


def files_compatible(values) -> bool:
    by_family = defaultdict(set)
    for v in values:
        if v and valid_expediente(v):
            by_family[_file_family(v)].add(tuple(sorted(re.findall(r"\d+", v))))
    return all(len(numbers) <= 1 for numbers in by_family.values())


def duplicate_groups(conn) -> list[list[dict]]:
    groups = defaultdict(list)
    for row in conn.execute("SELECT * FROM projects WHERE project_name IS NOT NULL AND technology IS NOT NULL AND power_mw IS NOT NULL"):
        p = dict(row)
        name = normalize_text(p['project_name'])
        # A real name has a word of 3+ letters that is not a heading word ('de 1' is not a name).
        if len(name) >= 4 and any(len(w) >= 3 and w.isalpha() and w not in GENERIC for w in name.split()):
            groups[(name, p['technology'], round(p['power_mw'], 3))].append(p)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        provinces = {m['province'] for m in members if m['province']}
        if len(provinces) <= 1 and files_compatible([m['expediente'] for m in members]) \
                and promoters_compatible([m['promoter'] for m in members]):
            out.append(members)
    return out


def _reproject(conn, key: str) -> None:
    events = [dict(r) for r in conn.execute("SELECT * FROM events WHERE project_key=? ORDER BY publication_date,id", (key,))]
    stages = [e['commercial_stage'] for e in events]
    stage = 'BLOCKED' if 'BLOCKED' in stages else max(stages, key=lambda s: STAGE_RANK.get(s, 0))
    fields = {f: None for f in ('technology', 'power_mw', 'promoter', 'expediente', 'province', 'ccaa')}
    for e in events:
        for f in fields:
            if e.get(f) is not None:
                fields[f] = e[f]
    project = dict(conn.execute("SELECT * FROM projects WHERE project_key=?", (key,)).fetchone())
    if project['expediente'] and valid_expediente(project['expediente']):
        fields['expediente'] = project['expediente']  # keep the canonical file number
    last = events[-1]
    sets = ', '.join(f"{f}=?" for f in fields)
    conn.execute(f"UPDATE projects SET {sets}, commercial_stage=?, first_seen=?, last_seen=?, latest_event_type=?, "
                 "latest_source_code=?, latest_source_url=? WHERE project_key=?",
                 (*fields.values(), stage, events[0]['publication_date'], last['publication_date'], last['event_type'],
                  last['source_code'], last['url'], key))


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def merge_duplicate_projects(conn) -> dict:
    conn.execute("""CREATE TABLE IF NOT EXISTS project_merge_audit (
        merged_key TEXT NOT NULL, canonical_key TEXT NOT NULL, rule TEXT NOT NULL,
        merged_project_json TEXT NOT NULL, merged_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS project_identity_aliases (
        alias_key TEXT PRIMARY KEY, project_key TEXT NOT NULL, rule TEXT NOT NULL, source_code TEXT NOT NULL,
        external_id TEXT NOT NULL, evidence_json TEXT NOT NULL, FOREIGN KEY(project_key) REFERENCES projects(project_key))""")
    tables, stamp, merged = _tables(conn), datetime.now(timezone.utc).isoformat(), 0
    for members in duplicate_groups(conn):
        members.sort(key=lambda p: (not (p['expediente'] and valid_expediente(p['expediente'])), p['first_seen'], p['project_key']))
        canonical = members[0]['project_key']
        for dup in members[1:]:
            key = dup['project_key']
            conn.execute("UPDATE events SET project_key=? WHERE project_key=?", (canonical, key))
            for table in MOVE_TABLES:
                if table in tables:
                    conn.execute(f"UPDATE OR IGNORE {table} SET project_key=? WHERE project_key=?", (canonical, key))
                    conn.execute(f"DELETE FROM {table} WHERE project_key=?", (key,))
            if 'project_geo_enrichment' in tables:
                conn.execute("UPDATE OR IGNORE project_geo_enrichment SET project_key=? WHERE project_key=?", (canonical, key))
                conn.execute("DELETE FROM project_geo_enrichment WHERE project_key=?", (key,))
            first = conn.execute("SELECT source_code, external_id FROM events WHERE project_key=? ORDER BY publication_date LIMIT 1",
                                 (canonical,)).fetchone()
            conn.execute("INSERT OR REPLACE INTO project_identity_aliases VALUES (?,?,?,?,?,?)",
                         (key, canonical, 'EXACT_NAME_TECH_POWER_COMPATIBLE_FIELDS', first[0], first[1],
                          json.dumps({k: dup[k] for k in ('project_name', 'technology', 'power_mw', 'province', 'expediente')},
                                     ensure_ascii=False)))
            conn.execute("INSERT INTO project_merge_audit VALUES (?,?,?,?,?)",
                         (key, canonical, 'EXACT_NAME_TECH_POWER_COMPATIBLE_FIELDS', json.dumps(dup, ensure_ascii=False), stamp))
            conn.execute("DELETE FROM projects WHERE project_key=?", (key,))
            merged += 1
        _reproject(conn, canonical)
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        conn.rollback()
        raise RuntimeError("Foreign-key violation after project merge")
    conn.commit()
    return {'merged_cards': merged}
