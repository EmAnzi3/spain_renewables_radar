from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.geo import PROVINCE_TO_CCAA, find_province
from app.lifecycle import commercial_stage
from app.parser import (
    ParsedEvent,
    build_project_key,
    detect_technology,
    extract_power_mw,
    extract_project_name,
)

SEARCH_URL="https://sede.miteco.gob.es/portal/site/seMITECO/navServicioContenido"
DETAIL_URL=SEARCH_URL

# Official SABIA project types relevant to the radar.
TYPE_CODES={
    "FTV":"PV",
    "EOL":"WIND",
    "EOM":"WIND",
    "HIB":"HYBRID",
    "ALM":"BESS",
}

# Early environmental stages with direct commercial value. FIN FASE POTESTATIVA
# is intentionally excluded: the live archive contains hundreds of old files and
# adds high request cost after the opportunity has already passed consultations.
# Later authorisation milestones remain covered by BOE/regional bulletins.
STATE_CODES={
    "05":"INICIO TELEMATICO",
    "20":"INICIO",
    "30":"CONSULTAS PREVIAS",
    "40":"TRASLADO CONSULTAS",
    "50":"RECEPCION EXPEDIENTE",
}

TYPE_TEXT_TO_TECH={
    "FOTOVOLTAICOS":"PV",
    "PARQUES EOLICOS":"WIND",
    "EOLICOS MARINOS":"WIND",
    "HIBRIDOS ENERGIAS RENOVABLES":"HYBRID",
    "ALMACENAMIENTO DE ENERGIA":"BESS",
}

MULTI_PROVINCE_RE=re.compile(r"\bprovincias?\s+de\b",re.I)


def _norm(value:str)->str:
    value=unicodedata.normalize("NFKD",value or "")
    value="".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+"," ",value).strip().upper()


def _iso_date(value:str|None)->str|None:
    if not value:
        return None
    m=re.search(r"\b(\d{2}/\d{2}/\d{4})\b",value)
    if not m:
        return None
    return datetime.strptime(m.group(1),"%d/%m/%Y").date().isoformat()


def _capture(text:str,pattern:str)->str|None:
    m=re.search(pattern,text,re.I|re.S)
    return " ".join(m.group(1).split()).strip() if m else None


def parse_search_html(html_text:str,source_type:str|None=None)->list[dict]:
    soup=BeautifulSoup(html_text,"html.parser")
    table=soup.find("table",id="tablaResultados")
    if table is None:
        body=" ".join(soup.stripped_strings)
        if "Se ha producido un error" in body:
            raise RuntimeError("SABIA historical search returned application error")
        return []
    rows=[]
    for tr in table.find_all("tr"):
        cells=[" ".join(td.stripped_strings) for td in tr.find_all("td")]
        if len(cells)<3 or not re.fullmatch(r"20\d{6}",cells[0] or ""):
            continue
        rows.append({
            "code":cells[0],
            "title":cells[1],
            "state":cells[2],
            "source_type":source_type,
        })
    return rows


