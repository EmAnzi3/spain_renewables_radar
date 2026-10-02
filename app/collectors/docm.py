from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.parser import parse_event

BASE="https://docm.jccm.es/docm/"
SUMMARY_URL=urljoin(BASE,"cambiarBoletin.do")
RELEVANT=re.compile(
    r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|"
    r"almacenamiento|bater[ií]a|hibridaci[oó]n|aerogenerador|repotenciaci[oó]n",
    re.I,
)
EXCLUDE=re.compile(
    r"contrataci[oó]n|licitaci[oó]n|adjudicaci[oó]n|autoconsumo|"
    r"instalaci[oó]n\s+de\s+paneles\s+fotovoltaicos\s+en\s+(?:edificios|cubiertas)",
    re.I,
)
NID_RE=re.compile(r"\[\s*NID\s+(\d{4})/(\d+)\s*\]",re.I)
PDF_RUTA_RE=re.compile(r"^(\d{4}/\d{2}/\d{2})/pdf/(.+)\.pdf$",re.I)

class DOCMCollector:
    code="DOCM"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent})

    def _get(self,url:str,params=None)->str|None:
        r=self.session.get(url,params=params,timeout=self.timeout)
        if r.status_code==404:
            return None
        r.raise_for_status()
        r.encoding=r.apparent_encoding or "utf-8"
        return r.text

    @staticmethod
    def _minimal_entry_node(anchor):
        node=anchor
        for _ in range(6):
            parent=getattr(node,"parent",None)
            if parent is None:
                break
            text=" ".join(parent.stripped_strings)
            if NID_RE.search(text):
                return parent
            node=parent
        return anchor.parent or anchor

    @staticmethod
    def _detail_url_from_pdf(href:str)->str|None:
        absolute=urljoin(BASE,href)
        parsed=urlparse(absolute)
        params=parse_qs(parsed.query)
        ruta=(params.get("ruta") or [None])[0]
        if not ruta:
            return None
        m=PDF_RUTA_RE.match(ruta)
        if not m:
            return None
        html_ruta=f"{m.group(1)}/html/{m.group(2)}.html"
        return urljoin(BASE,"verArchivoHtml.do?"+urlencode({"ruta":html_ruta,"tipo":"rutaDocm"}))

    @classmethod
    def parse_summary_html(cls,html:str)->list[dict]:
        soup=BeautifulSoup(html,"html.parser")
        results={}
        for anchor in soup.find_all("a",href=True):
            href=anchor.get("href") or ""
            low=href.lower()
            if "descargararchivo.do" not in low or "/pdf/" not in low:
                continue

            node=cls._minimal_entry_node(anchor)
            text=" ".join(node.stripped_strings)
            nid=NID_RE.search(text)
            if not nid:
                continue

            nid_value=f"{nid.group(1)}/{nid.group(2)}"
            title=text[:nid.start()].strip(" ,.;:-")
            if not title:
                title=" ".join(anchor.stripped_strings).strip()
            if not RELEVANT.search(title) or EXCLUDE.search(title):
                continue

            results[nid_value]={
                "external_id":f"DOCM-{nid.group(1)}-{nid.group(2)}",
                "nid":nid_value,
                "title":title,
                "detail_url":cls._detail_url_from_pdf(href),
                "pdf_url":urljoin(BASE,href),
            }
        return list(results.values())

    def collect_day(self,day:date):
        html=self._get(SUMMARY_URL,params={"fecha":day.strftime("%Y%m%d")})
        if not html:
            return []

        out=[]
        for item in self.parse_summary_html(html):
            detail_url=item["detail_url"]
            detail_html=self._get(detail_url) if detail_url else None
            if detail_html:
                detail_text=BeautifulSoup(detail_html,"html.parser").get_text("\n",strip=True)
                source_url=detail_url
            else:
                detail_text=item["title"]
                source_url=item["pdf_url"]

            combined=item["title"]+"\n"+detail_text
            if not RELEVANT.search(combined):
                continue

            event=parse_event(
                source_code=self.code,
                external_id=item["external_id"],
                publication_date=day.isoformat(),
                title=item["title"],
                url=source_url,
                raw_text=detail_text,
            )
            if event.technology:
                out.append(event)
        return out
