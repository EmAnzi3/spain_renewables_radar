"""Summarise a historical shard folder (certified or not) for offline diagnosis."""
import csv, json, sys
from pathlib import Path
root = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
for man in root.glob("*/*/manifest.json"):
    src, month = man.parent.parent.name, man.parent.name
    d = {"source": src, "month": month, "manifest": json.loads(man.read_text(encoding="utf-8"))}
    log = man.parent / "collector.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        d["log_tail"] = lines[-80:]
        d["log_errors"] = [l for l in lines if any(k in l for k in ("ERROR", "Error", "Traceback", "Exception", "FAIL"))][:80]
    q = man.parent / "workspace/reports/quality_issues_latest.csv"
    if q.exists():
        with q.open(encoding="utf-8-sig", newline="") as f:
            d["quality_errors"] = [r for r in csv.DictReader(f) if r.get("severity") == "ERROR"][:50]
    cov = man.parent / "workspace/reports/coverage_latest.csv"
    if cov.exists():
        with cov.open(encoding="utf-8-sig", newline="") as f:
            d["failed_days"] = [r for r in csv.DictReader(f) if r.get("status") == "ERROR"][:40]
    (out / f"{src}-{month}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