def parse_detail_html(html_text:str)->dict:
    soup=BeautifulSoup(html_text,"html.parser")
    text=" ".join(soup.stripped_strings)

    environmental_code=_capture(
        text,r"Código de Evaluación Ambiental:\s*([^\s]+)\s+Código para el Órgano Sustantivo:"
    )
    substantive_code=_capture(
        text,r"Código para el Órgano Sustantivo:\s*(.*?)\s+Título del proyecto:"
    )
    title=_capture(
        text,r"Título del proyecto:\s*(.*?)\s+Órgano Sustantivo:"
    )
    substantive_body=_capture(
        text,r"Órgano Sustantivo:\s*(.*?)\s+Promotor:"
    )
    promoter=_capture(
        text,r"Promotor:\s*(.*?)\s+(?:NIF|CIF):\s*[A-Z0-9\-]+\s+Tipo de proyecto:"
    )
    if not promoter:
        promoter=_capture(text,r"Promotor:\s*(.*?)\s+Tipo de proyecto:")
        if promoter:
            promoter=re.sub(r"\s+(?:NIF|CIF):\s*[A-Z0-9\-]+\s*$","",promoter,flags=re.I).strip()

    project_type=_capture(
        text,r"Tipo de proyecto:\s*(.*?)\s+Legislación aplicable:"
    )
    ccaa=_capture(
        text,r"Comunidad autónoma:\s*(.*?)\s+Provincia:"
    )
    province=_capture(
        text,r"Provincia:\s*(.*?)\s+Municipio:"
    )
    municipality=_capture(
        text,r"Municipio:\s*(.*?)\s+Página Web:"
    )
    state=_capture(
        text,r"Estado de tramitación:\s*(.*?)\s+Fecha de entrada:"
    )
    entry_date=_capture(text,r"Fecha de entrada:\s*(\d{2}/\d{2}/\d{4})")
    consultation_start=_capture(
        text,r"Fecha inicio de consultas:\s*(\d{2}/\d{2}/\d{4})"
    )
    resolution_date=_capture(
        text,r"Fecha de resolución:\s*(\d{2}/\d{2}/\d{4})"
    )
    resolution_sense=_capture(
        text,r"Sentido de la resolución:\s*(.*?)\s+Documentación"
    )

    if not environmental_code or not title:
        raise ValueError("SABIA project detail missing environmental code or title")

    return {
        "environmental_code":environmental_code,
        "substantive_code":substantive_code or None,
        "title":title,
        "substantive_body":substantive_body or None,
        "promoter":promoter or None,
        "project_type":project_type or None,
        "ccaa":ccaa or None,
        "province":province or None,
        "municipality":municipality or None,
        "state":state or None,
        "entry_date":_iso_date(entry_date),
        "consultation_start":_iso_date(consultation_start),
        "resolution_date":_iso_date(resolution_date),
        "resolution_sense":resolution_sense or None,
        "raw_text":text,
    }


def _technology(detail:dict,source_type:str|None)->str|None:
    official=_norm(detail.get("project_type") or "")
    if official in TYPE_TEXT_TO_TECH:
        return TYPE_TEXT_TO_TECH[official]
    if source_type in TYPE_CODES:
        return TYPE_CODES[source_type]
    return detect_technology(detail.get("title") or "") or detect_technology(detail.get("raw_text") or "")


def _explicit_multi_province(title:str)->bool:
    if not MULTI_PROVINCE_RE.search(title or ""):
        return False
    low=(title or "").casefold()
    hits={p for p in PROVINCE_TO_CCAA if p.casefold() in low}
    return len(hits)>=2


def events_from_detail(detail:dict,source_type:str|None,url:str)->list[ParsedEvent]:
    title=detail["title"]
    tech=_technology(detail,source_type)
    if tech not in {"PV","WIND","BESS","HYBRID"}:
        return []

    power_mw=extract_power_mw(title)
    name=extract_project_name(title)
    promoter=detail.get("promoter")
    expediente=detail.get("substantive_code") or detail["environmental_code"]

    province=(detail.get("province") or "").strip() or None
    ccaa=(detail.get("ccaa") or "").strip() or None
    if _explicit_multi_province(title):
        province=None
    if not province:
        fallback_province,fallback_ccaa=find_province(title)
        if fallback_province and not _explicit_multi_province(title):
            province=fallback_province
        if not ccaa:
            ccaa=fallback_ccaa
    if province and not ccaa:
        ccaa=PROVINCE_TO_CCAA.get(province)

    project_key=build_project_key(
        name,tech,province,detail["environmental_code"],expediente
    )
    common=dict(
        source_code="MITECO_SABIA",
        title=title,
        url=url,
        raw_text=detail.get("raw_text") or title,
        technology=tech,
        power_mw=power_mw,
        project_name=name,
        promoter=promoter,
        expediente=expediente,
        province=province,
        ccaa=ccaa,
        project_key=project_key,
    )

    out=[]
    if detail.get("entry_date"):
        event_type="OTHER"
        out.append(ParsedEvent(
            external_id=f"{detail['environmental_code']}:ENTRY",
            publication_date=detail["entry_date"],
            event_type=event_type,
            commercial_stage=commercial_stage(event_type),
            **common,
        ))
    if detail.get("consultation_start"):
        event_type="PUBLIC_INFO"
        out.append(ParsedEvent(
            external_id=f"{detail['environmental_code']}:CONSULT",
            publication_date=detail["consultation_start"],
            event_type=event_type,
            commercial_stage=commercial_stage(event_type),
            **common,
        ))
    return out


