from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.parser import BOE_ID_RE, parse_event

BASE="https://www.boe.es"
API_BASE=f"{BASE}/datosabiertos/api/boe/sumario"
RELEVANT=re.compile(r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|almacenamiento|bater[ií]a|hibridaci[oó]n|aerogenerador",re.I)

class BOECollector:
    code="BOE"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent})

    def _get(self,url:str)->str|None:
        r=self.session.get(url,timeout=self.timeout)
        if r.status_code==404:return None
        r.raise_for_status()
        r.encoding=r.apparent_encoding or "utf-8"
        return r.text

    def _get_json(self,url:str):
        r=self.session.get(url,headers={"Accept":"application/json"},timeout=self.timeout)
        if r.status_code==404:return None
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _iter_api_items(node):
        if isinstance(node,dict):
            if "identificador" in node and "titulo" in node:
                ident=str(node.get("identificador") or "")
                if BOE_ID_RE.fullmatch(ident):
                    yield node
            for value in node.values():
                yield from BOECollector._iter_api_items(value)
        elif isinstance(node,list):
            for value in node:
                yield from BOECollector._iter_api_items(value)

    @staticmethod
    def parse_api_json(payload)->list[dict]:
        results={}
        for item in BOECollector._iter_api_items(payload):
            title=str(item.get("titulo") or "")
            if not RELEVANT.search(title):
                continue
            boe_id=str(item.get("identificador") or "").upper()
            url_html=item.get("url_html")
            if isinstance(url_html,dict):
                url_html=url_html.get("texto")
            url_pdf=item.get("url_pdf")
            if isinstance(url_pdf,dict):
                url_pdf=url_pdf.get("texto")
            results[boe_id]={
                "external_id":boe_id,
                "title":title[:4000],
                "href":url_html or url_pdf or f"{BASE}/buscar/doc.php?id={boe_id}",
            }
        return list(results.values())

    @staticmethod
    def parse_summary_html(html:str)->list[dict]:
        soup=BeautifulSoup(html,"html.parser")
        results={}
        for node in soup.find_all(["li","p","div"]):
            text=" ".join(node.stripped_strings)
            if not text or not RELEVANT.search(text):continue
            boe_id=None;href=None
            for a in node.find_all("a",href=True):
                candidate=a.get_text(" ",strip=True)+" "+a["href"]
                m=BOE_ID_RE.search(candidate)
                if m:
                    boe_id=m.group(0).upper()
                    href=urljoin(BASE,a["href"])
                    break
            if not boe_id:
                m=BOE_ID_RE.search(text)
                if m:boe_id=m.group(0).upper()
            if not boe_id:continue
            results[boe_id]={"external_id":boe_id,"title":text[:4000],"href":href}
        return list(results.values())

    def _summary_items(self,day:date)->list[dict]:
        api_url=f"{API_BASE}/{day:%Y%m%d}"
        try:
            payload=self._get_json(api_url)
            if payload:
                return self.parse_api_json(payload)
        except Exception as exc:
            print(f"  WARN BOE API fallback HTML: {exc}")
        html=self._get(f"{BASE}/boe/dias/{day:%Y/%m/%d}/")
        return self.parse_summary_html(html) if html else []

    def collect_day(self,day:date):
        out=[]
        for item in self._summary_items(day):
            boe_id=item["external_id"]
            text_url=f"{BASE}/diario_boe/txt.php?id={boe_id}"
            detail_html=self._get(text_url)
            if detail_html:
                detail_text=BeautifulSoup(detail_html,"html.parser").get_text("\n",strip=True)
            else:
                detail_text=item["title"]
                text_url=item["href"]
            combined=item["title"]+"\n"+detail_text
            if not RELEVANT.search(combined):continue
            event=parse_event(
                source_code=self.code,external_id=boe_id,publication_date=day.isoformat(),
                title=item["title"],url=text_url,raw_text=detail_text
            )
            if event.technology:out.append(event)
        return out
