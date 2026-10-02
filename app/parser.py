from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, asdict

from app.geo import find_province
from app.lifecycle import classify_event, commercial_stage

MW_RE=re.compile(r"(?<!\d)(\d{1,4}(?:[\.,]\d{1,3})?)\s*(?:MWp|MWac|MW)\b",re.I)
BOE_ID_RE=re.compile(r"BOE-[AB]-\d{4}-\d+",re.I)
QUOTED_RE=re.compile(r"[«\"]([^»\"]{3,120})[»\"]")
PROJECT_PATTERNS=[
    re.compile(r"(?:instalaci[oó]n|planta)\s+(?:solar\s+)?fotovoltaica\s+(?:denominada\s+)?[«\"]?([^,»\"\.]{3,100})",re.I),
    re.compile(r"parque\s+e[oó]lico\s+(?:denominado\s+)?[«\"]?([^,»\"\.]{3,100})",re.I),
    re.compile(r"(?:m[oó]dulo|sistema)\s+de\s+almacenamiento\s+(?:denominado\s+)?[«\"]?([^,»\"\.]{3,100})",re.I),
]

@dataclass
class ParsedEvent:
    source_code:str
    external_id:str
    publication_date:str
    title:str
    url:str
    raw_text:str
    technology:str|None
    power_mw:float|None
    project_name:str|None
    province:str|None
    ccaa:str|None
    event_type:str
    commercial_stage:str
    project_key:str
    def asdict(self): return asdict(self)

def normalize_text(s:str)->str:
    s=unicodedata.normalize("NFKD",s or "")
    s="".join(ch for ch in s if not unicodedata.combining(ch))
    s=re.sub(r"[^a-zA-Z0-9]+"," ",s).strip().lower()
    return re.sub(r"\s+"," ",s)

def detect_technology(text:str)->str|None:
    t=normalize_text(text)
    has_pv=any(k in t for k in ("fotovolta","solar pv"))
    has_wind=any(k in t for k in ("eolic","aerogenerador"))
    has_storage=any(k in t for k in ("almacenamiento","bateria","bess"))
    has_hybrid="hibrid" in t or sum((has_pv,has_wind,has_storage))>=2
    if has_hybrid:return "HYBRID"
    if has_pv:return "PV"
    if has_wind:return "WIND"
    if has_storage:return "BESS"
    return None

def extract_power_mw(text:str)->float|None:
    values=[]
    for m in MW_RE.finditer(text or ""):
        raw=m.group(1)
        try:
            if "," in raw:
                value=float(raw.replace(".","").replace(",","."))
            else:
                value=float(raw)
            values.append(value)
        except ValueError:
            pass
    return max(values) if values else None

def extract_project_name(text:str)->str|None:
    for p in PROJECT_PATTERNS:
        m=p.search(text or "")
        if m:
            value=m.group(1).strip(" '“”«»")
            if 3<=len(value)<=100:return value
    for m in QUOTED_RE.finditer(text or ""):
        value=m.group(1).strip()
        low=normalize_text(value)
        if any(k in low for k in ("fotovolta","eolic","solar","hibrid")) or len(value.split())<=8:
            return value
    return None

def build_project_key(name,technology,province,external_id)->str:
    if name:
        base="|".join([normalize_text(name),technology or "UNK",normalize_text(province or "")])
    else:
        base="external|"+external_id
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]

def parse_event(*,source_code,external_id,publication_date,title,url,raw_text)->ParsedEvent:
    combined=f"{title}\n{raw_text}"
    technology=detect_technology(combined)
    power_mw=extract_power_mw(combined)
    project_name=extract_project_name(combined)
    province,ccaa=find_province(combined)
    event_type=classify_event(combined)
    stage=commercial_stage(event_type)
    return ParsedEvent(
        source_code=source_code,external_id=external_id,publication_date=publication_date,
        title=title.strip(),url=url,raw_text=raw_text.strip(),technology=technology,
        power_mw=power_mw,project_name=project_name,province=province,ccaa=ccaa,
        event_type=event_type,commercial_stage=stage,
        project_key=build_project_key(project_name,technology,province,external_id)
    )
