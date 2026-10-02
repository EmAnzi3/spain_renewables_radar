from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.parser import BOE_ID_RE, parse_event

BASE="https://www.boe.es"
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
            results[boe_id]={"external_id":boe_id,"title":text[:1500],"href":href}
        return list(results.values())

    def collect_day(self,day:date):
        day_url=f"{BASE}/boe/dias/{day:%Y/%m/%d}/"
        html=self._get(day_url)
        if not html:return []
        out=[]
        for item in self.parse_summary_html(html):
            boe_id=item["external_id"]
            text_url=f"{BASE}/diario_boe/txt.php?id={boe_id}"
            detail_html=self._get(text_url)
            if detail_html:
                detail_text=BeautifulSoup(detail_html,"html.parser").get_text("\n",strip=True)
            else:
                detail_text=item["title"]
                text_url=item["href"] or day_url
            combined=item["title"]+"\n"+detail_text
            if not RELEVANT.search(combined):continue
            event=parse_event(source_code=self.code,external_id=boe_id,publication_date=day.isoformat(),title=item["title"],url=text_url,raw_text=detail_text)
            if event.technology:out.append(event)
        return out
