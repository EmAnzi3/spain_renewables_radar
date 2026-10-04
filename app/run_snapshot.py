"""Reuse one validated source acquisition within a single CI run, never across runs."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_AGE_SECONDS = 3600


def snapshot_paths(directory: str | Path, scope: str, source_url: str) -> tuple[Path, Path]:
    key = hashlib.sha256((scope + "\n" + source_url).encode("utf-8")).hexdigest()
    root = Path(directory)
    return root / (key + ".raw"), root / (key + ".json")


def load_run_snapshot(
    directory: str | Path, scope: str, source_url: str, *, now: datetime | None = None
) -> tuple[bytes, dict[str, Any]] | None:
    """Return original bytes/audit only for the same scope and acquisition <1 hour old.

    Missing, corrupt, foreign-scope and expired snapshots are cache misses. The
    caller must validate the source schema again before using returned bytes.
    Neither a cache miss nor a failed live request may be treated as empty data.
    """
    if not scope:
        return None
    raw_path, audit_path = snapshot_paths(directory, scope, source_url)
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if not isinstance(audit, dict):
            return None
        if audit.get("run_snapshot_scope") != scope or audit.get("source_url") != source_url:
            return None
        if audit.get("complete") is not True:
            return None
        retrieved = datetime.fromisoformat(audit["retrieved_at"])
        if retrieved.tzinfo is None:
            return None
        current = now or datetime.now(timezone.utc)
        if not 0 <= (current - retrieved).total_seconds() <= MAX_AGE_SECONDS:
            return None
        raw = raw_path.read_bytes()
        if not raw or hashlib.sha256(raw).hexdigest() != audit.get("sha256"):
            return None
        return raw, audit
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save_run_snapshot(
    directory: str | Path, scope: str, source_url: str, raw: bytes, audit: dict[str, Any]
) -> None:
    """Persist unchanged source bytes and original audit after source validation."""
    if not scope:
        return
    if audit.get("complete") is not True or audit.get("source_url") != source_url:
        raise ValueError("Cannot cache an incomplete or foreign source acquisition")
    if not raw or hashlib.sha256(raw).hexdigest() != audit.get("sha256"):
        raise ValueError("Cannot cache source bytes with an invalid acquisition hash")
    retrieved = datetime.fromisoformat(audit["retrieved_at"])
    if retrieved.tzinfo is None:
        raise ValueError("Source acquisition timestamp must contain a timezone")
    raw_path, audit_path = snapshot_paths(directory, scope, source_url)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = dict(audit, run_snapshot_scope=scope)
    # Install the audit last, so an interrupted write cannot create a valid pair.
    raw_tmp = raw_path.with_suffix(".raw.tmp")
    audit_tmp = audit_path.with_suffix(".json.tmp")
    raw_tmp.write_bytes(raw)
    audit_tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(raw_tmp, raw_path)
    os.replace(audit_tmp, audit_path)
