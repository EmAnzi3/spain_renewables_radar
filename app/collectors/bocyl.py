from __future__ import annotations

import hashlib
import re
from datetime import date
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET

from app.parser import parse_event

API="https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/catalog/datasets/bocyl/records"
RELEVANT=re.compile(r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|almacenamiento|bater[ií]a|hibridaci[oó]n|aerogenerador",re.I)
EXCLUDE=re.compile(r"contrataci[oó]n|licitaci[oó]n|adjudicaci[oó]n|autoconsumo|instalaci[oó]n\s+de\s+paneles\s+fotovoltaicos\s+en\s+(?:edificios|cubiertas)",re.I)
ID_RE=re.compile(r"(BOCYL-D-\d{8}-\d+-\d+)(?![\d-])",re.I)

class BOCYLCollector:
    code="BOCYL"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=(8, timeout)
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent})
        retry=Retry(total=2,connect=2,read=1,status=2,backoff_factor=0.8,
                    status_forcelist=(429,500,502,503,504),allowed_methods=frozenset({"GET"}))
        self.session.mount("https://",HTTPAdapter(max_retries=retry))

    def _get_json(self,url,params=None):
        r=self.session.get(url,params=params,timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _get_text(self,url):
        if not url:
            return None
        if url.startswith("http://"):
            url="https://"+url[len("http://"):]
        r=self.session.get(url,timeout=self.timeout)
        if r.status_code==404:
            return None
        r.raise_for_status()
        declaration=re.search(br'encoding=[\'"]([^\'"]+)',r.content[:150])
        r.encoding=declaration[1].decode('ascii') if declaration else (r.apparent_encoding or "utf-8")
        return r.text

    @staticmethod
    def _external_id(row:dict)->str:
        for key in ("enlace_fichero_xml","enlace_fichero_html","enlace_fichero_pdf"):
            value=str(row.get(key) or "")
            m=ID_RE.search(value)
            if m:
                return m.group(1).upper()
        title=str(row.get("titulo") or "")
        edition=str(row.get("no_edicion") or "")
        digest=hashlib.sha1((str(row.get("fecha_publicacion") or "")+"|"+edition+"|"+title).encode("utf-8")).hexdigest()[:16]
        return f"BOCYL-{digest}"

    def _day_rows(self,day:date):
        where=f"fecha_publicacion=date'{day.isoformat()}'"
        offset=0
        while True:
            payload=self._get_json(API,params={"where":where,"limit":100,"offset":offset})
            if not isinstance(payload,dict) or not isinstance(payload.get("results"),list) or "total_count" not in payload:
                raise RuntimeError("BOCYL index schema invalid, not empty coverage")
            rows=payload["results"]
            if not rows and offset<int(payload["total_count"]):
                raise RuntimeError("BOCYL index pagination truncated")
            for row in rows:
                yield row
            offset += len(rows)
            if not rows or offset >= int(payload.get("total_count") or 0):
                break

    def _detail_text(self,row:dict)->tuple[str,str]:
        errors=[]
        for field in ("enlace_fichero_xml","enlace_fichero_html"):
            url=row.get(field)
            if not url:continue
            try:
                raw=self._get_text(url)
                if not raw:raise RuntimeError("Published BOCYL document missing: "+url)
                if field.endswith("xml"):
                    root=ET.fromstring(raw)
                    if root.tag!="disposicion":raise ValueError("Unexpected BOCYL XML root")
                    text="\n".join(t.strip() for t in root.itertext() if t and t.strip())
                else:
                    soup=BeautifulSoup(raw,"html.parser")
                    for tag in soup.select("script,style,nav,header,footer"):tag.decompose()
                    text=soup.get_text("\n",strip=True)
                    if len(text)<100:raise ValueError("BOCYL HTML document too short")
                return text,(row.get("enlace_fichero_html") or url).replace("http://","https://",1)
            except (requests.RequestException,ValueError,ET.ParseError,RuntimeError) as exc:
                errors.append(f"{field}: {exc}")
        if errors:
            raise RuntimeError("BOCYL published detail unavailable; "+"; ".join(errors))
        # An index-only source without document links is not fabricated full text.
        return str(row.get("titulo") or ""),row.get("enlace_fichero_pdf") or API

    def collect_day(self,day:date):
        out=[]
        for row in self._day_rows(day):
            title=str(row.get("titulo") or "")
            if not RELEVANT.search(title) or EXCLUDE.search(title):
                continue
            detail_text,source_url=self._detail_text(row)
            combined=title+"\n"+detail_text
            if not RELEVANT.search(combined):
                continue
            event=parse_event(
                source_code=self.code,
                external_id=self._external_id(row),
                publication_date=day.isoformat(),
                title=title,
                url=source_url,
                raw_text=detail_text,
            )
            if event.technology:
                out.append(event)
        return out
