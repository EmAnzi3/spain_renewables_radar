from __future__ import annotations

import argparse
import os
from datetime import date,timedelta

from app.collectors.boe import BOECollector
from app.dashboard import write_dashboard
from app.db import connect
from app.reporting import export_dashboard,write_changes
from app.store import save_event

def daterange(start:date,end:date):
    d=start
    while d<=end:
        yield d;d+=timedelta(days=1)

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=7,help="giorni inclusi fino a oggi")
    p.add_argument("--since",help="YYYY-MM-DD")
    p.add_argument("--until",help="YYYY-MM-DD")
    p.add_argument("--db",default=os.getenv("RADAR_DB","data/spain_renewables.sqlite"))
    return p.parse_args()

def main():
    args=parse_args();today=date.today()
    end=date.fromisoformat(args.until) if args.until else today
    start=date.fromisoformat(args.since) if args.since else end-timedelta(days=max(args.days-1,0))
    conn=connect(args.db)
    collector=BOECollector(timeout=int(os.getenv("HTTP_TIMEOUT","30")),user_agent=os.getenv("USER_AGENT","SpainRenewablesRadar/0.1"))
    new_events=[];new_projects=0;scanned=0;errors=0
    for day in daterange(start,end):
        print(f"[BOE] {day.isoformat()}")
        try:
            events=collector.collect_day(day)
        except Exception as exc:
            errors+=1;print(f"  WARN: {exc}");continue
        scanned+=len(events)
        for event in events:
            inserted,new_project=save_event(conn,event)
            if inserted:
                new_events.append(event);new_projects+=int(new_project)
    write_changes(new_events)
    rows=export_dashboard(conn);write_dashboard()
    print(f"Eventi rilevanti letti: {scanned}")
    print(f"Nuovi eventi: {len(new_events)} | nuovi progetti: {new_projects} | progetti totali: {len(rows)} | giorni errore: {errors}")
    print("Report: reports/change_reports/changes_latest.html")
    print("Dashboard: docs/index.html")

if __name__=="__main__":main()
