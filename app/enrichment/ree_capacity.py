from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

CAPACITY_PAGE = "https://www.ree.es/es/clientes/generador/acceso-conexion/conoce-la-capacidad-de-acceso"
DATE_RE = re.compile(r"/(\d{4})_(\d{2})_(\d{2})_GRT_generacion\.csv$", re.I)


@dataclass
class REENodeCapacity:
    snapshot_date: str
    node_name: str
    substation_code: str | None
    ccaa: str | None
    positions_rdt_existing: float | None
    positions_rdt_planned: float | None
    positions_rdd_existing: float | None
    positions_rdd_planned: float | None
    granted_gen_mw: float | None
    granted_storage_mw: float | None
    pending_gen_mw: float | None
    pending_storage_mw: float | None
    margin_gen_mges_mw: float | None
    margin_gen_mpe_mw: float | None
    margin_storage_mges_mw: float | None
    margin_storage_mpe_mw: float | None
    available_gen_rdt_mges_mw: float | None
    available_gen_rdt_mpe_mw: float | None
    available_gen_rdd_mges_mw: float | None
    available_gen_rdd_mpe_mw: float | None
    available_storage_rdt_mges_mw: float | None
    available_storage_rdt_mpe_mw: float | None
    available_storage_rdd_mges_mw: float | None
    available_storage_rdd_mpe_mw: float | None
    source_url: str

    def asdict(self):
        return asdict(self)


def _num(value: str | None) -> float | None:
    text=(value or "").strip()
    if not text or text.upper() in {"N/A","NA","N.D.","ND","-"}:
        return None
    text=text.replace("\xa0","").replace(" ","")
    if "," in text:
        text=text.replace(".","").replace(",",".")
    elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+",text):
        text=text.replace(".","")
    try:
        return float(text)
    except ValueError:
        return None


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


def parse_capacity_csv(content: bytes | str, snapshot_date: str, source_url: str) -> list[REENodeCapacity]:
    if isinstance(content,bytes):
        text=content.decode("utf-8-sig","replace")
    else:
        text=content.lstrip("\ufeff")

    rows=list(csv.reader(io.StringIO(text),delimiter=";"))
    if not rows:
        return []

    header_index=None
    for i,row in enumerate(rows[:12]):
        if row and row[0].strip().startswith("Nombre y tensión del nudo"):
            header_index=i
            break
    if header_index is None:
        raise RuntimeError("REE CSV format drift: primary header not found")

    # REE currently publishes three logical header rows.
    second=rows[header_index+1] if len(rows)>header_index+1 else []
    if len(second) <= 34 or "otorgada GEN" not in _cell(second,26):
        raise RuntimeError("REE CSV format drift: granted-capacity columns not found")
    data_start=header_index+3

    result=[]
    for row in rows[data_start:]:
        node=_cell(row,0)
        if not node:
            continue
        if node.lower().startswith("nota") or node.lower().startswith("fuente"):
            continue
        result.append(REENodeCapacity(
            snapshot_date=snapshot_date,
            node_name=node,
            substation_code=_cell(row,1) or None,
            ccaa=_cell(row,2) or None,
            positions_rdt_existing=_num(_cell(row,3)),
            positions_rdt_planned=_num(_cell(row,4)),
            positions_rdd_existing=_num(_cell(row,5)),
            positions_rdd_planned=_num(_cell(row,6)),
            granted_gen_mw=_num(_cell(row,26)),
            granted_storage_mw=_num(_cell(row,27)),
            pending_gen_mw=_num(_cell(row,33)),
            pending_storage_mw=_num(_cell(row,34)),
            margin_gen_mges_mw=_num(_cell(row,35)),
            margin_gen_mpe_mw=_num(_cell(row,36)),
            margin_storage_mges_mw=_num(_cell(row,37)),
            margin_storage_mpe_mw=_num(_cell(row,38)),
            available_gen_rdt_mges_mw=_num(_cell(row,52)),
            available_gen_rdt_mpe_mw=_num(_cell(row,53)),
            available_gen_rdd_mges_mw=_num(_cell(row,54)),
            available_gen_rdd_mpe_mw=_num(_cell(row,55)),
            available_storage_rdt_mges_mw=_num(_cell(row,56)),
            available_storage_rdt_mpe_mw=_num(_cell(row,57)),
            available_storage_rdd_mges_mw=_num(_cell(row,58)),
            available_storage_rdd_mpe_mw=_num(_cell(row,59)),
            source_url=source_url,
        ))
    return result


