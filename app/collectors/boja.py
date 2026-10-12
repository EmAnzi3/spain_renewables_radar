from __future__ import annotations

import re
from datetime import date,timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from app.parser import parse_event

API="https://datos.juntadeandalucia.es/api/v0/boja"
RELEVANT=re.compile(r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|almacenamiento|bater[ií]a|hibridaci[oó]n|aerogenerador",re.I)
EXCLUDE=re.compile(r"contrataci[oó]n|licitaci[oó]n|adjudicaci[oó]n|autoconsumo|instalaci[oó]n\s+de\s+paneles\s+fotovoltaicos\s+en\s+(?:edificios|cubiertas)",re.I)

class BOJACollector:
    code="BOJA"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent,"Accept":"application/json"})

    def _get_json(self,url,params=None,allow_empty_400=False):
        r=self.session.get(url,params=params,timeout=self.timeout)
        if allow_empty_400 and r.status_code==400:
            # The API returns {"status":400,"message":"Bad request"} for
            # some nonpublication days. This response alone does NOT prove
            # that the bulletin was empty. Require independent verification.
            return {"_unverified_400":True}
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _publication_date(row):
        from datetime import datetime
        raw=row.get("date")
        if not isinstance(raw,str):
            raise ValueError("BOJA publication date absent")
        try:
            return datetime.strptime(raw,"%d/%m/%Y").date()
        except ValueError:
            try:return date.fromisoformat(raw)
            except ValueError as exc:raise ValueError("Invalid BOJA publication date") from exc

    def _pages(self,start:date,end:date,allow_empty_400=False):
        size=100
        page=0
        seen=set()
        total=None
        while True:
            payload=self._get_json(
                f"{API}/get/search_pagination",
                allow_empty_400=allow_empty_400,
                params={"order_by":"id","mode":"DESC","size":size,
                        "page":page,"date_from":start.isoformat(),
                        "date_to":end.isoformat()})
            if payload.get("_unverified_400"):
                if not allow_empty_400 or page!=0:raise ValueError("BOJA HTTP 400 not established as a zero-publication day")
                yield None
                return
            if not isinstance(payload,dict) or not isinstance(payload.get("results"),list):
                raise ValueError("BOJA malformed search payload")
            declared=payload.get("total_hits")
            if type(declared) is not int or declared<0:
                raise ValueError("BOJA total_hits missing/invalid")
            if total is None:total=declared
            elif declared!=total:raise ValueError("BOJA total count changed between pages")
            rows=payload["results"]
            if len(rows)>size:
                raise ValueError("BOJA page exceeds requested size")
            for row in rows:
                if not isinstance(row,dict) or not row.get("id"):
                    raise ValueError("BOJA row identity missing")
                key=str(row["id"])
                if key in seen:raise ValueError("BOJA repeated row across pages")
                if not start<=self._publication_date(row)<=end:
                    raise ValueError("BOJA row outside requested publication window")
                seen.add(key)
                if len(seen)>total:raise ValueError("BOJA page exceeds declared total")
                yield row
            if len(seen)==total:return
            if not rows or page>=200:
                raise ValueError("BOJA truncated or stalled pagination")
            page+=1

    def _day_rows(self,day:date):
        rows=self._pages(day,day,allow_empty_400=True)
        first=True
        for row in rows:
            if row is None:
                # Cross-check on a separate official window: a generic HTTP 400
                # cannot be silently promoted to a true zero-publication day.
                adjacent=list(self._pages(day-timedelta(days=1),
                                          day+timedelta(days=1)))
                if any(self._publication_date(item)==day for item in adjacent):
                    raise ValueError("BOJA exact-date 400 contradicts adjacent official search")
                return
            first=False
            yield row

    @staticmethod
    def _plain(value)->str:
        if value is None:
            return ""
        if not isinstance(value,str):
            return str(value)
        return BeautifulSoup(value,"html.parser").get_text(" ",strip=True)

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
