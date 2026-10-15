"""Import complete historical source-months (data-export branch) into an operational database.

Additive and idempotent. Only shards marked CERTIFIED in index.json whose database digest
matches their manifest are read (CERTIFIED, or COMPLETE_WITH_QUALITY_FLAGS: every
source-day acquired, only record-level flags). Original source events are inserted unchanged; an event
already present with identical immutable evidence is skipped; an event present with
different evidence is never overwritten: the existing (official) record is kept and the
anomaly is reported. Source-scoped evidence tables are copied only for inserted events.
Nothing here re-parses, infers or enriches fields: the operational pipeline that follows
applies the reviewed identity/field repairs and the quality gate as for any other event.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

from app.db import connect
from app.store import save_event
from scripts.historical_month import month_bounds
from scripts.merge_historical_shards import EVENT_FIELDS, convert, original_signature

# Every source-day acquired in both cases. COMPLETE_WITH_QUALITY_FLAGS carries only
# record-level flags (missing name / MW, handled via config/manual_overrides.csv) or BOJA
# legally restricted notices, which are never projected as events.
ACCEPTED = ("CERTIFIED", "COMPLETE_WITH_QUALITY_FLAGS")
# Shard-time ERRORs that app.reporting now emits as WARN (manual-override queue).
RECORD_LEVEL = {"MISSING_PROJECT_NAME", "INVALID_POWER_MW"}

# Evidence tables keyed by source event or project that the portal needs and that are
# not re-derivable without re-downloading the official originals.
EVENT_SCOPED = {"regional_public_metadata": ("source_code", "external_id")}
DOCUMENT_SCOPED = ("dogc_document_observations",)
PROJECT_SCOPED = ("project_geo_enrichment",)


def verified_shards(export: Path) -> list[tuple[dict, Path]]:
    index = json.loads((export / "index.json").read_text(encoding="utf-8"))
    out = []
    for item in index.get("shards", []):
        if item.get("status") not in ACCEPTED:
            continue
        folder = export / "shards" / item["source"] / item["month"]
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        complete_days = (manifest.get("source_days_failed") == 0 and manifest.get("source_days_expected")
                         and manifest.get("source_days_ok") == manifest.get("source_days_expected"))
        blocking = [e for e in manifest.get("structural_errors") or [] if e.get("code") not in RECORD_LEVEL]
        if not complete_days or blocking:
            raise ValueError(f"Index status {item['status']} but source-days or structure incomplete: {folder}")
        if item["status"] == "CERTIFIED" and not manifest.get("certified"):
            raise ValueError(f"Index says CERTIFIED but manifest does not: {folder}")
        if (manifest.get("source"), manifest.get("month")) != (item["source"], item["month"]):
            raise ValueError(f"Shard scope differs from its folder: {folder}")
        digest = hashlib.sha256((folder / "historical.sqlite").read_bytes()).hexdigest()
        if digest != manifest.get("database_sha256"):
            raise ValueError(f"Historical database digest mismatch: {folder}")
        out.append((dict(manifest, export_status=item["status"]), folder))
    return out


def _table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _copy_rows(src, dst, table: str, where: str, params: tuple) -> int:
    if not (_table_exists(src, table) and _table_exists(dst, table)):
        return 0
    rows = src.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()
    if not rows:
        return 0
    cols = rows[0].keys()
    target_cols = {r[1] for r in dst.execute(f"PRAGMA table_info({table})")}
    cols = [c for c in cols if c in target_cols]
    sql = f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
    before = dst.total_changes
    for r in rows:
        dst.execute(sql, tuple(r[c] for c in cols))
    return dst.total_changes - before


def import_history(db: str, export: str, report: str | None = None) -> dict:
    export = Path(export)
    shards = verified_shards(export)
    conn = connect(db)
    summary = {"shards_imported": 0, "events_inserted": 0, "events_already_present": 0,
               "evidence_rows_copied": 0, "by_source": Counter(), "shard_status": Counter(), "conflicts": []}
    try:
        if conn.in_transaction:
            conn.commit()
        for manifest, folder in shards:
            first, last = month_bounds(manifest["month"])
            with sqlite3.connect(f"file:{(folder / 'historical.sqlite').resolve()}?mode=ro", uri=True) as src:
                src.row_factory = sqlite3.Row
                rows = [dict(r) for r in src.execute(
                    "SELECT e.*,p.project_name FROM events e JOIN projects p USING(project_key) "
                    "ORDER BY e.publication_date,e.source_code,e.external_id")]
                if len(rows) != manifest["events"]:
                    raise ValueError(f"Shard event count differs from manifest: {folder}")
                for row in rows:
                    if row["source_code"] != manifest["source"] or not first <= date.fromisoformat(row["publication_date"]) <= last:
                        raise ValueError(f"Event outside its certified source-month: {row['source_code']}:{row['external_id']}")
                    existing = conn.execute("SELECT * FROM events WHERE source_code=? AND external_id=?",
                                            (row["source_code"], row["external_id"])).fetchone()
                    if existing:
                        if original_signature(dict(existing)) != original_signature(row):
                            summary["conflicts"].append({"kind": "SOURCE_EVENT_DIFFERS_EXISTING_KEPT",
                                                         "source": row["source_code"], "external_id": row["external_id"],
                                                         "shard": f"{manifest['source']}/{manifest['month']}"})
                        else:
                            summary["events_already_present"] += 1
                        continue
                    inserted, _ = save_event(conn, convert({k: row[k] for k in EVENT_FIELDS}))
                    if not inserted:
                        raise RuntimeError(f"Event not inserted: {row['source_code']}:{row['external_id']}")
                    summary["events_inserted"] += 1
                    summary["by_source"][row["source_code"]] += 1
                    key = conn.execute("SELECT project_key FROM events WHERE source_code=? AND external_id=?",
                                       (row["source_code"], row["external_id"])).fetchone()[0]
                    for table in EVENT_SCOPED:
                        summary["evidence_rows_copied"] += _copy_rows(src, conn, table, "source_code=? AND external_id=?",
                                                                      (row["source_code"], row["external_id"]))
                    for table in DOCUMENT_SCOPED:
                        summary["evidence_rows_copied"] += _copy_rows(src, conn, table, "external_id=?", (row["external_id"],))
                    for table in PROJECT_SCOPED:
                        if key == row["project_key"]:
                            summary["evidence_rows_copied"] += _copy_rows(src, conn, table, "project_key=?", (key,))
                if "DOGC" == manifest["source"]:
                    # Held/excluded DOGC acts are observations without events; keep their audit trail.
                    summary["evidence_rows_copied"] += _copy_rows(
                        src, conn, "dogc_document_observations", "publication_date BETWEEN ? AND ?", (str(first), str(last)))
            summary["shards_imported"] += 1
            summary["shard_status"][manifest["export_status"]] += 1
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Integrity failure after historical import")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    summary["by_source"] = dict(sorted(summary["by_source"].items()))
    summary["shard_status"] = dict(summary["shard_status"])
    summary["note"] = "Complete official source-months only; uncovered source-months are not zero projects."
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        Path(report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("HISTORY_IMPORT", json.dumps({k: v for k, v in summary.items() if k != "conflicts"} | {"conflicts": len(summary["conflicts"])},
                                       ensure_ascii=False), flush=True)
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True)
    p.add_argument("--export", required=True, help="Checkout of the data-export branch")
    p.add_argument("--report")
    a = p.parse_args()
    import_history(a.db, a.export, a.report)


if __name__ == "__main__":
    main()
