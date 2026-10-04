from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from app.scoring import score_project
from app.enrichment.epc_bop import project_epc_summary

def write_changes(events,out_dir="reports/change_reports"):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    csv_path=out/"changes_latest.csv";html_path=out/"changes_latest.html"
    fields=["publication_date","event_date","date_basis","source_code","external_id","technology","power_mw","project_name","promoter","expediente","province","ccaa","event_type","commercial_stage","url"]
    records=[]
    for event in events:
        row=event.asdict();row['event_date']=event.publication_date
        row['date_basis']='SOURCE_PUBLICATION'
        if event.source_code=='MITECO_SABIA':
            row['publication_date']=None
            row['date_basis']='ENTRY_DATE' if ':ENTRY' in event.external_id else 'CONSULTATION_START'
        records.append(row)
    with csv_path.open("w",newline="",encoding="utf-8-sig") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        writer.writerows({k:row.get(k) for k in fields} for row in records)
    body="".join("<tr>"+"".join(f"<td>{html.escape(str(row.get(k) if row.get(k) is not None else ''))}</td>" for k in fields[:-1])+
                 f"<td><a href='{html.escape(row['url'])}' target='_blank' rel='noopener'>fonte</a></td></tr>" for row in records)
    html_path.write_text("<!doctype html><html lang='it'><head><meta charset='utf-8'><title>Spain Radar changes</title>"
        "<style>body{font-family:Arial;margin:28px;color:#172033}table{border-collapse:collapse;width:100%;font-size:13px}"
        "th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f6fa}</style></head><body>"
        "<h1>Spain Renewables Radar — variazioni ultimo run</h1>"
        f"<p>Nuovi eventi: <b>{len(events)}</b>. SABIA: data amministrativa distinta dalla pubblicazione web, non disponibile.</p>"
        "<table><thead><tr>"+''.join(f'<th>{k}</th>' for k in fields)+"</tr></thead><tbody>"+body+"</tbody></table></body></html>",encoding='utf-8')
    return csv_path,html_path

def build_commercial_rows(conn):
    projects=[dict(r) for r in conn.execute("SELECT * FROM projects").fetchall()]
    ree_ccaas={r["ccaa"] for r in conn.execute(
        "SELECT DISTINCT ccaa FROM ree_node_capacity WHERE ccaa IS NOT NULL"
    ).fetchall()}
    geo_rows={r["project_key"]:dict(r) for r in conn.execute(
        "SELECT project_key,municipalities_json,provinces_json,status FROM project_geo_enrichment"
    ).fetchall()}
    meta_by_key={}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_source_metadata'").fetchone():
        for meta in conn.execute("SELECT m.* FROM event_source_metadata m JOIN events e USING(source_code,external_id) ORDER BY e.publication_date,e.id"):
            meta_by_key[meta['project_key']]=dict(meta)
    rows=[]
    for project in projects:
        event_types={r["event_type"] for r in conn.execute(
            "SELECT event_type FROM events WHERE project_key=?",(project["project_key"],)
        ).fetchall()}
        epc=project_epc_summary(conn,project["project_key"])
        scored=score_project(
            project,
            event_types=event_types,
            ree_context_available=bool(project.get("ccaa") and project.get("ccaa") in ree_ccaas),
            epc_status=epc["status"],
        )
        row=dict(project)
        row["commercial_score"]=scored["score"]
        row["commercial_priority"]=scored["priority"]
        row["epc_status"]=scored["epc_status"]
        row["epc_name"]="; ".join(epc["contractors"]) if epc["contractors"] else None
        row["epc_roles"]=epc["roles"]
        row["epc_evidence_count"]=epc["evidence_count"]
        row["score_components"]=scored["components"]
        row["age_days"]=scored["age_days"]
        geo=geo_rows.get(project["project_key"])
        if geo:
            row["municipalities"]=json.loads(geo.get("municipalities_json") or "[]")
            row["provinces"]=json.loads(geo.get("provinces_json") or "[]")
            row["geo_enrichment_status"]=geo.get("status")
        else:
            row["municipalities"]=[]
            row["provinces"]=[project["province"]] if project.get("province") else []
            row["geo_enrichment_status"]=None
        meta=meta_by_key.get(project['project_key'])
        if meta:
            evidence=json.loads(meta['evidence_json'])
            row['source_group_id']=evidence.get('source_group_id')
            row['group_unallocated_power_mw']=evidence['asset'].get('group_power_mw')
            row['name_basis']=evidence['asset'].get('rule')
            row['date_basis']=meta['date_basis'] if project.get('latest_source_code')=='MITECO_SABIA' else 'SOURCE_PUBLICATION'
            row['source_current_state']=meta['source_current_state']
            row['environmental_code']=meta['environmental_code']
        rows.append(row)
    rows.sort(
        key=lambda x:(x["commercial_score"],x.get("last_seen") or "",x.get("power_mw") or -1),
        reverse=True,
    )
    return rows


