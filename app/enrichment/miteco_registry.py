from __future__ import annotations

import csv
import io
import re
from datetime import date
from pathlib import Path

import requests

SOURCE_URL="https://energia.serviciosmin.gob.es/Electra/descargarCSVProduccion.aspx"

CCAA_MAP={
    "principado de asturias":"Asturias",
    "asturias":"Asturias",
    "cantabria":"Cantabria",
    "castilla y leon":"Castilla y León",
    "castilla-la mancha":"Castilla-La Mancha",
    "castilla la mancha":"Castilla-La Mancha",
    "cataluna":"Catalunya",
    "cataluña":"Catalunya",
    "comunidad de madrid":"Madrid",
    "madrid":"Madrid",
    "comunidad valenciana":"Comunitat Valenciana",
    "comunitat valenciana":"Comunitat Valenciana",
    "extremadura":"Extremadura",
    "galicia":"Galicia",
    "islas baleares":"Illes Balears",
    "illes balears":"Illes Balears",
    "navarra":"Navarra",
    "pais vasco":"País Vasco",
    "país vasco":"País Vasco",
    "region de murcia":"Murcia",
    "región de murcia":"Murcia",
    "murcia":"Murcia",
    "la rioja":"La Rioja",
    "andalucia":"Andalucía",
    "andalucía":"Andalucía",
    "aragon":"Aragón",
    "aragón":"Aragón",
    "canarias":"Canarias",
    "ceuta":"Ceuta",
    "melilla":"Melilla",
}

def normalize_name(value:str|None)->str:
    s=(value or "").strip().casefold()
    s=re.sub(r"\s+"," ",s)
    return s

def canonical_ccaa(value:str|None)->str|None:
    if not value:
        return None
    key=normalize_name(value)
    return CCAA_MAP.get(key,value.strip())

def fetch_registry_snapshot(timeout:int=240,user_agent:str="SpainRenewablesRadar/0.1"):
    s=requests.Session()
    s.headers.update({"User-Agent":user_agent})
    r=s.get(SOURCE_URL,timeout=(30,timeout))
    r.raise_for_status()

    text=r.content.decode("utf-8-sig")
    reader=csv.DictReader(io.StringIO(text),delimiter=";")
    expected={"AUTOID","INSTALACIONID","REGIMEN","INSTALACION","AUTONOMIA"}
    if not reader.fieldnames or not expected.issubset(set(reader.fieldnames)):
        raise RuntimeError(f"Formato MITECO inatteso: {reader.fieldnames}")

    records=[]
    for row in reader:
        name=(row.get("INSTALACION") or "").strip()
        if not name:
            continue
        records.append({
            "autoid":(row.get("AUTOID") or "").strip() or None,
            "installation_id":(row.get("INSTALACIONID") or "").strip() or None,
            "regime":(row.get("REGIMEN") or "").strip() or None,
            "installation_name":name,
            "normalized_name":normalize_name(name),
            "ccaa":canonical_ccaa(row.get("AUTONOMIA")),
        })

    return date.today().isoformat(),SOURCE_URL,records

def save_registry_snapshot(conn,snapshot_date:str,source_url:str,records:list[dict])->int:
    conn.execute("DELETE FROM miteco_production_registry WHERE snapshot_date=?",(snapshot_date,))
    conn.executemany(
        """INSERT INTO miteco_production_registry
        (snapshot_date,autoid,installation_id,regime,installation_name,normalized_name,ccaa,source_url)
        VALUES (?,?,?,?,?,?,?,?)""",
        [
            (
                snapshot_date,r.get("autoid"),r.get("installation_id"),r.get("regime"),
                r.get("installation_name"),r.get("normalized_name"),r.get("ccaa"),source_url
            )
            for r in records
        ],
    )
    conn.commit()
    return len(records)

def exact_project_matches(conn,snapshot_date:str)->list[dict]:
    registry=conn.execute(
        """SELECT autoid,installation_id,regime,installation_name,normalized_name,ccaa
           FROM miteco_production_registry
           WHERE snapshot_date=?""",
        (snapshot_date,),
    ).fetchall()
    by_name={}
    for row in registry:
        by_name.setdefault(row["normalized_name"],[]).append(row)

    matches=[]
    projects=conn.execute(
        """SELECT project_key,project_name,ccaa,technology,power_mw,commercial_stage
           FROM projects
           WHERE project_name IS NOT NULL
           ORDER BY project_name"""
    ).fetchall()
    for p in projects:
        key=normalize_name(p["project_name"])
        for m in by_name.get(key,[]):
            if p["ccaa"] and m["ccaa"] and p["ccaa"]!=m["ccaa"]:
                continue
            matches.append({
                "project_key":p["project_key"],
                "project_name":p["project_name"],
                "ccaa":p["ccaa"],
                "technology":p["technology"],
                "power_mw":p["power_mw"],
                "commercial_stage":p["commercial_stage"],
                "autoid":m["autoid"],
                "installation_id":m["installation_id"],
                "regime":m["regime"],
                "installation_name":m["installation_name"],
                "registry_ccaa":m["ccaa"],
            })
    return matches

def write_registry_exports(records:list[dict],snapshot_date:str,source_url:str,matches:list[dict]|None=None,out_dir="reports"):
    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)

    registry_path=out/"miteco_registry_latest.csv"
    fields=["autoid","installation_id","regime","installation_name","normalized_name","ccaa"]
    with registry_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        for row in records:
            w.writerow({k:row.get(k) for k in fields})

    meta_path=out/"miteco_registry_latest.txt"
    meta_path.write_text(
        f"snapshot_date={snapshot_date}\nsource_url={source_url}\nrecords={len(records)}\n",
        encoding="utf-8",
    )

    match_path=out/"miteco_exact_matches_latest.csv"
    matches=matches or []
    if matches:
        match_fields=list(matches[0].keys())
    else:
        match_fields=[
            "project_key","project_name","ccaa","technology","power_mw","commercial_stage",
            "autoid","installation_id","regime","installation_name","registry_ccaa",
        ]
    with match_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=match_fields)
        w.writeheader()
        for row in matches:
            w.writerow(row)

    return registry_path,match_path,meta_path
