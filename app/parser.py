from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, asdict

from app.identifiers import extract_identifier, valid_expediente
from app.geo import find_province
from app.lifecycle import classify_event, commercial_stage

MW_RE=re.compile(r"(?<!\d)(\d{1,4}(?:[\.,]\d{1,6})?)\s*(?:MWp|MWac|MWn|MW)\b",re.I)
KW_RE=re.compile(r"(?<!\d)(\d{1,7}(?:[\.,]\d{1,3})?)\s*kW\b",re.I)
BOE_ID_RE=re.compile(r"BOE-[AB]-\d{4}-\d+",re.I)
QUOTED_RE=re.compile(r"[«“\"]([^»”\"]{3,120})[»”\"]")
EXPEDIENTE_RE=re.compile(
    r"(?:expedientes?|expdte\.?|expte\.?|exp\.|c[oó]digo)"
    r"(?:\s*(?:n[ºo°]\.?|n[uú]mero))?\s*[:\-]?\s*"
    r"(?:SIAGGE\s+)?([A-Z0-9][A-Z0-9._/\-]{2,60})",
    re.I,
)
PROJECT_PATTERNS=[
    re.compile(r"parque\s+e[oó]lico\s+(?:denominado\s+)?[«“\"]?(.{3,120}?)[»”\"]?\s+de\s+\d+(?:[.,]\d+)?\s*(?:MW|MWn|MWp)\b",re.I),
    # Explicit umbrella hybrid names precede component descriptions.
    re.compile(r"h[ií]brid[oa]\s+[«“\"]([^»”\"]{2,120})[»”\"]",re.I),
    re.compile(
        r"(?:m[oó]dulo|planta|sistema)\s+de\s+almacenamiento"
        r"(?:\s+de\s+energ[ií]a)?(?:\s+electroqu[ií]mico)?"
        r"(?:\s+por\s+bater[ií]as?)?(?:\s+h[ií]brid[oa])?(?:\s+de\s+la\s+instalaci[oó]n\s+h[ií]brida)?\s+"
        r"[«“\"]([^»”\"]{2,120})[»”\"]", re.I,
    ),
    re.compile(
        r"(?:m[oó]dulo|planta|sistema)\s+de\s+almacenamiento"
        r"(?:\s+de\s+energ[ií]a)?(?:\s+electroqu[ií]mico)?"
        r"(?:\s+por\s+bater[ií]as?)?(?:\s+h[ií]brid[oa])?(?:\s+de\s+la\s+instalaci[oó]n\s+h[ií]brida)?\s+"
        r"(.{3,120}?)\s*,?\s+de\s+\d{1,4}(?:[\.,]\d+)?\s*(?:MWp|MWac|MWn|MW)\b", re.I,
    ),
    re.compile(r"proyecto\s+de\s+hibridaci[oó]n\s+[«“\"]([^»”\"]{3,120})[»”\"]",re.I),
    re.compile(r"fotovoltaic[ao]\s+denominad[oa]\s+[«“\"]([^»”\"]{3,120})[»”\"]",re.I),
    re.compile(r"parque\s+(?:solar\s+)?fotovoltaico\s+(?:denominado\s+)?[«“\"]?([^,»”\"]{3,120})",re.I),
    re.compile(
        r"(?:instalaci[oó]n|planta)\s+(?:solar\s+)?fotovoltaica\s+"
        r"de\s+\d{1,7}(?:[\.,]\d+)?\s*(?:kW|MWp|MWac|MWn|MW)\s+"
        r"denominada\s+[«“\"]?(.{3,120}?)(?=[»”\"]?(?:\s+que\b|\s+en\b|,|\.|$))", re.I,
    ),
    re.compile(
        r"(?:instalaci[oó]n|planta)\s+(?:solar\s+)?fotovoltaica\s+"
        r"(?:(?:denominada|denominado|de)\s+)?[«\"]?(.{3,120}?)[»\"]?,?\s+"
        r"de\s+\d{1,4}(?:[\.,]\d+)?\s*(?:MWp|MWac|MWn|MW)\b", re.I,
    ),
    re.compile(r"(?:instalaci[oó]n|planta)\s+(?:solar\s+)?fotovoltaica\s+(?:denominada\s+)?[«“\"]?([^,»”\"\.]{3,140})",re.I),
    re.compile(r"parque\s+e[oó]lico\s+(?:denominado\s+)?[«“\"]?([^,»”\"\.]{3,140})",re.I),
    re.compile(r"instalaci[oó]n\s+de\s+producci[oó]n\s+de\s+energ[ií]a\s+el[eé]ctrica\s+[«“\"]?([^,»”\"\.]{3,140})",re.I),
    re.compile(r"m[oó]dulo\s+de\s+almacenamiento\s+de\s+la\s+instalaci[oó]n\s+h[ií]brida\s+[«“\"]?([^,»”\"\.]{3,140})",re.I),
    re.compile(r"(?:m[oó]dulo|sistema)\s+de\s+almacenamiento\s+(?:denominado\s+)?[«“\"]?([^,»”\"\.]{3,140})",re.I),
]