def fetch_capacity_snapshot(timeout: int=30, user_agent: str="SpainRenewablesRadar/0.1"):
    session=requests.Session()
    session.headers.update({"User-Agent":user_agent})
    page=session.get(CAPACITY_PAGE,timeout=timeout)
    page.raise_for_status()
    soup=BeautifulSoup(page.text,"html.parser")

    csv_urls=[]
    for a in soup.find_all("a",href=True):
        href=urljoin(CAPACITY_PAGE,a["href"])
        if "GRT_generacion" in href and href.lower().endswith(".csv"):
            csv_urls.append(href)
    if not csv_urls:
        raise RuntimeError("REE capacity CSV link not found")

    source_url=csv_urls[0]
    match=DATE_RE.search(source_url)
    if not match:
        raise RuntimeError("REE capacity snapshot date not found in CSV URL")
    snapshot_date="-".join(match.groups())

    response=session.get(source_url,timeout=timeout)
    response.raise_for_status()
    records=parse_capacity_csv(response.content,snapshot_date,source_url)
    if not records:
        raise RuntimeError("REE capacity CSV returned no node records")
    return snapshot_date,source_url,records


def save_capacity_snapshot(conn, snapshot_date: str, source_url: str, records: list[REENodeCapacity]) -> int:
    sql="""
    INSERT OR REPLACE INTO ree_node_capacity (
      snapshot_date,node_name,substation_code,ccaa,
      positions_rdt_existing,positions_rdt_planned,positions_rdd_existing,positions_rdd_planned,
      granted_gen_mw,granted_storage_mw,pending_gen_mw,pending_storage_mw,
      margin_gen_mges_mw,margin_gen_mpe_mw,margin_storage_mges_mw,margin_storage_mpe_mw,
      available_gen_rdt_mges_mw,available_gen_rdt_mpe_mw,available_gen_rdd_mges_mw,available_gen_rdd_mpe_mw,
      available_storage_rdt_mges_mw,available_storage_rdt_mpe_mw,available_storage_rdd_mges_mw,available_storage_rdd_mpe_mw,
      source_url
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    for item in records:
        d=item.asdict()
        conn.execute(sql,(
            d["snapshot_date"],d["node_name"],d["substation_code"],d["ccaa"],
            d["positions_rdt_existing"],d["positions_rdt_planned"],d["positions_rdd_existing"],d["positions_rdd_planned"],
            d["granted_gen_mw"],d["granted_storage_mw"],d["pending_gen_mw"],d["pending_storage_mw"],
            d["margin_gen_mges_mw"],d["margin_gen_mpe_mw"],d["margin_storage_mges_mw"],d["margin_storage_mpe_mw"],
            d["available_gen_rdt_mges_mw"],d["available_gen_rdt_mpe_mw"],d["available_gen_rdd_mges_mw"],d["available_gen_rdd_mpe_mw"],
            d["available_storage_rdt_mges_mw"],d["available_storage_rdt_mpe_mw"],d["available_storage_rdd_mges_mw"],d["available_storage_rdd_mpe_mw"],
            source_url,
        ))
    conn.commit()
    return len(records)


def write_capacity_exports(records: list[REENodeCapacity], snapshot_date: str, source_url: str, out_dir: str="reports"):
    out=Path(out_dir)
    out.mkdir(parents=True,exist_ok=True)
    fields=list(REENodeCapacity.__dataclass_fields__.keys())

    csv_path=out/"ree_capacity_latest.csv"
    with csv_path.open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        for item in records:
            writer.writerow(item.asdict())

    json_path=out/"ree_capacity_latest.json"
    json_path.write_text(json.dumps({
        "snapshot_date":snapshot_date,
        "source_url":source_url,
        "records":[x.asdict() for x in records],
    },ensure_ascii=False,indent=2),encoding="utf-8")
    return csv_path,json_path