def build_province_view_from_rows(rows):
    provinces={}
    for row in rows:
        province=row.get("province")
        if len(row.get("provinces",[]))>1:province=None
        if not province:
            continue
        item=provinces.setdefault(province,{
            "province":province,
            "projects":0,
            "known_mw":0.0,
            "projects_without_mw":0,
            "pv":0,
            "wind":0,
            "bess_hybrid":0,
            "early":0,
            "permitting":0,
            "authorized":0,
            "preconstruction":0,
            "blocked":0,
        })
        item["projects"]+=1
        if row.get("power_mw") is None:
            item["projects_without_mw"]+=1
        else:
            item["known_mw"]+=float(row["power_mw"])
        tech=row.get("technology")
        if tech=="PV":
            item["pv"]+=1
        elif tech=="WIND":
            item["wind"]+=1
        elif tech in {"BESS","HYBRID"}:
            item["bess_hybrid"]+=1
        stage=(row.get("commercial_stage") or "").casefold()
        if stage in item:
            item[stage]+=1
    out=list(provinces.values())
    for item in out:
        item["known_mw"]=round(item["known_mw"],6)
    out.sort(key=lambda x:(-x["known_mw"],-x["projects"],x["province"]))
    return out


def write_province_view(conn,out_dir="reports"):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    rows=build_commercial_rows(conn)
    provinces=build_province_view_from_rows(rows)
    fields=[
        "province","projects","known_mw","projects_without_mw","pv","wind","bess_hybrid",
        "early","permitting","authorized","preconstruction","blocked",
    ]
    csv_path=out/"province_view_latest.csv"
    html_path=out/"province_view_latest.html"
    with csv_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(provinces)
    body="".join(
        "<tr>"+"".join(f"<td>{html.escape(str(row.get(k,'')))}</td>" for k in fields)+"</tr>"
        for row in provinces
    )
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Vista provinciale</title>"
        "<style>body{font-family:Arial,sans-serif;margin:28px;color:#172033}"
        "table{border-collapse:collapse;width:100%;font-size:13px}"
        "th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left}"
        "th{background:#f3f6fa;position:sticky;top:0}</style></head><body>"
        "<h1>Spain Renewables Radar — vista provinciale</h1>"
        "<p>I MW riportati sono esclusivamente quelli identificati. I progetti senza MW sono conteggiati a parte.</p>"
        "<table><thead><tr>"+''.join(f"<th>{k}</th>" for k in fields)+"</tr></thead>"
        "<tbody>"+body+"</tbody></table></body></html>",
        encoding="utf-8",
    )
    return provinces,csv_path,html_path


def geography_accounting(rows):
    multi=[r for r in rows if len(r.get('provinces',[]))>1]
    unknown=[r for r in rows if not r.get('province') and len(r.get('provinces',[]))<=1]
    groups={r['source_group_id']:r['group_unallocated_power_mw'] for r in rows
            if r.get('source_group_id') and r.get('group_unallocated_power_mw') is not None}
    return {'multi_province_projects':len(multi),
            'multi_province_known_mw':round(sum(r['power_mw'] for r in multi if r.get('power_mw') is not None),6),
            'multi_province_without_mw':sum(r.get('power_mw') is None for r in multi),
            'unknown_province_projects':len(unknown),
            'unknown_province_known_mw':round(sum(r['power_mw'] for r in unknown if r.get('power_mw') is not None),6),
            'source_group_unallocated_mw':groups,
            'note':'Multi-provincia: potenza di progetto non ripartita né duplicata nelle province. Potenze di gruppo escluse dai totali dei singoli impianti.'}


def export_dashboard(conn,docs_dir="docs"):
    docs=Path(docs_dir);docs.mkdir(parents=True,exist_ok=True)
    rows=build_commercial_rows(conn)
    provinces=build_province_view_from_rows(rows)
    (docs/"data.json").write_text(
        json.dumps({"records":rows,"provinces":provinces,"geography_accounting":geography_accounting(rows)},ensure_ascii=False,indent=2),
        encoding="utf-8",
    )
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

    multi_geo={r['project_key'] for r in conn.execute("SELECT project_key FROM project_geo_enrichment WHERE status='MULTI_PROVINCE'")}
    unnamed_components=set()
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_source_metadata'").fetchone():
        for meta in conn.execute("SELECT project_key,evidence_json FROM event_source_metadata WHERE source_code='MITECO_SABIA'"):
            evidence=json.loads(meta['evidence_json'])
            if evidence.get('asset',{}).get('reason')=='UNNAMED_RENEWABLE_COMPONENT_OF_HYDROGEN_PROJECT':
                unnamed_components.add(meta['project_key'])
    for p in projects:
        name=(p.get("project_name") or "").strip()
        mw=p.get("power_mw")

        if not name:
            latest_title=(p.get("latest_title") or "").strip()
            if p['project_key'] in unnamed_components:
                add(p,"WARN","SOURCE_UNNAMED_RENEWABLE_COMPONENT",
                    "La fonte nomina l'impianto a idrogeno, non la componente rinnovabile: nome FV volutamente vuoto.")
            elif unnamed_multi_project.search(latest_title):
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
            if p['project_key'] in multi_geo:
                add(p,"INFO","MULTI_PROVINCE","La fonte dichiara più province; potenza non ripartita arbitrariamente.")
            else:
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
