"""Auditable national historical discovery from free, official Spanish gazettes.

Scanning generates immutable source-event candidate bundles, NOT production
projects or false new-day notifications. Import requires a separate identity,
field-quality and cross-source gate. Unsupported regions are never called
complete. All observed gaps are explicit and restartable by source/month.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from app.run_pipeline import COLLECTOR_CLASSES

NATIONAL_START = date(2024, 10, 12)
REGIONAL_GAZETTES = {
    "BOJA": "Andalucía", "BOA": "Aragón", "BOCYL": "Castilla y León",
    "DOCM": "Castilla-La Mancha", "DOGC": "Catalunya",
    "DOE": "Extremadura", "DOG": "Galicia", "BOCM": "Madrid",
    "BORM": "Murcia",
}
MISSING_GAZETTES = {
    "BOPA": "Asturias", "BOIB": "Illes Balears",
    "BOC-CAN": "Canarias", "BOCANT": "Cantabria",
    "DOGV": "Comunitat Valenciana", "BON": "Navarra",
    "BOPV": "País Vasco", "BOR": "La Rioja",
}
REGIONAL_NAMES = {**REGIONAL_GAZETTES, **MISSING_GAZETTES}
SCANNABLE = ("BOE", "BOJA", "BOA", "BOCYL", "DOCM", "DOGC", "DOE", "DOG", "BOCM", "BORM")
SOURCE_HOSTS = {
    "BOE": {"www.boe.es", "boe.es"},
    "BOJA": {"www.juntadeandalucia.es", "juntadeandalucia.es"},
    "BOA": {"www.boa.aragon.es", "boa.aragon.es"},
    "BOCYL": {"bocyl.jcyl.es", "www.bocyl.jcyl.es"},
    "DOCM": {"docm.jccm.es"},
    "DOE": {"doe.juntaex.es"},
    "DOG": {"www.xunta.gal", "xunta.gal"},
    "DOGC": {"portaldogc.gencat.cat", "dogc.gencat.cat"},
    "BOCM": {"www.bocm.es", "bocm.es"},
    "BORM": {"www.borm.es", "borm.es", "transparencia.carm.es"},
}
HARD_MAX_DAYS = 31
HARD_MAX_ITEMS_PER_DAY = 2000


def days(start: date, end: date):
    current=start
    while current<=end:
        yield current
        current+=timedelta(days=1)


def months(start: date, end: date) -> list[dict]:
    """Disjoint, continuous calendar-month partitions, preserving partial edges."""
    if end<start: raise ValueError("Invalid historical window")
    entries=[]
    year,month=start.year,start.month
    while (year,month)<=(end.year,end.month):
        month_start=date(year,month,1)
        next_start=date(year+1,1,1) if month==12 else date(year,month+1,1)
        first=max(start,month_start)
        last=min(end,next_start-timedelta(days=1))
        entries.append({"start":first.isoformat(),"end":last.isoformat(),
                        "days":(last-first).days+1,"month":month_start.strftime("%Y-%m")})
        year,month=next_start.year,next_start.month
    if entries[0]["start"]!=start.isoformat() or entries[-1]["end"]!=end.isoformat():
        raise ValueError("Historical partitions do not cover requested edges")
    if sum(e["days"] for e in entries)!=(end-start).days+1:
        raise ValueError("Historical month windows contain a gap or overlap")
    return entries


def build_plan(*,start: date=NATIONAL_START,end: date=date(2026,10,11)) -> dict:
    if not (date(2000,1,1)<=start<=end):
        raise ValueError("Invalid period")
    windows=months(start,end)
    tasks=[]
    for source in SCANNABLE:
        for window in windows:
            reason=None
            if source=="BORM" and int(window["month"][:4])<end.year:
                reason="BORM_CURRENT_YEAR_INDEX_ONLY_NO_HISTORICAL_PROOF"
            tasks.append(dict(source_code=source,region=REGIONAL_GAZETTES.get(source,"Spagna nazionale"),
                **window, status="UNSUPPORTED" if reason else "PENDING",
                limitation=reason))
    gaps=[dict(source_code=code,region=region,status="NO_COLLECTOR_IMPLEMENTED",
               reason="Official regional gazette not yet certified")
          for code,region in MISSING_GAZETTES.items()]
    gaps.extend([
        dict(source_code="GVA_PUBLIC",region="Comunitat Valenciana",
             status="SOURCE_UNAVAILABLE",reason="Current official portal does not respond reliably"),
        dict(source_code="MITECO_SABIA",region="Spagna nazionale",
             status="SEPARATE_SNAPSHOT",reason="Current all-state inventory; administrative milestones are not dated gazette publications"),
        dict(source_code="AND_PUBLIC",region="Andalucía",
             status="SEPARATE_SNAPSHOT",reason="Complete current archive, acquire once; do not download 25 times"),
    ])
    return dict(schema="spain-historical-backfill-plan-v1",
        period_start=start.isoformat(),period_end=end.isoformat(),period_days=(end-start).days+1,
        month_windows=len(windows),national_bulletin="BOE",
        regional_gazettes_implemented=len(REGIONAL_GAZETTES),regional_gazettes_total=17,
        regional_gazettes_missing=len(MISSING_GAZETTES),
        months=windows,tasks=tasks,source_gaps=gaps,
        quality_rule="PENDING and UNSUPPORTED are never counted as complete; no bulk project creation from an unreviewed scan")


def official_event(event, source: str, day: date) -> dict:
    """Preserve every original required field. Refuse synthetic missing provenance."""
    fields=asdict(event)
    if fields.get("source_code")!=source or fields.get("publication_date")!=day.isoformat():
        raise ValueError("Collector identity or published date outside the requested day")
    identity=fields.get("external_id")
    if not isinstance(identity,str) or not 3<=len(identity)<=180:
        raise ValueError("External ID not stable")
    raw=fields.get("raw_text")
    if not isinstance(raw,str) or not raw.strip():
        raise ValueError("Missing official raw text")
    url=fields.get("url")
    if not isinstance(url,str):
        raise ValueError("Missing source URL")
    parsed=urlsplit(url)
    if parsed.scheme!="https" or parsed.hostname not in SOURCE_HOSTS[source] or parsed.username or parsed.password:
        raise ValueError("Source URL is not on the official gazette host")
    if fields.get("power_mw") is not None and not isinstance(fields["power_mw"],(int,float)):
        raise ValueError("Power is not numeric")
    return fields


def issues(fields:dict) -> list[str]:
    found=[]
    name=fields.get("project_name")
    if not name:found.append("NO_UNAMBIGUOUS_PROJECT_NAME")
    mw=fields.get("power_mw")
    if mw is None:found.append("MW_MISSING")
    elif mw<=0 or mw>1000:found.append("MW_REVIEW_REQUIRED")
    promoter=fields.get("promoter")
    if not promoter:found.append("PROMOTER_NOT_EXTRACTED")
    elif re.search(r"\b(?:dispone de capacidad|peticionario\s+es|t[eé]cnico\-econ[oó]mica)\b",promoter,re.I):
        found.append("PROMOTER_MALFORMED")
    if not fields.get("province"):found.append("PROVINCE_MISSING_OR_MULTIPROVINCE")
    if not fields.get("expediente"):found.append("EXPEDIENTE_MISSING")
    return found


def batch_directory(root:Path,source:str,start:date,end:date)->Path:
    return root/(source+"_"+start.isoformat()+"_"+end.isoformat())


def persist_json(file:Path,payload)->None:
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def scan_source(*,source:str,start:date,end:date,out:Path,collector=None,
                clock:date|None=None)->dict:
    if source not in SCANNABLE or source not in COLLECTOR_CLASSES:
        raise ValueError("Only implemented official national/regional gazettes can be scanned")
    today=clock or datetime.now(ZoneInfo("Europe/Madrid")).date()
    if start>end or (end-start).days+1>HARD_MAX_DAYS or end>=today:
        raise ValueError("Historical batches are limited to 31 complete Spanish calendar days")
    target=batch_directory(out,source,start,end)
    target.mkdir(parents=True,exist_ok=True)
    scanned=[];accepted={};all_days=[];failures=[]
    if source=="BORM" and (start.year!=today.year or end.year!=today.year):
        failures=[dict(date=day.isoformat(),status="UNSUPPORTED",
                       error="BORM_CURRENT_YEAR_INDEX_ONLY_NO_HISTORICAL_PROOF")
                  for day in days(start,end)]
        all_days=failures
    else:
        external=collector or COLLECTOR_CLASSES[source](timeout=30,user_agent="SpainRenewablesRadar/0.7 (official historical audit)")
        try:
            for day in days(start,end):
                candidates=[]
                row=dict(date=day.isoformat(),status="ERROR",candidates=0,accepted=0,error=None)
                try:
                    candidates=external.collect_day(day)
                    if not isinstance(candidates,list) or len(candidates)>HARD_MAX_ITEMS_PER_DAY:
                        raise ValueError("Unbounded or malformed official daily collector output")
                    mapped=[official_event(candidate,source,day) for candidate in candidates]
                    identities=[x["external_id"] for x in mapped]
                    if len(set(identities))!=len(identities):
                        raise ValueError("Duplicate official source identity within one day")
                    for fields in mapped:
                        old=accepted.get(fields["external_id"])
                        if old is not None and old!=fields:
                            raise ValueError("Source reused one external_id for different official events/dates")
                    for fields in mapped:
                        accepted[fields["external_id"]]=fields
                    row.update(status="COMPLETE",candidates=len(candidates),accepted=len(mapped),
                               original_sha256=hashlib.sha256(json.dumps(mapped,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
                    scanned.extend(mapped)
                except Exception as exc:
                    row["error"]=f"{type(exc).__name__}: {exc}"[:450]
                    failures.append(row)
                all_days.append(row)
                persist_json(target/"progress.json",dict(source=source,days=all_days,
                    latest_checked=day.isoformat(),status="IN_PROGRESS",
                    scanned_events=len(scanned),errors=len(failures)))
                print("HISTORIC_SOURCE_DAY",json.dumps(dict(source_code=source,**row),ensure_ascii=False),flush=True)
        finally:
            if hasattr(external,"close"):external.close()
    flags={key:sum(key in issues(e) for e in scanned) for key in (
        "NO_UNAMBIGUOUS_PROJECT_NAME","MW_MISSING","MW_REVIEW_REQUIRED",
        "PROMOTER_NOT_EXTRACTED","PROMOTER_MALFORMED","PROVINCE_MISSING_OR_MULTIPROVINCE")}
    provinces={}
    for e in scanned:
        key=e.get("province") or "UNALLOCATED"
        p=provinces.setdefault(key,{"events":0,"identified_mw_sum_not_unique_project_capacity":0.0})
        p["events"]+=1
        if e.get("power_mw") is not None and e["power_mw"]>0:
            p["identified_mw_sum_not_unique_project_capacity"]+=e["power_mw"]
    full=len(all_days)==(end-start).days+1 and all(x["status"]=="COMPLETE" for x in all_days)
    outcome=dict(schema="official-source-month-observations-v1",source_code=source,
        region=REGIONAL_GAZETTES.get(source,"Spagna nazionale"),
        from_date=start.isoformat(),until_date=end.isoformat(),
        intended_source_days=(end-start).days+1,
        covered_days=sum(x["status"]=="COMPLETE" for x in all_days),
        failed_days=sum(x["status"]=="ERROR" for x in all_days),
        unsupported_days=sum(x["status"]=="UNSUPPORTED" for x in all_days),
        complete=full,status="COMPLETE" if full else "INCOMPLETE",
        scanned_events=len(scanned),unique_source_ids=len(accepted),
        extraction_review_flags=flags,
        geographic_observations_not_unique_projects=provinces,
        representative_company_coverage=sum(bool(x.get("promoter")) for x in scanned),
        input_window_is_historical=True,events_inserted_into_production_db=0,
        project_fields_rewritten=False,source_urls_preserved=True,
        source_dates_preserved=True,certification_limit="Official dated source-day observations, not unique project reconciliation or national completeness",
        days=all_days)
    persist_json(target/"audit.json",outcome)
    persist_json(target/"events.json",scanned)
    flags_rows=[dict(source_code=source,external_id=e["external_id"],publication_date=e["publication_date"],
                      title=e["title"],project_name=e.get("project_name"),power_mw=e.get("power_mw"),
                      promoter=e.get("promoter"),province=e.get("province"),url=e["url"],
                      flags=";".join(issues(e))) for e in scanned]
    with (target/"candidates.csv").open("w",encoding="utf-8-sig",newline="") as f:
        columns=["source_code","external_id","publication_date","title","project_name",
                 "power_mw","promoter","province","url","flags"]
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(flags_rows)
    cards="".join("<tr>"+"".join("<td>"+html.escape(str(r.get(k) or ""))+"</td>" for k in
        ("publication_date","title","project_name","power_mw","promoter","province","flags"))
        +"<td><a href='"+html.escape(r["url"],quote=True)+"'>Fonte ufficiale</a></td></tr>" for r in flags_rows)
    (target/"index.html").write_text("<!doctype html><html lang='it'><meta charset='utf-8'><title>Backfill storico "+html.escape(source)+"</title><style>body{font:14px system-ui;margin:2rem}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #ccc;text-align:left}td{max-width:300px;overflow-wrap:anywhere}</style><h1>"+html.escape(source)+" — "+start.isoformat()+" / "+end.isoformat()+"</h1><p>Esito: "+outcome["status"]+". Dati acquisiti, non ancora riconciliati nel database progetti; MW per evento non sommabili come MW unici.</p><table><tr>"+''.join("<th>"+x+"</th>" for x in ("Data","Atto","Progetto","MW","Proponente","Provincia","Qualità","Fonte"))+"</tr>"+cards+"</table></html>",encoding="utf-8")
    print("HISTORIC_BATCH_AUDIT",json.dumps({k:v for k,v in outcome.items() if k not in ("days","geographic_observations_not_unique_projects")},ensure_ascii=False),flush=True)
    return outcome


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",action="store_true")
    parser.add_argument("--source")
    parser.add_argument("--from-date")
    parser.add_argument("--until")
    parser.add_argument("--plan-start",default=NATIONAL_START.isoformat())
    parser.add_argument("--plan-end",default="2026-10-11")
    parser.add_argument("--output",default="reports/national_historical_backfill")
    args=parser.parse_args(argv)
    root=Path(args.output)
    if args.plan:
        plan=build_plan(start=date.fromisoformat(args.plan_start),end=date.fromisoformat(args.plan_end))
        persist_json(root/"plan.json",plan)
        print("NATIONAL_HISTORICAL_PLAN",json.dumps({k:v for k,v in plan.items() if k not in ("months","tasks","source_gaps")}),flush=True)
        return
    if not args.source or not args.from_date or not args.until:
        parser.error("Scan requires --source, --from-date, --until")
    report=scan_source(source=args.source,start=date.fromisoformat(args.from_date),
                       end=date.fromisoformat(args.until),out=root)
    if not report["complete"]:
        raise SystemExit("Incomplete historical source batch; consult audit.json and do not promote")


if __name__=="__main__":main()