REGIONAL_SOURCE_SCOPE={
    "BOA":("Aragón",{"Huesca","Teruel","Zaragoza"}),
    "BOCYL":("Castilla y León",{"Ávila","Burgos","León","Palencia","Salamanca","Segovia","Soria","Valladolid","Zamora"}),
    "BOJA":("Andalucía",{"Almería","Cádiz","Córdoba","Granada","Huelva","Jaén","Málaga","Sevilla"}),
    "DOCM":("Castilla-La Mancha",{"Albacete","Ciudad Real","Cuenca","Guadalajara","Toledo"}),
    "DOE":("Extremadura",{"Badajoz","Cáceres"}),
    "BORM":("Murcia",{"Murcia"}),
}

PROMOTER_PATTERNS=[
    re.compile(
        r"cuya\s+promotor[ae]\s+es\s+(?:la\s+)?(?:mercantil\s+)?"
        r"[«\"]?(.{2,140}?)[»\"]?(?=,\s+(?:e\s+)?infraestructura|\.\s*(?:Expte|Expediente)|;|\n|$)",re.I,
    ),
    re.compile(r"empresa\s+beneficiaria\s*:\s*(.{2,140}?)(?=\s+(?:Direcci[oó]n|Domicilio|NIF|CIF)\s*:|;|\n|$)",re.I),
    re.compile(r"(?:de\s+la\s+empresa|empresa)\s+[«\"]?(.{2,140}?)[»\"]?(?=,?\s+as[ií]\s+como|\s*\.?\s*\(\s*Expediente|\s*\.?\s*Expediente|;|\n|$)",re.I),
    re.compile(r"(?:promovid[ao]|formulad[ao])\s+por\s+(?:la\s+)?(?:(?:mercantil|sociedad|entidad)\s+)?[«\"]([^»\"]{2,140})[»\"]",re.I),
    re.compile(r"(?:promovid[ao]|formulad[ao])\s+por\s+(?:la\s+)?(?:(?:mercantil|sociedad|entidad)\s+)?(.{2,140}?)(?=\s*\(\s*expediente|,\s*con\s+NIF|;|\n|$)",re.I),
    re.compile(r"cuyo\s+peticionario\s+es\s+(?:la\s+)?mercantil\s+(.{2,140}?)(?=,\s*con\s+NIF|;|\n|$)",re.I),
    re.compile(r"(?:peticionario|titular(?:\s+de\s+la\s+solicitud)?)\s*:\s*(.{2,140}?)(?=\s+(?:Domicilio|NIF|CIF)\s*:|;|\n|$)",re.I),
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
    promoter:str|None
    expediente:str|None
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
    has_pv=any(k in t for k in ("fotovolta","solar pv")) or bool(re.search(r"\b(?:psfv|pfv|fv)\b",t))
    has_wind=any(k in t for k in ("eolic","aerogenerador"))
    has_storage=bool(re.search(r"\bbaterias?\b|\bbess\b",t)) or any(k in t for k in (
        "modulo de almacenamiento","sistema de almacenamiento",
        "almacenamiento de energia","almacenamiento energet","almacenamiento electr"
    ))
    has_hybrid=("hibrid" in t and any((has_pv,has_wind,has_storage))) or sum((has_pv,has_wind,has_storage))>=2
    if has_hybrid:return "HYBRID"
    if has_pv:return "PV"
    if has_wind:return "WIND"
    if has_storage:return "BESS"
    return None

def _parse_spanish_number(raw:str)->float:
    return float(raw.replace(".","").replace(",", ".")) if "," in raw else float(raw)

def extract_power_mw(text:str)->float|None:
    values=[]
    for m in MW_RE.finditer(text or ""):
        try:
            values.append(_parse_spanish_number(m.group(1)))
        except ValueError:
            pass
    if values:
        return values[0]
    for m in KW_RE.finditer(text or ""):
        try:
            return _parse_spanish_number(m.group(1))/1000.0
        except ValueError:
            pass
    return None

def _clean_project_name(value:str)->str:
    value=value.strip(" '“”«»")
    cuts=[
        r"\s+y\s+las?\s+infraestructuras?\b",
        r"\s+y\s+su\s+infraestructura\b",
        r"\s+de\s+\d{1,4}(?:[\.,]\d+)?\s*(?:MWp|MWac|MWn|MW)\b",
        r"\s+ubicad[ao]\b",
        r"\s+situad[ao]\b",
    ]
    for pat in cuts:
        value=re.split(pat,value,maxsplit=1,flags=re.I)[0]
    return value.strip(" ,.;:-")

SUSPICIOUS_PROJECT_NAME_RE=re.compile(
    r"^(?:bolet[ií]n oficial|existente\b|por bater[ií]as\b|estar[aá] sometida\b|"
    r"a instancia de\b|de autoconsumo\b|fase\s+\d|y\s+\d|\(csfv\)$)", re.I,
)

def _acceptable_project_name(value:str)->bool:
    value=(value or "").strip()
    return 3<=len(value)<=120 and not SUSPICIOUS_PROJECT_NAME_RE.search(value)

def extract_project_name(text:str)->str|None:
    for p in PROJECT_PATTERNS:
        m=p.search(text or "")
        if m:
            value=_clean_project_name(m.group(1))
            if _acceptable_project_name(value):return value
    for m in QUOTED_RE.finditer(text or ""):
        value=_clean_project_name(m.group(1));low=normalize_text(value)
        if _acceptable_project_name(value) and (any(k in low for k in ("fotovolta","eolic","solar","hibrid","bess")) or len(value.split())<=8):
            return value
    return None

def extract_expediente(text:str, *, body:bool=False)->str|None:
    return extract_identifier(text, body=body)

def extract_promoter(text:str)->str|None:
    for p in PROMOTER_PATTERNS:
        m=p.search(text or "")
        if m:
            value=" ".join(m.group(1).split()).strip(" «»\".,;")
            if 2<=len(value)<=140:return value
    return None

def build_project_key(name,technology,province,external_id,expediente=None)->str:
    if valid_expediente(expediente):base="expediente|"+normalize_text(expediente)
    elif name:base="|".join([normalize_text(name),technology or "UNK",normalize_text(province or "")])
    else:base="external|"+external_id
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]

