"""Manually verified project-field corrections, applied without re-acquiring sources.

config/manual_overrides.csv (one row per field):
    selector,field,value,evidence_url,note,author,date
- selector: an official event identity "SOURCE:EXTERNAL_ID" (e.g. "BOA:007961616"),
  stable across runs, or a project_key.
- field: project_name | power_mw | promoter | province | ccaa | technology
- evidence_url: official document (or public source) proving the value. Required.

Original events (title, raw_text, url, dates) are never modified. Applied values
are logged in manual_field_overrides (dato arricchito manuale, with provenance)
and re-applied after every pipeline run, so collectors cannot overwrite them.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "config" / "manual_overrides.csv"
FIELDS = {"project_name", "power_mw", "promoter", "province", "ccaa", "technology"}
TECHNOLOGIES = {"PV", "WIND", "HYBRID", "BESS"}
COLUMNS = ("selector", "field", "value", "evidence_url", "note", "author", "date")


def load(path: Path = DEFAULT) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"manual_overrides.csv header must be: {','.join(COLUMNS)}")
        rows = []
        for n, r in enumerate(reader, 2):
            r = {k: (r.get(k) or "").strip() for k in COLUMNS}
            if not any(r.values()):
                continue
            if r["field"] not in FIELDS:
                raise ValueError(f"line {n}: field '{r['field']}' not allowed")
            if not r["selector"] or not r["value"]:
                raise ValueError(f"line {n}: selector and value are required")
            if not r["evidence_url"].startswith(("https://", "http://")):
                raise ValueError(f"line {n}: evidence_url (official document) is required")
            if r["field"] == "power_mw":
                v = float(r["value"].replace(",", "."))
                if not 0 < v <= 5000:
                    raise ValueError(f"line {n}: power_mw out of range")
                r["value"] = v
            if r["field"] == "technology" and r["value"] not in TECHNOLOGIES:
                raise ValueError(f"line {n}: technology must be one of {sorted(TECHNOLOGIES)}")
            r["line"] = n
            rows.append(r)
        return rows


def _project_key(conn, selector: str) -> str | None:
    if ":" in selector:
        source, external = selector.split(":", 1)
        row = conn.execute("SELECT project_key FROM events WHERE source_code=? AND external_id=?",
                           (source.strip().upper(), external.strip())).fetchone()
        return row[0] if row else None
    row = conn.execute("SELECT project_key FROM projects WHERE project_key=?", (selector,)).fetchone()
    return row[0] if row else None


def apply(conn: sqlite3.Connection, rows: list[dict] | None = None, path: Path = DEFAULT) -> dict:
    rows = load(path) if rows is None else rows
    conn.execute("""CREATE TABLE IF NOT EXISTS manual_field_overrides (
        project_key TEXT NOT NULL, field TEXT NOT NULL, value TEXT NOT NULL, previous_value TEXT,
        selector TEXT NOT NULL, evidence_url TEXT NOT NULL, note TEXT, author TEXT, date TEXT,
        applied_at TEXT NOT NULL, PRIMARY KEY(project_key, field))""")
    applied, unmatched = 0, []
    for r in rows:
        key = _project_key(conn, r["selector"])
        if not key:
            unmatched.append(r["selector"])  # project not (yet) in this database: kept for later runs
            continue
        prev = conn.execute(f"SELECT {r['field']} FROM projects WHERE project_key=?", (key,)).fetchone()[0]
        conn.execute(f"UPDATE projects SET {r['field']}=? WHERE project_key=?", (r["value"], key))
        conn.execute("""INSERT OR REPLACE INTO manual_field_overrides VALUES (?,?,?,
                COALESCE((SELECT previous_value FROM manual_field_overrides WHERE project_key=? AND field=?),?),
                ?,?,?,?,?,?)""",
                     (key, r["field"], str(r["value"]), key, r["field"], None if prev is None else str(prev),
                      r["selector"], r["evidence_url"], r["note"], r["author"], r["date"],
                      datetime.now(timezone.utc).isoformat()))
        applied += 1
    conn.commit()
    return {"rows": len(rows), "applied": applied, "unmatched": unmatched}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--overrides", default=str(DEFAULT))
    ap.add_argument("--review-queue", help="write CSV of records still awaiting manual data")
    a = ap.parse_args()
    with sqlite3.connect(a.db) as conn:
        conn.row_factory = sqlite3.Row
        print("MANUAL_OVERRIDES", apply(conn, path=Path(a.overrides)))
        if a.review_queue:
            print("REVIEW_QUEUE", review_queue(conn, Path(a.review_queue)))



def review_queue(conn: sqlite3.Connection, out: Path) -> int:
    """CSV of records awaiting manual data, with a ready-to-paste selector."""
    from app.reporting import write_quality_issues
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        issues, _, _ = write_quality_issues(conn, out_dir=tmp)
    wanted = {"MISSING_PROJECT_NAME": "project_name", "INVALID_POWER_MW": "power_mw"}
    rows = []
    for i in issues:
        if i["code"] not in wanted:
            continue
        ev = conn.execute("""SELECT source_code,external_id,publication_date,title,url FROM events
                             WHERE project_key=? ORDER BY publication_date DESC,id DESC LIMIT 1""",
                          (i["project_key"],)).fetchone()
        rows.append({"selector": f"{ev[0]}:{ev[1]}", "field": wanted[i["code"]], "value": "",
                     "evidence_url": ev[4], "publication_date": ev[2], "technology": i["technology"],
                     "power_mw": i["power_mw"], "province": i["province"], "title": ev[3][:400]})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["selector", "field", "value", "evidence_url", "publication_date",
                                          "technology", "power_mw", "province", "title"])
        w.writeheader(); w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    main()
