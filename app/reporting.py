from __future__ import annotations

import csv
import html
import json
from pathlib import Path

def write_changes(events,out_dir="reports/change_reports"):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    csv_path=out/"changes_latest.csv";html_path=out/"changes_latest.html"
    fields=["publication_date","source_code","external_id","technology","power_mw","project_name","province","ccaa","event_type","commercial_stage","url"]
    with csv_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for e in events:
            d=e.asdict();w.writerow({k:d.get(k) for k in fields})
    rows="".join(
        "<tr>"+"".join(f"<td>{html.escape(str(e.asdict().get(k) or ''))}</td>" for k in fields[:-1])+
        f"<td><a href='{html.escape(e.url)}' target='_blank'>fonte</a></td></tr>" for e in events
    )
    html_path.write_text(f"""<!doctype html><html><head><meta charset='utf-8'><title>Spain Radar changes</title>
<style>body{{font-family:Arial,sans-serif;margin:28px;color:#172033}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #ddd;padding:8px;text-align:left}}th{{background:#f3f6fa;position:sticky;top:0}}</style></head><body>
<h1>Spain Renewables Radar — variazioni ultimo run</h1><p>Nuovi eventi rilevati: <b>{len(events)}</b></p>
<table><thead><tr>{''.join(f'<th>{k}</th>' for k in fields)}</tr></thead><tbody>{rows}</tbody></table></body></html>""",encoding="utf-8")
    return csv_path,html_path

def export_dashboard(conn,docs_dir="docs"):
    docs=Path(docs_dir);docs.mkdir(parents=True,exist_ok=True)
    rows=[dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY last_seen DESC,power_mw DESC").fetchall()]
    (docs/"data.json").write_text(json.dumps({"records":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    return rows
