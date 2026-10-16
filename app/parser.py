from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, asdict

from app.identifiers import extract_identifier, valid_expediente
from app.geo import find_province
from app.lifecycle import classify_event, commercial_stage,dia_outcome

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
    # A named single hybrid installation may be unquoted and followed by
    # a parenthetical technology specification (e.g. "híbrida Araña (eólica...").
    re.compile(r"(?:instalaci[oó]n|planta)\s+h[ií]brid[ao]\s+([A-ZÁÉÍÓÚÜÑ][^(),;:]{2,80}?)\s*\(\s*(?:e[oó]lic[oa]|solar|fotovoltaic[ao])",re.I),
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
    "DOGV":("Comunitat Valenciana",{"Alicante","Alicante/Alacant","Castellón","Castelló","Valencia","València"}),
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

POWER_RE=re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3}){1,2}(?:,\d+)?|\d{1,7}(?:[.,]\d+)?)\s*(MW|kW)(p|ac|n|nom|inst)?\b",re.I)  # never inside cadastral refs (…0000KW)
POWER_LABEL=re.compile(r"potencia\s+(?:total\s+)?(?:instalada|nominal|total|de\s+la\s+(?:instalaci[oó]n|planta))(?:\s+(?:total|instalaci[oó]n|prevista|a\s+instalar))?[^.;]{0,25}$|"
                       r"(?:planta|instalaci[oó]n|parque|central|proyecto|m[oó]dulo de almacenamiento)[^.;]{0,60}?\bde\s*$|"
                       r"potencia\s+total\s+(?:a\s+instalar|del\s+parque)[^.;]{0,25}$",re.I)
POWER_LABEL_AFTER=re.compile(r"^\s*(?:de\s+potencia\s+(?:instalada|nominal)|instalad[oa]s?\b)",re.I)
POWER_PEAK=re.compile(r"potencia\s+(?:de\s+)?pico[^.;]{0,40}$",re.I)
POWER_COMPONENT=re.compile(r"(?:inversor(?:es)?|transformador(?:es)?|cada\s+uno|"
                           r"unitari[ao]|aerogeneradores?\s+(?:de|modelo)|modelo|acceso|evacuaci[oó]n|(?:capacidad|potencia|punto)\s+de\s+conexi[oó]n|l[ií]nea|subestaci[oó]n|"
                           r"inyectada|limit(?:ad[ao]s?|ar[aá])\s+(?:electr[oó]nicamente\s+)?a|existente|reducci[oó]n|concedida)(?:(?!potencia)[^.;]){0,35}$",re.I)
POWER_COMPONENT_AFTER=re.compile(r"^(?:[^.;]{0,40}?\bcada\s+un[oa]\b|\s*(?:por\s+inversor|de\s+potencia\s+(?:unitaria|de\s+acceso)|de\s+capacidad\s+de\s+acceso|"
                                 r"de\s+acceso|\(?\d*\s*motogenerador))",re.I)

def _parse_spanish_number(raw:str)->float:
    """Spanish/Catalan notation: '4.990' and '1.000' are thousands; '4,99' and '0.99' decimals."""
    if "," in raw:return float(raw.replace(".","").replace(",","."))
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+",raw):return float(raw.replace(".",""))
    return float(raw)

def power_candidates(text:str)->list[tuple[int,float,int]]:
    """(score, MW, position). Plant installed/nominal capacity wins over peak DC; inverter,
    turbine-unit, access, injection-limit, evacuation and existing-plant values never win."""
    out=[]
    for m in POWER_RE.finditer(text or ""):
        raw,unit,suffix=m.group(1),m.group(2).lower(),(m.group(3) or "").lower()
        try:value=_parse_spanish_number(raw)
        except ValueError:continue
        if unit=="mw" and "," not in raw and value>=1000 and re.fullmatch(r"\d{1,3}\.\d{3}",raw):
            value=float(raw)  # '1.299 MWp' is 1,299 MW; no single plant act declares >1 GW this way
        mw=value/1000.0 if unit=="kw" else value
        if mw<=0:continue
        before=text[max(0,m.start()-90):m.start()];after=text[m.end():m.end()+45]
        if re.search(r"\d[\s\u0080-\u009f\u2019\u00a0\u202f]$",before):continue  # fragment of a number broken by text extraction ('15\x92785 MW')
        score=0
        if POWER_LABEL.search(before) or POWER_LABEL_AFTER.search(after) or re.search(r"[kM]Wp\s*/\s*$",before) or suffix=="inst":score+=2
        if suffix=="p" or POWER_PEAK.search(before):score-=1
        inverter_total=re.search(r"potencia\s+(?:nominal|total|en)\s+(?:de\s+(?:los\s+)?)?inversores[^.;]{0,12}$",before,re.I)
        grid_only=re.search(r"(?:acceso|evacuaci[oó]n|l[ií]nea|subestaci[oó]n)(?:(?!potencia)[^.;]){0,35}$",before,re.I)
        if inverter_total:score=max(score,2)  # Valencian acts: installed capacity = inverter nominal power
        elif suffix=="p" and grid_only and not POWER_COMPONENT_AFTER.search(after):pass  # a MWp value is a plant, never a line
        elif POWER_COMPONENT.search(before) or POWER_COMPONENT_AFTER.search(after):score-=3
        out.append((score,mw,m.start()))
    return out

def extract_power_mw(text:str)->float|None:
    candidates=[c for c in power_candidates(text) if c[0]>-3]
    if not candidates:return None
    best=max(c[0] for c in candidates)
    return next(c[1] for c in candidates if c[0]==best)

def _clean_project_name(value:str)->str:
    value=value.strip(" '“”«»")
    cuts=[
        r"\s+y\s+las?\s+infraestructuras?\b",
        r"\s+y\s+su\s+infraestructura\b",
        r"\s+y\s+sus\s+infraestructuras\b",
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
    if event_type=="DIA":event_type=dia_outcome(raw_text)
    stage=commercial_stage(event_type)
    return ParsedEvent(
        source_code=source_code,external_id=external_id,publication_date=publication_date,
        title=title.strip(),url=url,raw_text=raw_text.strip(),technology=technology,
        power_mw=power_mw,project_name=project_name,promoter=promoter,expediente=expediente,
        province=province,ccaa=ccaa,event_type=event_type,commercial_stage=stage,
        project_key=build_project_key(project_name,technology,province,external_id,expediente)
    )
