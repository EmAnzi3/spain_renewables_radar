"""Collect the newest certified historical shard per (source, month) from Actions
artifacts and lay them out as plain files for a git data-export branch.

Read-only with respect to evidence: shard SQLite files and manifests are copied
byte-for-byte; nothing is merged, repaired or re-parsed here.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import zipfile
from datetime import date
from pathlib import Path

NAME_RE = re.compile(
    r"^(?:boe-historical|boja-historical|regional-historical-(?P<src>[A-Z\-]+))-"
    r"(?P<month>\d{4}-\d{2})(?:-attempt-\d+)?$"
)
EVENT_COLS = ("source_code", "external_id", "publication_date", "title", "url",
              "project_key", "event_type", "commercial_stage", "technology",
              "power_mw", "promoter", "expediente", "province", "ccaa")
PROJECT_COLS = ("project_key", "project_name", "technology", "power_mw", "promoter",
                "expediente", "province", "ccaa", "commercial_stage", "first_seen",
                "last_seen", "latest_event_type", "latest_source_code", "latest_source_url")


def gh_json(path: str):
    out = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def list_artifacts(repo: str) -> list[dict]:
    items, page = [], 1
    while True:
        data = gh_json(f"repos/{repo}/actions/artifacts?per_page=100&page={page}")
        batch = data.get("artifacts") or []
        items.extend(a for a in batch if not a.get("expired"))
        if len(batch) < 100:
            return items
        page += 1


def source_of(name: str, m: re.Match) -> str:
    if name.startswith("boe-"):
        return "BOE"
    if name.startswith("boja-"):
        return "BOJA"
    return m.group("src")


def download(repo: str, artifact_id: int) -> zipfile.ZipFile:
    raw = subprocess.run(["gh", "api", f"repos/{repo}/actions/artifacts/{artifact_id}/zip"],
                         check=True, capture_output=True).stdout
    return zipfile.ZipFile(io.BytesIO(raw))


def certified(manifest: dict) -> bool:
    return bool(manifest.get("certified")) and not manifest.get("source_days_failed") \
        and not (manifest.get("quality") or {}).get("ERROR")


def complete_with_flags(manifest: dict) -> bool:
    """Every source-day acquired, evidence inventory valid, only record-level quality ERRORs.
    Such shards are exported with an explicit status; certification is not claimed."""
    exp, ok = manifest.get("source_days_expected"), manifest.get("source_days_ok")
    return bool(exp) and exp == ok and manifest.get("source_days_failed") == 0 \
        and manifest.get("events") is not None and (manifest.get("quality") or {}).get("ERROR", 0) > 0


def quality_errors(z, names):
    q = next((n for n in names if n.endswith("quality_issues_latest.csv")), None)
    if not q:
        return []
    rows = csv.DictReader(io.StringIO(z.read(q).decode("utf-8-sig")))
    return [{k: r.get(k) for k in ("code", "project_key", "detail")} for r in rows if r.get("severity") == "ERROR"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", default="export")
    ap.add_argument("--from-month", default="2024-10")
    a = ap.parse_args()

    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    groups: dict[tuple[str, str], list[dict]] = {}
    for art in list_artifacts(a.repo):
        m = NAME_RE.match(art["name"])
        if not m or m.group("month") < a.from_month:
            continue
        groups.setdefault((source_of(art["name"], m), m.group("month")), []).append(art)

    index = []
    for (source, month), arts in sorted(groups.items()):
        chosen, fallback, reasons = None, None, []
        for art in sorted(arts, key=lambda x: x["created_at"], reverse=True):
            try:
                z = download(a.repo, art["id"])
            except subprocess.CalledProcessError:
                continue
            names = z.namelist()
            man_name = next((n for n in names if n.endswith("manifest.json") and n.count("/") <= 1), None)
            db_name = next((n for n in names if n.endswith("historical.sqlite")), None)
            if not man_name or not db_name:
                reasons.append({"artifact": art["name"], "reason": "no manifest or database"})
                continue
            manifest = json.loads(z.read(man_name))
            meta = {"source": source, "month": month, "artifact_id": art["id"],
                    "artifact_name": art["name"], "created_at": art["created_at"],
                    "run_id": (art.get("workflow_run") or {}).get("id"), "events": manifest.get("events")}
            if certified(manifest):
                chosen = dict(meta, status="CERTIFIED", z=z, man=man_name, db=db_name)
                break
            if fallback is None and complete_with_flags(manifest):
                fallback = dict(meta, status="COMPLETE_WITH_QUALITY_FLAGS", z=z, man=man_name, db=db_name,
                                quality_errors=quality_errors(z, names))
            reasons.append({"artifact": art["name"], "error": str(manifest.get("error", ""))[:200],
                            "source_days_failed": manifest.get("source_days_failed"),
                            "quality": manifest.get("quality")})
        pick = chosen or fallback
        if pick:
            dest = out / "shards" / source / month
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "manifest.json").write_bytes(pick["z"].read(pick["man"]))
            (dest / "historical.sqlite").write_bytes(pick["z"].read(pick["db"]))
            chosen = {k: v for k, v in pick.items() if k not in ("z", "man", "db")}
        else:
            chosen = None
        index.append(chosen or {"source": source, "month": month, "status": "NO_USABLE_SHARD",
                                "attempts": reasons})

    # Flat, human-readable views: one row per original event and per shard project.
    with (out / "events.csv").open("w", newline="", encoding="utf-8-sig") as fe, \
         (out / "projects.csv").open("w", newline="", encoding="utf-8-sig") as fp:
        we = csv.writer(fe); we.writerow(("shard_source", "shard_month") + EVENT_COLS)
        wp = csv.writer(fp); wp.writerow(("shard_source", "shard_month") + PROJECT_COLS)
        for row in index:
            if "artifact_id" not in row:
                continue
            db = out / "shards" / row["source"] / row["month"] / "historical.sqlite"
            with sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True) as c:
                for r in c.execute(f"SELECT {','.join(EVENT_COLS)} FROM events ORDER BY publication_date"):
                    we.writerow((row["source"], row["month"]) + tuple(r))
                for r in c.execute(f"SELECT {','.join(PROJECT_COLS)} FROM projects"):
                    wp.writerow((row["source"], row["month"]) + tuple(r))

    (out / "index.json").write_text(json.dumps({
        "generated": date.today().isoformat(),
        "repo": a.repo,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "note": "Raw certified shards, not merged; uncovered source/months are not zero projects.",
        "shards": index,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = sum("artifact_id" in r for r in index)
    flagged = sum(r.get("status") == "COMPLETE_WITH_QUALITY_FLAGS" for r in index)
    print(f"EXPORT shards_usable={ok} (with_quality_flags={flagged}) shards_missing={len(index) - ok}")


if __name__ == "__main__":
    main()
