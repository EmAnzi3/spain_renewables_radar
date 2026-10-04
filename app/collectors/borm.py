from __future__ import annotations

import re
import hashlib
import json
import time
from pathlib import Path
from datetime import date, datetime, timezone

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
        self._index_error=None
        self.audit={"source_url":INDEX_JSON,"attempts":[],"complete":False}

    @staticmethod
    def validate_index(payload):
        # Fail closed: malformed official rows must not disappear as empty days.
        if not isinstance(payload,list) or not payload:
            raise ValueError("BORM annual index must be a non-empty row list")
        identities=set()
        dates=[]
        for number,row in enumerate(payload,1):
            if not isinstance(row,list) or len(row)<=PAGINAS:
                raise ValueError(f"BORM malformed row {number}: expected at least 20 columns")
            try:
                parsed=date.fromisoformat(str(row[FECHA_PUBLICACION])[:10])
            except (ValueError,TypeError) as exc:
                raise ValueError(f"BORM invalid publication date at row {number}") from exc
            identity=str(row[NPE] or row[ID_OBJETO_DIGITAL_ANUNCIO] or "")
            if not identity or identity in identities:
                raise ValueError(f"BORM missing or duplicate official identity at row {number}")
            identities.add(identity);dates.append(parsed.isoformat())
        return {"rows":len(payload),"distinct_ids":len(identities),
                "min_publication_date":min(dates),"max_publication_date":max(dates)}

    def _write_audit(self):
        out=Path("reports/borm");out.mkdir(parents=True,exist_ok=True)
        (out/"index_acquisition.json").write_text(json.dumps(self.audit,ensure_ascii=False,indent=2),encoding="utf-8")

    def _rows(self):
        if self._rows_cache is not None:
            return self._rows_cache
        if self._index_error:
            raise RuntimeError(self._index_error)
        # One bounded retry cycle for the annual index, not 30 independent downloads
        # when a temporarily unavailable endpoint responds with HTML and HTTP 200.
        # JSON is decoded from bytes so a valid UTF BOM is not a spurious failure.
        last_error=None
        for attempt in range(1,5):
            item={"attempt":attempt,"requested_at":datetime.now(timezone.utc).isoformat()}
            response=None
            try:
                response=self.session.get(INDEX_JSON,timeout=(8,max(self.timeout,90)))
                item.update(http_status=response.status_code,content_type=response.headers.get("content-type"),
                            response_url=response.url,bytes=len(response.content),
                            sha256=hashlib.sha256(response.content).hexdigest())
                response.raise_for_status()
                payload=json.loads(response.content)
            except (requests.RequestException,json.JSONDecodeError,UnicodeError) as exc:
                last_error=f"{type(exc).__name__}: {exc}"
                item["error"]=last_error[:500]
                if response is not None:
                    item["response_prefix_hex"]=response.content[:80].hex()
                self.audit["attempts"].append(item);self._write_audit()
                retryable=response is None or response.status_code in (200,429,500,502,503,504)
                if attempt<4 and retryable:
                    time.sleep(2**attempt)
                    continue
                break
            try:
                summary=self.validate_index(payload)
            except ValueError as exc:
                last_error=str(exc);item["error"]=last_error
                self.audit["attempts"].append(item);self._write_audit()
                break
            self.audit["attempts"].append(item)
            self.audit.update(summary,complete=True,retrieved_at=datetime.now(timezone.utc).isoformat(),
                              sha256=item["sha256"],recovered_after_retry=attempt>1)
            self._rows_cache=payload
            out=Path("reports/borm");out.mkdir(parents=True,exist_ok=True)
            (out/"index_raw.json").write_bytes(response.content)
            self._write_audit()
            return self._rows_cache
        self._index_error="BORM annual index unavailable after bounded recovery: "+str(last_error)
        self.audit["failure"]=self._index_error;self._write_audit()
        raise RuntimeError(self._index_error)

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
