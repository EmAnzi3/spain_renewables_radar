from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from app.parser import parse_event

API="https://datos.juntadeandalucia.es/api/v0/boja"
RELEVANT=re.compile(r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|almacenamiento|bater[ií]a|hibridaci[oó]n|aerogenerador",re.I)
EXCLUDE=re.compile(r"contrataci[oó]n|licitaci[oó]n|adjudicaci[oó]n|instalaci[oó]n\s+de\s+paneles\s+fotovoltaicos\s+en\s+(?:edificios|cubiertas)",re.I)

class BOJACollector:
    code="BOJA"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent,"Accept":"application/json"})

    def _get_json(self,url,params=None):
        r=self.session.get(url,params=params,timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _plain(value)->str:
        if value is None:
            return ""
        if not isinstance(value,str):
            return str(value)
        return BeautifulSoup(value,"html.parser").get_text(" ",strip=True)

    def _day_rows(self,day:date):
        page=0
        size=200
        while True:
            payload=self._get_json(
                f"{API}/get/search_pagination",
                params={
                    "order_by":"dateUTC",
                    "mode":"DESC",
                    "size":size,
                    "page":page,
                    "date_from":day.isoformat(),
                    "date_to":day.isoformat(),
                },
            )
            rows=payload.get("results") or []
            for row in rows:
                yield row
            total=int(payload.get("total_hits") or payload.get("hits") or 0)
            if not rows or (page+1)*size >= total:
                break
            page+=1

    @classmethod
    def _flatten_text(cls,node)->str:
        parts=[]
        def walk(x):
            if isinstance(x,dict):
                priority=("title","summaryNoHtml","summary","bodyNoHtml","body","headsup","organisation")
                seen=set()
                for k in priority:
                    if k in x:
                        seen.add(k);walk(x[k])
                for k,v in x.items():
                    if k not in seen and isinstance(v,(dict,list)):
                        walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
            elif isinstance(x,str):
                p=cls._plain(x)
                if p:parts.append(p)
        walk(node)
        return "\n".join(dict.fromkeys(parts))

    def _detail(self,row:dict)->tuple[str,str]:
        bid=str(row.get("id") or "")
        if not bid:
            return self._plain(row.get("summary")),"https://www.juntadeandalucia.es/eboja.html"
        url=f"{API}/{quote(bid,safe='')}"
        try:
            payload=self._get_json(url)
        except Exception:
            payload=row
        text=self._flatten_text(payload)
        public_url=None
        def find_url(x):
            nonlocal public_url
            if public_url:return
            if isinstance(x,dict):
                for k,v in x.items():
                    if k in ("publicUrl","url","urlHtml") and isinstance(v,str) and v.startswith("http"):
                        public_url=v;return
                    find_url(v)
            elif isinstance(x,list):
                for v in x:find_url(v)
        find_url(payload)
        return text or self._plain(row.get("summary")),public_url or url

    def collect_day(self,day:date):
        out=[]
        for row in self._day_rows(day):
            title=self._plain(row.get("summary") or row.get("title") or "")
            if not RELEVANT.search(title) or EXCLUDE.search(title):
                continue
            detail_text,source_url=self._detail(row)
            combined=title+"\n"+detail_text
            if not RELEVANT.search(combined):
                continue
            event=parse_event(
                source_code=self.code,
                external_id=str(row.get("id") or f"BOJA-{day.isoformat()}-{len(out)}"),
                publication_date=day.isoformat(),
                title=title,
                url=source_url,
                raw_text=detail_text,
            )
            if event.technology:
                out.append(event)
        return out
