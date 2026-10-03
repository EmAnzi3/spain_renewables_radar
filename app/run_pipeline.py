from __future__ import annotations

import argparse
import os
from datetime import date,timedelta

from app.collectors import BOECollector,BOCYLCollector,BOACollector,BOJACollector,DOCMCollector,DOECollector,BORMCollector,BOCMCollector,SABIACollector
from app.dashboard import write_dashboard
from app.db import connect
from app.enrichment import (
    fetch_capacity_snapshot,
    save_capacity_snapshot,
    write_capacity_exports,
    fetch_registry_snapshot,
    save_registry_snapshot,
    exact_project_matches,
    write_registry_exports,
    fetch_ine_municipalities,
    enrich_missing_project_geography,
    refresh_epc_evidence_from_events,
    write_epc_evidence_exports,
)
from app.reporting import export_dashboard,write_changes,write_coverage,write_quality_issues,write_province_view
from app.store import save_event

COLLECTOR_CLASSES={
    "BOE":BOECollector,
    "BOCYL":BOCYLCollector,
    "BOA":BOACollector,
    "BOJA":BOJACollector,
    "DOCM":DOCMCollector,
    "DOE":DOECollector,
    "BORM":BORMCollector,
    "BOCM":BOCMCollector,
    "MITECO_SABIA":SABIACollector,
}

def daterange(start:date,end:date):
    d=start
    while d<=end:
        yield d
        d+=timedelta(days=1)

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=7,help="giorni inclusi fino a oggi")
    p.add_argument("--since",help="YYYY-MM-DD")
    p.add_argument("--until",help="YYYY-MM-DD")
    p.add_argument("--sources",default="BOE,BOCYL,BOA,BOJA,DOCM,DOE,BORM,BOCM",help="sorgenti separate da virgola")
    p.add_argument("--db",default=os.getenv("RADAR_DB","data/spain_renewables.sqlite"))
    p.add_argument("--skip-ree",action="store_true",help="salta lo snapshot REE accesso/connessione")
    p.add_argument("--skip-miteco",action="store_true",help="salta lo snapshot MITECO registro produzione")
    p.add_argument("--strict-coverage",action="store_true",help="termina con errore se una sorgente/giorno fallisce")
    return p.parse_args()

