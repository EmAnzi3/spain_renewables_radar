"""Seed reusable official HTML; dates/provenance remain unchanged and indexes are fetched live."""
from __future__ import annotations
import hashlib,json,shutil,sys,os
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.collectors.sabia import PARSER_VERSION


def seed_details(source:Path,destination:Path,now=None):
    now=now or datetime.now(timezone.utc)
    destination.mkdir(parents=True,exist_ok=True)
    result={"seeded":0,"expired_or_invalid":0,"index_files_copied":0,"original_retrieval_dates_preserved":True}
    for path in sorted(source.glob("**/*.json")):
        if not path.stem.isdigit() or len(path.stem)!=8:continue
        try:
            record=json.loads(path.read_text(encoding="utf-8"));raw=path.with_suffix(".html")
            at=datetime.fromisoformat(record["retrieved_at"])
            age=(now-at).total_seconds()
            if not raw.exists() or not 0<=age<86400:raise ValueError("expired detail")
            if record["detail"]["environmental_code"]!=path.stem:raise ValueError("identity mismatch")
            if hashlib.sha256(raw.read_bytes()).hexdigest()!=record["sha256"]:raise ValueError("raw digest mismatch")
            existing=destination/path.name
            if existing.exists():
                old=json.loads(existing.read_text())
                if old["retrieved_at"]>=record["retrieved_at"]:continue
            shutil.copyfile(path,existing);shutil.copyfile(raw,destination/raw.name)
            result["seeded"]+=1
        except (KeyError,ValueError,TypeError):result["expired_or_invalid"]+=1
    return result


def main():
    today=datetime.now(timezone.utc).date().isoformat()
    source=Path("sabia-recovery-input/data/sabia_cache")
    result=seed_details(source,Path("data/sabia_cache")/today/PARSER_VERSION)
    result["origin_run"]=int(os.getenv("SABIA_SEED_RUN_ID","37160816843"))
    result["cache_check_date"]=today
    result["note"]="Original detail retrieval times are unchanged. All five discovery indexes must be acquired live."
    out=Path("reports/sabia");out.mkdir(parents=True,exist_ok=True)
    (out/"cache_seed.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("SABIA_CACHE_SEED",json.dumps(result),flush=True)

if __name__=="__main__":main()
