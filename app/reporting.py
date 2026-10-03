from __future__ import annotations

import csv
import html
import json
from pathlib import Path

def write_changes(events,out_dir="reports/change_reports"):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    csv_path=out/"changes_latest.csv";html_path=out/"changes_latest.html"
    fields=["publication_date","source_code","external_id","technology","power_mw","project_name","promoter","expediente","province","ccaa","event_type","commercial_stage","url"]
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


def write_coverage(records,out_dir="reports"):
    import csv
    import html
    from pathlib import Path

    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    csv_path=out/"coverage_latest.csv"
    html_path=out/"coverage_latest.html"
    fields=["source_code","date","status","candidates","inserted","new_projects","error"]

    with csv_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        for row in records:
            w.writerow({k:row.get(k,"") for k in fields})

    rows="".join(
        "<tr>"+"".join(f"<td>{html.escape(str(row.get(k,'')))}</td>" for k in fields)+"</tr>"
        for row in records
    )
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Coverage</title>"
        "<style>body{font-family:Arial,sans-serif;margin:28px;color:#172033}"
        "table{border-collapse:collapse;width:100%;font-size:13px}"
        "th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left}"
        "th{background:#f3f6fa}</style></head><body>"
        "<h1>Spain Renewables Radar — coverage ultimo run</h1>"
        f"<p>Source/day checks: <b>{len(records)}</b></p>"
        "<table><thead><tr>"+''.join(f"<th>{k}</th>" for k in fields)+"</tr></thead>"
        "<tbody>"+rows+"</tbody></table></body></html>",
        encoding="utf-8",
    )
    return csv_path,html_path


def write_quality_issues(conn,out_dir="reports"):
    import re

    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    csv_path=out/"quality_issues_latest.csv"
    html_path=out/"quality_issues_latest.html"

    projects=[dict(r) for r in conn.execute(
        """SELECT p.project_key,p.project_name,p.technology,p.power_mw,p.promoter,p.expediente,
                  p.province,p.ccaa,p.commercial_stage,p.last_seen,p.latest_source_code,p.latest_source_url,
                  (
                    SELECT e.title
                    FROM events e
                    WHERE e.project_key=p.project_key
                    ORDER BY e.publication_date DESC,e.id DESC
                    LIMIT 1
                  ) AS latest_title
           FROM projects p ORDER BY p.last_seen DESC,p.project_name"""
    ).fetchall()]

    suspicious_name=re.compile(
        r"^(?:bolet[ií]n oficial|existente\b|por bater[ií]as\b|estar[aá] sometida\b|"
        r"a instancia de\b|de autoconsumo\b|fase\s+\d|y\s+\d|\(csfv\)$)",
        re.I,
    )
    unnamed_multi_project=re.compile(
        r"\b(?:dos|varios|varias|m[uú]ltiples?)\s+"
        r"(?:parques?|plantas?|instalaciones?|m[oó]dulos?)\s+"
        r"(?:solares?\s+)?(?:fotovoltaic[oa]s?|e[oó]lic[oa]s?|de\s+almacenamiento)\b",
        re.I,
    )

    issues=[]
    def add(p,severity,code,detail):
        issues.append({
            "severity":severity,
            "code":code,
            "project_key":p.get("project_key"),
            "project_name":p.get("project_name") or "",
            "technology":p.get("technology") or "",
            "power_mw":p.get("power_mw"),
            "province":p.get("province") or "",
            "ccaa":p.get("ccaa") or "",
            "commercial_stage":p.get("commercial_stage") or "",
            "source_code":p.get("latest_source_code") or "",
            "source_url":p.get("latest_source_url") or "",
            "detail":detail,
        })

    for p in projects:
        name=(p.get("project_name") or "").strip()
        mw=p.get("power_mw")

        if not name:
            latest_title=(p.get("latest_title") or "").strip()
            if unnamed_multi_project.search(latest_title):
                add(
                    p,
                    "WARN",
                    "SOURCE_UNNAMED_MULTI_PROJECT",
                    "La fonte raggruppa più progetti senza una denominazione individuale; il nome resta volutamente vuoto.",
                )
            else:
                add(p,"ERROR","MISSING_PROJECT_NAME","Nome progetto non estratto.")
        elif suspicious_name.search(name):
            add(p,"WARN","SUSPICIOUS_PROJECT_NAME","Nome probabilmente estratto da testo generico e da verificare.")

        if mw is None:
            add(p,"INFO","MISSING_POWER_MW","Potenza non presente o non estratta dalla fonte corrente.")
        elif mw <= 0:
            add(p,"ERROR","INVALID_POWER_MW",f"Potenza non valida: {mw}.")
        elif mw > 1000:
            add(p,"WARN","POWER_OUTLIER_GT_1000_MW",f"Potenza molto elevata ({mw} MW): verificare unità/decimali e progetto.")

        if not p.get("province"):
            add(p,"INFO","MISSING_PROVINCE","Provincia non attribuita con sufficiente confidenza.")
        if not p.get("expediente"):
            add(p,"INFO","MISSING_EXPEDIENTE","Numero expediente non estratto.")

    fields=[
        "severity","code","project_key","project_name","technology","power_mw",
        "province","ccaa","commercial_stage","source_code","source_url","detail",
    ]
    with csv_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(issues)

    order={"ERROR":0,"WARN":1,"INFO":2}
    issues.sort(key=lambda x:(order.get(x["severity"],9),x["code"],x["project_name"]))
    display_fields=[k for k in fields if k!="source_url"]+["source_url"]
    rows="".join(
        "<tr>"+''.join(
            f"<td>{html.escape(str(row.get(k,'')))}</td>" for k in fields if k!="source_url"
        )+(
            f"<td><a href='{html.escape(row['source_url'])}' target='_blank'>fonte</a></td>"
            if row.get("source_url") else "<td></td>"
        )+"</tr>"
        for row in issues
    )
    counts={s:sum(1 for x in issues if x["severity"]==s) for s in ("ERROR","WARN","INFO")}
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Quality issues</title>"
        "<style>body{font-family:Arial,sans-serif;margin:28px;color:#172033}"
        "table{border-collapse:collapse;width:100%;font-size:13px}"
        "th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}"
        "th{background:#f3f6fa;position:sticky;top:0}</style></head><body>"
        "<h1>Spain Renewables Radar — controlli qualità</h1>"
        f"<p>ERROR: <b>{counts['ERROR']}</b> · WARN: <b>{counts['WARN']}</b> · INFO: <b>{counts['INFO']}</b></p>"
        "<p>I flag non modificano automaticamente i dati: servono a individuare record da verificare.</p>"
        "<table><thead><tr>"+''.join(f"<th>{k}</th>" for k in display_fields)+"</tr></thead>"
        "<tbody>"+rows+"</tbody></table></body></html>",
        encoding="utf-8",
    )
    return issues,csv_path,html_path