def main():
    args=parse_args()
    today=date.today()
    end=date.fromisoformat(args.until) if args.until else today
    start=date.fromisoformat(args.since) if args.since else end-timedelta(days=max(args.days-1,0))

    wanted=[x.strip().upper() for x in args.sources.split(",") if x.strip()]
    unknown=[x for x in wanted if x not in COLLECTOR_CLASSES]
    if unknown:
        raise SystemExit(f"Sorgenti non implementate: {', '.join(unknown)}")

    timeout=int(os.getenv("HTTP_TIMEOUT","30"))
    user_agent=os.getenv("USER_AGENT","SpainRenewablesRadar/0.1")
    collectors=[COLLECTOR_CLASSES[code](timeout=timeout,user_agent=user_agent) for code in wanted]

    conn=connect(args.db)
    new_events=[]
    new_projects=0
    scanned=0
    errors=0
    coverage=[]

    for collector in collectors:
        for day in daterange(start,end):
            print(f"[{collector.code}] {day.isoformat()}")
            row={
                "source_code":collector.code,
                "date":day.isoformat(),
                "status":"OK",
                "candidates":0,
                "inserted":0,
                "new_projects":0,
                "error":"",
            }
            try:
                events=collector.collect_day(day)
                row["candidates"]=len(events)
            except Exception as exc:
                errors+=1
                row["status"]="ERROR"
                row["error"]=str(exc)[:500]
                coverage.append(row)
                print(f"  WARN: {exc}")
                continue

            scanned+=len(events)
            for event in events:
                inserted,new_project=save_event(conn,event)
                if inserted:
                    new_events.append(event)
                    row["inserted"]+=1
                    row["new_projects"]+=int(new_project)
                    new_projects+=int(new_project)
            coverage.append(row)

    missing_geo=conn.execute("SELECT count(*) FROM projects WHERE province IS NULL").fetchone()[0]
    if missing_geo:
        print(f"[INE_MUNICIPALITIES] enriching {missing_geo} projects without province")
        geo_row={
            "source_code":"INE_MUNICIPALITIES",
            "date":end.isoformat(),
            "status":"OK",
            "candidates":0,
            "inserted":0,
            "new_projects":0,
            "error":"",
        }
        try:
            municipalities=fetch_ine_municipalities(timeout=timeout,user_agent=user_agent)
            geo_result=enrich_missing_project_geography(conn,municipalities)
            geo_row["candidates"]=len(municipalities)
            geo_row["inserted"]=geo_result["resolved"]
            print(
                f"  INE geography: resolved={geo_result['resolved']} | "
                f"multi-province={geo_result['multi_province']} | unresolved={geo_result['unresolved']}"
            )
        except Exception as exc:
            geo_row["status"]="WARN"
            geo_row["error"]=str(exc)[:500]
            print(f"  WARN INE_MUNICIPALITIES: {exc}")
        coverage.append(geo_row)

    epc_result=refresh_epc_evidence_from_events(conn)
    epc_rows,_,_=write_epc_evidence_exports(conn)
    print(
        f"[EPC_BOP] evidence={len(epc_rows)} | projects={epc_result['projects_with_evidence']} | "
        f"confirmed={epc_result['confirmed_evidence']} | candidate={epc_result['candidate_evidence']}"
    )

    if not args.skip_ree:
        print("[REE_ACCESS] latest node-capacity snapshot")
        ree_row={
            "source_code":"REE_ACCESS",
            "date":"",
            "status":"OK",
            "candidates":0,
            "inserted":0,
            "new_projects":0,
            "error":"",
        }
        try:
            snapshot_date,source_url,ree_records=fetch_capacity_snapshot(
                timeout=timeout,user_agent=user_agent
            )
            saved=save_capacity_snapshot(conn,snapshot_date,source_url,ree_records)
            write_capacity_exports(ree_records,snapshot_date,source_url)
            ree_row["date"]=snapshot_date
            ree_row["candidates"]=len(ree_records)
            ree_row["inserted"]=saved
            print(f"  REE snapshot {snapshot_date}: {len(ree_records)} nodi")
        except Exception as exc:
            errors+=1
            ree_row["status"]="ERROR"
            ree_row["date"]=end.isoformat()
            ree_row["error"]=str(exc)[:500]
            print(f"  WARN REE_ACCESS: {exc}")
        coverage.append(ree_row)

    if not args.skip_miteco:
        print("[MITECO_RAIPEE] production registry snapshot")
        miteco_row={
            "source_code":"MITECO_RAIPEE",
            "date":"",
            "status":"OK",
            "candidates":0,
            "inserted":0,
            "new_projects":0,
            "error":"",
        }
        try:
            snapshot_date,source_url,miteco_records=fetch_registry_snapshot(
                timeout=max(timeout,240),user_agent=user_agent
            )
            saved=save_registry_snapshot(conn,snapshot_date,source_url,miteco_records)
            matches=exact_project_matches(conn,snapshot_date)
            write_registry_exports(
                miteco_records,snapshot_date,source_url,matches=matches
            )
            miteco_row["date"]=snapshot_date
            miteco_row["candidates"]=len(miteco_records)
            miteco_row["inserted"]=saved
            print(
                f"  MITECO snapshot {snapshot_date}: {len(miteco_records)} impianti | "
                f"exact project matches: {len(matches)}"
            )
        except Exception as exc:
            errors+=1
            miteco_row["status"]="ERROR"
            miteco_row["date"]=end.isoformat()
            miteco_row["error"]=str(exc)[:500]
            print(f"  WARN MITECO_RAIPEE: {exc}")
        coverage.append(miteco_row)

    if new_events:
        print("Nuovi eventi rilevati:")
        for e in new_events:
            mw=f"{e.power_mw:g} MW" if e.power_mw is not None else "MW n.d."
            print(
                f"  + {e.source_code} | {e.publication_date} | {e.technology or '?'} | {mw} | "
                f"{e.project_name or 'nome n.d.'} | {e.province or 'provincia n.d.'} | "
                f"{e.commercial_stage} | {e.external_id}"
            )

    write_changes(new_events)
    write_coverage(coverage)
    quality_issues,_,_=write_quality_issues(conn)
    provinces,_,_=write_province_view(conn)
    rows=export_dashboard(conn)
    write_dashboard()

    q_error=sum(1 for x in quality_issues if x["severity"]=="ERROR")
    q_warn=sum(1 for x in quality_issues if x["severity"]=="WARN")
    q_info=sum(1 for x in quality_issues if x["severity"]=="INFO")
    print(f"Quality issues: ERROR={q_error} | WARN={q_warn} | INFO={q_info}")
    print(f"Eventi rilevanti letti: {scanned}")
    print(
        f"Nuovi eventi: {len(new_events)} | nuovi progetti: {new_projects} | "
        f"progetti totali: {len(rows)} | source/day errori: {errors}"
    )
    print("Report: reports/change_reports/changes_latest.html")
    print("Coverage: reports/coverage_latest.html")
    print("Quality: reports/quality_issues_latest.html")
    print("EPC/BoP: reports/epc_bop_evidence_latest.html")
    print(f"Province view: reports/province_view_latest.html ({len(provinces)} province)")
    if not args.skip_ree:
        print("REE: reports/ree_capacity_latest.csv")
    if not args.skip_miteco:
        print("MITECO: reports/miteco_registry_latest.csv")
        print("MITECO exact matches: reports/miteco_exact_matches_latest.csv")
    print("Dashboard: docs/index.html")
    if args.strict_coverage and errors:
        raise SystemExit(f"Coverage gate failed: {errors} source/day errors")

if __name__=="__main__":
    main()
