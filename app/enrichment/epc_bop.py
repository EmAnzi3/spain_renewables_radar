from __future__ import annotations

import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path

STATUS_RANK={"EPC_UNKNOWN":0,"EPC_CANDIDATE":1,"EPC_CONFIRMED":2}

LEGAL_SUFFIX=(
    r"(?:S\.?\s*L\.?(?:\s*U\.?)?|S\.?\s*A\.?(?:\s*U\.?)?|"
    r"SLU|SAU|SL|SA|GmbH|Ltd\.?|Limited|Inc\.?|S\.p\.A\.|AG)"
)
COMPANY=(
    r"([A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9&.,'()\- ]{1,140}?"
    r"\b"+LEGAL_SUFFIX+r")"
)

CONFIRMED_PATTERNS=[
    ("EPC",re.compile(r"(?:contratista|empresa)\s+EPC\s*[:\-]?\s*"+COMPANY,re.I)),
    ("EPC",re.compile(r"contrato\s+EPC.{0,120}?(?:adjudicad[oa]|suscrit[oa]|otorgad[oa])\s+(?:a|con)\s+(?:la\s+)?"+COMPANY,re.I|re.S)),
    ("EPC",re.compile(r"(?:adjudica(?:do)?|ha\s+adjudicado).{0,120}?contrato\s+EPC\s+(?:a\s+)?"+COMPANY,re.I|re.S)),
    ("EPC",re.compile(r"EPC\s+contractor\s*[:\-]?\s*"+COMPANY,re.I)),
    ("BOP",re.compile(r"(?:contratista|contractor)\s+(?:BoP|balance\s+of\s+plant)\s*[:\-]?\s*"+COMPANY,re.I)),
    ("BOP",re.compile(r"contrato\s+(?:BoP|balance\s+of\s+plant).{0,120}?(?:adjudicad[oa]|suscrit[oa]|otorgad[oa])\s+(?:a|con)\s+(?:la\s+)?"+COMPANY,re.I|re.S)),
]

CANDIDATE_PATTERNS=[
    ("CONSTRUCTION",re.compile(r"(?:empresa\s+constructora|contratista\s+principal|contratista\s+de\s+(?:las\s+)?obras)\s*[:\-]?\s*"+COMPANY,re.I)),
    ("CONSTRUCTION",re.compile(r"empresa\s+encargada\s+de\s+(?:la\s+)?construcci[oó]n\s*[:\-]?\s*"+COMPANY,re.I)),
]


@dataclass(frozen=True)
class EPCEvidence:
    contractor_name:str
    role:str
    status:str
    evidence_text:str


def _clean_company(value:str)->str:
    return " ".join((value or "").split()).strip(" ,;:-")


def extract_epc_evidence(text:str)->list[EPCEvidence]:
    value=text or ""
    found={}
    for status,patterns in (
        ("EPC_CONFIRMED",CONFIRMED_PATTERNS),
        ("EPC_CANDIDATE",CANDIDATE_PATTERNS),
    ):
        for role,pattern in patterns:
            for match in pattern.finditer(value):
                company=_clean_company(match.group(1))
                if not company:
                    continue
                key=(company.casefold(),role,status)
                found[key]=EPCEvidence(
                    contractor_name=company,
                    role=role,
                    status=status,
                    evidence_text=" ".join(match.group(0).split())[:500],
                )
    return sorted(found.values(),key=lambda x:(-STATUS_RANK[x.status],x.contractor_name.casefold(),x.role))


