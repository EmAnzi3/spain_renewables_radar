from __future__ import annotations

import re
from datetime import date
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.parser import parse_event

BASE="https://doe.juntaex.es/"
SUMMARY=urljoin(BASE,"ultimosdoe/mostrardoe.php")
DETAIL_PATH="otrosFormatos/html.php"
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

class DOECollector:
    code="DOE"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent})

    def _get(self,url:str,params=None)->str|None:
        r=self.session.get(url,params=params,timeout=self.timeout)
        if r.status_code==404:
            return None
        r.raise_for_status()
        r.encoding=r.apparent_encoding or "iso-8859-1"
        return r.text

    @staticmethod
    def _external_id(detail_url:str)->str|None:
        q=parse_qs(urlparse(detail_url).query)
        xml=(q.get("xml") or [None])[0]
        return f"DOE-{xml}" if xml else None

    @classmethod
    def parse_summary_html(cls,html:str)->list[dict]:
        soup=BeautifulSoup(html,"html.parser")
        rows={}
        for a in soup.find_all("a",href=True):
            detail_url=urljoin(BASE,a.get("href") or "")
            if DETAIL_PATH.lower() not in detail_url.lower():
                continue

            external_id=cls._external_id(detail_url)
            if not external_id:
                continue

            # In the DOE sumario the HTML/PDF icons are children of the same
            # <p> that contains the full disposition title.
            parent=a.find_parent("p")
            if parent is None:
                continue
            title=" ".join(parent.stripped_strings).strip()
            if not title or not RELEVANT.search(title) or EXCLUDE.search(title):
                continue

            rows[external_id]={
                "external_id":external_id,
                "title":title,
                "detail_url":detail_url,
            }
        return list(rows.values())

    def collect_day(self,day:date):
        html=self._get(SUMMARY,params={"fecha":day.strftime("%Y%m%d"),"t":"o"})
        if not html:
            return []

        out=[]
        for item in self.parse_summary_html(html):
            detail_html=self._get(item["detail_url"])
            if detail_html:
                detail_text=BeautifulSoup(detail_html,"html.parser").get_text("\n",strip=True)
            else:
                detail_text=item["title"]

            combined=item["title"]+"\n"+detail_text
            if not RELEVANT.search(combined):
                continue

            event=parse_event(
                source_code=self.code,
                external_id=item["external_id"],
                publication_date=day.isoformat(),
                title=item["title"],
                url=item["detail_url"],
                raw_text=detail_text,
            )
            if event.technology:
                out.append(event)
        return out
