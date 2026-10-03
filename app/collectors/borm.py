from __future__ import annotations

import re
from datetime import date

import requests

from app.parser import parse_event

INDEX_JSON="https://transparencia.carm.es/rest-services/services/restFile/BORMIndice.json"

RELEVANT=re.compile(
    r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|"
    r"almacenamiento|bater[ií]a|hibridaci[oó]n|aerogenerador|repotenciaci[oó]n",
    re.I,
)
EXCLUDE=re.compile(
    r"contrataci[oó]n|licitaci[oó]n|adjudicaci[oó]n|autoconsumo|"
    r"reciclaje|almacenamiento\s+de\s+residuos|veh[ií]culos\s+al\s+final\s+de\s+su\s+vida|"
    r"curso|subvenci[oó]n",
    re.I,
)

# Official open-data schema positions documented by Región de Murcia.
PUBLICACION=0
ID_ANUNCIO=1
ID_OBJETO_DIGITAL_ANUNCIO=2
NUM_PUBLICACION=3
FECHA_PUBLICACION=4
SUMARIO=5
ADMINISTRACION=6
SECCION=7
APARTADO=8
ANUNCIANTE=9
NUM_DISPOSICION=10
YEAR_PUB=11
RANGO=12
FECHA_DISPOSICION=13
YEAR_DISP=14
CATEGORIA=15
NPE=16
URL_HTML=17
URL_PDF=18
PAGINAS=19


class BORMCollector:
    code="BORM"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent,"Accept":"application/json"})
        self._rows_cache=None

    def _rows(self):
        if self._rows_cache is None:
            r=self.session.get(INDEX_JSON,timeout=max(self.timeout,90))
            r.raise_for_status()
            payload=r.json()
            if not isinstance(payload,list):
                raise RuntimeError("BORM open-data index did not return a row list")
            self._rows_cache=payload
        return self._rows_cache

    @staticmethod
    def _date_text(row)->str:
        if not isinstance(row,list) or len(row)<=FECHA_PUBLICACION:
            return ""
        return str(row[FECHA_PUBLICACION] or "")[:10]

    @classmethod
    def event_from_row(cls,row,day:date):
        if not isinstance(row,list) or len(row)<=PAGINAS:
            return None
        if cls._date_text(row)!=day.isoformat():
            return None

        title=str(row[SUMARIO] or "").strip()
        if not title or not RELEVANT.search(title) or EXCLUDE.search(title):
            return None

        npe=str(row[NPE] or "").strip()
        digital_id=str(row[ID_OBJETO_DIGITAL_ANUNCIO] or "").strip()
        publication_id=str(row[ID_ANUNCIO] or "").strip()
        external_id=npe or digital_id or f"BORM-{day.isoformat()}-{publication_id}"

        source_url=str(row[URL_HTML] or "").strip()
        if not source_url:
            source_url=str(row[URL_PDF] or "").strip()
        if not source_url:
            source_url="https://www.borm.es/"

        event=parse_event(
            source_code=cls.code,
            external_id=external_id,
            publication_date=day.isoformat(),
            title=title,
            url=source_url,
            raw_text=title,
        )
        return event if event.technology else None

    def collect_day(self,day:date):
        out=[]
        for row in self._rows():
            if self._date_text(row)!=day.isoformat():
                continue
            event=self.event_from_row(row,day)
            if event:
                out.append(event)
        return out
