"""Reclassify stored DIA events whose operative clause is unfavourable (projection-only).

Source text, title, URL and dates are untouched; only the derived event_type/commercial_stage
change, and every change is logged in dia_outcome_repairs. Idempotent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.lifecycle import dia_outcome


def repair_unfavourable_dia(conn) -> dict:
    conn.execute("""CREATE TABLE IF NOT EXISTS dia_outcome_repairs (
        source_code TEXT NOT NULL, external_id TEXT NOT NULL, project_key TEXT NOT NULL,
        previous_event_type TEXT NOT NULL, previous_project_stage TEXT, repaired_at TEXT NOT NULL,
        PRIMARY KEY(source_code, external_id))""")
    rows = conn.execute("SELECT id,source_code,external_id,project_key,raw_text FROM events WHERE event_type='DIA'").fetchall()
    hits = [r for r in rows if dia_outcome(r[4]) == "DIA_UNFAVOURABLE"]
    stamp = datetime.now(timezone.utc).isoformat()
    for event_id, source, external_id, key, _ in hits:
        previous = conn.execute("SELECT commercial_stage FROM projects WHERE project_key=?", (key,)).fetchone()
        conn.execute("INSERT OR IGNORE INTO dia_outcome_repairs VALUES (?,?,?,?,?,?)",
                     (source, external_id, key, "DIA", previous[0] if previous else None, stamp))
        conn.execute("UPDATE events SET event_type='DIA_UNFAVOURABLE',commercial_stage='BLOCKED' WHERE id=?", (event_id,))
        conn.execute("UPDATE projects SET commercial_stage='BLOCKED' WHERE project_key=?", (key,))
        latest = conn.execute("SELECT event_type FROM events WHERE project_key=? ORDER BY publication_date DESC,id DESC LIMIT 1",
                              (key,)).fetchone()
        if latest:
            conn.execute("UPDATE projects SET latest_event_type=? WHERE project_key=?", (latest[0], key))
    conn.commit()
    return {"reclassified_events": len(hits), "projects": len({h[3] for h in hits})}