class SABIACollector:
    code="MITECO_SABIA"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=max(timeout,30)
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent})
        retry=Retry(
            total=4,
            connect=3,
            read=3,
            status=4,
            backoff_factor=0.8,
            status_forcelist=(429,500,502,503,504),
            allowed_methods=frozenset({"GET","POST"}),
            raise_on_status=False,
        )
        adapter=HTTPAdapter(max_retries=retry)
        self.session.mount("https://",adapter)
        self.session.mount("http://",adapter)
        self._candidate_rows=None
        self._details={}
        self._events_by_date=None

    def _get_search_form(self):
        r=self.session.get(SEARCH_URL,timeout=self.timeout)
        r.raise_for_status()
        soup=BeautifulSoup(r.text,"html.parser")
        form=soup.find("form")
        if form is None:
            raise RuntimeError("SABIA search form not found")
        payload={}
        for inp in form.find_all("input"):
            name=inp.get("name")
            if name:
                payload[name]=inp.get("value") or ""
        return payload

    def _search(self,base_payload:dict,type_code:str,state_code:str)->list[dict]:
        payload=dict(base_payload)
        payload.update({
            "accion":"proy_resultados",
            "select_comunidades":"",
            "codigo":"",
            "titulo":"",
            "select_estado_tramitacion":state_code,
            "select_tipo":type_code,
            "select_organo_sustantivo":"",
            "select_promotor":"",
        })
        r=self.session.post(SEARCH_URL,data=payload,timeout=max(self.timeout,60))
        r.raise_for_status()
        return parse_search_html(r.text,source_type=type_code)

    def _load_candidates(self)->dict[str,dict]:
        if self._candidate_rows is not None:
            return self._candidate_rows
        base=self._get_search_form()
        rows={}
        for type_code in TYPE_CODES:
            for state_code in STATE_CODES:
                for row in self._search(base,type_code,state_code):
                    current=rows.get(row["code"])
                    if current is None:
                        rows[row["code"]]=row
                    elif not current.get("source_type"):
                        current["source_type"]=type_code
        self._candidate_rows=rows
        return rows

    def _detail(self,code:str)->tuple[dict,str]:
        if code in self._details:
            return self._details[code]
        r=self.session.get(
            DETAIL_URL,
            params={
                "accion":"proy_detalle",
                "codigo_seleccionado":code,
                "id_pagina_cargada":"RESULTADOS",
            },
            timeout=max(self.timeout,60),
        )
        r.raise_for_status()
        detail=parse_detail_html(r.text)
        if detail["environmental_code"]!=code:
            raise RuntimeError(
                f"SABIA detail code mismatch: requested {code}, got {detail['environmental_code']}"
            )
        value=(detail,r.url)
        self._details[code]=value
        return value

    def _build_cache(self):
        if self._events_by_date is not None:
            return
        events_by_date={}
        rows=self._load_candidates()
        for code in sorted(rows,reverse=True):
            detail,url=self._detail(code)
            for event in events_from_detail(detail,rows[code].get("source_type"),url):
                events_by_date.setdefault(event.publication_date,[]).append(event)
        self._events_by_date=events_by_date

    def collect_day(self,day:date):
        self._build_cache()
        return list(self._events_by_date.get(day.isoformat(),[]))
