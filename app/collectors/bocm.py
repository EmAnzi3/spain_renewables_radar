from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from app.parser import parse_event

BASE="https://www.bocm.es/"
SEARCH_URL=urljoin(BASE,"search-day-month")
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

class BOCMCollector:
    code="BOCM"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent})
        retry=Retry(
            total=4,
            connect=3,
            read=2,
            status=4,
            backoff_factor=0.8,
            status_forcelist=(429,500,502,503,504),
            allowed_methods=frozenset({"GET","POST"}),
            raise_on_status=False,
        )
        adapter=HTTPAdapter(max_retries=retry)
        self.session.mount("https://",adapter)
        self.session.mount("http://",adapter)

    def _get(self,url:str)->str|None:
        r=self.session.get(url,timeout=self.timeout)
        if r.status_code==404:
            return None
        r.raise_for_status()
        r.encoding=r.apparent_encoding or "utf-8"
        return r.text

    def _daily_xml_url(self,day:date)->str|None:
        # Official BOCM date form. It redirects to the bulletin page when a
        # bulletin exists; weekends/non-publication days simply yield no XML.
        r=self.session.post(
            SEARCH_URL,
            data={"field_date[date]":day.strftime("%d/%m/%Y")},
            timeout=self.timeout,
            allow_redirects=True,
        )
        r.raise_for_status()
        soup=BeautifulSoup(r.text,"html.parser")
        for a in soup.find_all("a",href=True):
            href=urljoin(r.url,a["href"])
            low=href.lower()
            if "cm_boletin_bocm" in low and low.endswith(".xml"):
                return href
        return None

    @staticmethod
    def parse_summary_xml(xml_text:str)->list[dict]:
        root=ET.fromstring(xml_text)
        rows={}
        for node in root.findall(".//disposicion"):
            def txt(tag):
                el=node.find(tag)
                return "".join(el.itertext()).strip() if el is not None else ""
            external_id=txt("identificador")
            title=txt("titulo")
            if not external_id or not title:
                continue
            if not RELEVANT.search(title) or EXCLUDE.search(title):
                continue
            rows[external_id]={
                "external_id":external_id,
                "title":title,
                "url_html":txt("url_html"),
                "url_xml":txt("url_xml"),
                "url_pdf":txt("url_pdf"),
            }
        return list(rows.values())

    @staticmethod
    def _xml_text(xml_text:str)->str:
        root=ET.fromstring(xml_text)
        return "\n".join(
            " ".join(t.split())
            for t in root.itertext()
            if t and t.strip()
        )

    def collect_day(self,day:date):
        daily_xml=self._daily_xml_url(day)
        if not daily_xml:
            return []
        summary=self._get(daily_xml)
        if not summary:
            return []

        out=[]
        for item in self.parse_summary_xml(summary):
            detail_text=item["title"]
            source_url=item["url_html"] or item["url_xml"] or item["url_pdf"] or daily_xml
            if item["url_xml"]:
                detail=self._get(item["url_xml"])
                if detail:
                    try:
                        detail_text=self._xml_text(detail)
                    except ET.ParseError:
                        detail_text=BeautifulSoup(detail,"html.parser").get_text("\n",strip=True)

            combined=item["title"]+"\n"+detail_text
            if not RELEVANT.search(combined):
                continue

            # Madrid is a single-province autonomous community. Adding the
            # official source scope gives the generic parser deterministic
            # geography without guessing from company addresses.
            scoped_detail=detail_text+"\nComunidad de Madrid"
            event=parse_event(
                source_code=self.code,
                external_id=item["external_id"],
                publication_date=day.isoformat(),
                title=item["title"],
                url=source_url,
                raw_text=scoped_detail,
            )
            if event.technology:
                out.append(event)
        return out