def parse_event(*,source_code,external_id,publication_date,title,url,raw_text)->ParsedEvent:
    technology=detect_technology(title) or detect_technology(raw_text)
    power_mw=extract_power_mw(title)
    if power_mw is None:power_mw=extract_power_mw(raw_text)
    project_name=extract_project_name(title) or extract_project_name(raw_text)
    promoter=extract_promoter(title) or extract_promoter(raw_text)
    expediente=extract_expediente(title) or extract_expediente(raw_text,body=True)
    province,ccaa=find_province(title)
    if not province:province,ccaa=find_province(raw_text)
    scope=REGIONAL_SOURCE_SCOPE.get((source_code or "").upper())
    if scope:
        scope_ccaa,allowed_provinces=scope
        if province not in allowed_provinces:province=None
        if province is None and len(allowed_provinces)==1:province=next(iter(allowed_provinces))
        ccaa=scope_ccaa
    event_type=classify_event(title)
    if event_type=="OTHER":
        raw_event=classify_event((raw_text or "")[:4000])
        if raw_event not in {"DENIED","WITHDRAWN"}:event_type=raw_event
    stage=commercial_stage(event_type)
    return ParsedEvent(
        source_code=source_code,external_id=external_id,publication_date=publication_date,
        title=title.strip(),url=url,raw_text=raw_text.strip(),technology=technology,
        power_mw=power_mw,project_name=project_name,promoter=promoter,expediente=expediente,
        province=province,ccaa=ccaa,event_type=event_type,commercial_stage=stage,
        project_key=build_project_key(project_name,technology,province,external_id,expediente)
    )