def refresh_epc_evidence_from_events(conn):
    inserted=0
    projects=set()
    confirmed=0
    candidate=0
    rows=conn.execute(
        """SELECT e.project_key,e.source_code,e.publication_date,e.url,e.title,e.raw_text
           FROM events e ORDER BY e.publication_date,e.id"""
    ).fetchall()
    for row in rows:
        text=f"{row['title'] or ''}\n{row['raw_text'] or ''}"
        for ev in extract_epc_evidence(text):
            cur=conn.execute(
                """INSERT OR IGNORE INTO project_epc_evidence
                   (project_key,contractor_name,role,status,source_code,source_url,publication_date,evidence_text)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    row["project_key"],ev.contractor_name,ev.role,ev.status,
                    row["source_code"],row["url"],row["publication_date"],ev.evidence_text,
                ),
            )
            if cur.rowcount:
                inserted+=1
                projects.add(row["project_key"])
                if ev.status=="EPC_CONFIRMED":
                    confirmed+=1
                elif ev.status=="EPC_CANDIDATE":
                    candidate+=1
    conn.commit()
    return {
        "inserted":inserted,
        "projects_with_evidence":len(projects),
        "confirmed_evidence":confirmed,
        "candidate_evidence":candidate,
    }


def project_epc_summary(conn,project_key:str)->dict:
    rows=[dict(r) for r in conn.execute(
        """SELECT contractor_name,role,status,source_url,publication_date
           FROM project_epc_evidence
           WHERE project_key=?
           ORDER BY CASE status WHEN 'EPC_CONFIRMED' THEN 2 WHEN 'EPC_CANDIDATE' THEN 1 ELSE 0 END DESC,
                    publication_date DESC,contractor_name""",
        (project_key,),
    ).fetchall()]
    if not rows:
        return {"status":"EPC_UNKNOWN","contractors":[],"roles":[],"evidence_count":0,"source_urls":[]}
    best=max((r["status"] for r in rows),key=lambda x:STATUS_RANK.get(x,0))
    selected=[r for r in rows if r["status"]==best]
    return {
        "status":best,
        "contractors":sorted({r["contractor_name"] for r in selected}),
        "roles":sorted({r["role"] for r in selected}),
        "evidence_count":len(rows),
        "source_urls":list(dict.fromkeys(r["source_url"] for r in selected if r.get("source_url"))),
    }


def write_epc_evidence_exports(conn,out_dir="reports"):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    csv_path=out/"epc_bop_evidence_latest.csv"
    html_path=out/"epc_bop_evidence_latest.html"
    rows=[dict(r) for r in conn.execute(
        """SELECT p.project_name,p.technology,p.power_mw,p.province,
                  e.contractor_name,e.role,e.status,e.source_code,e.publication_date,
                  e.source_url,e.evidence_text
           FROM project_epc_evidence e
           JOIN projects p ON p.project_key=e.project_key
           ORDER BY CASE e.status WHEN 'EPC_CONFIRMED' THEN 0 ELSE 1 END,
                    e.publication_date DESC,p.project_name"""
    ).fetchall()]
    fields=["project_name","technology","power_mw","province","contractor_name","role",
            "status","source_code","publication_date","source_url","evidence_text"]
    with csv_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    body="".join(
        "<tr>"+"".join(
            (f"<td><a href='{html.escape(str(row.get(k) or ''))}' target='_blank'>fonte</a></td>"
             if k=="source_url" and row.get(k)
             else f"<td>{html.escape(str(row.get(k) or ''))}</td>")
            for k in fields
        )+"</tr>" for row in rows
    )
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>EPC / BoP evidence</title>"
        "<style>body{font-family:Arial,sans-serif;margin:28px;color:#172033}"
        "table{border-collapse:collapse;width:100%;font-size:13px}"
        "th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}"
        "th{background:#f3f6fa;position:sticky;top:0}</style></head><body>"
        "<h1>Spain Renewables Radar — EPC / BoP evidence</h1>"
        "<p>Solo evidenze esplicite; developer/promotore non viene mai assunto come EPC.</p>"
        f"<p>Evidenze: <b>{len(rows)}</b></p>"
        "<table><thead><tr>"+''.join(f"<th>{k}</th>" for k in fields)+"</tr></thead>"
        "<tbody>"+body+"</tbody></table></body></html>",
        encoding="utf-8",
    )
    return rows,csv_path,html_path
