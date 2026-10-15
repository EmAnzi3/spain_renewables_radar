from __future__ import annotations

import re
import json
import hashlib
from pathlib import Path
from datetime import date,timedelta,datetime,timezone
from urllib.parse import quote,urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from app.parser import parse_event

API="https://datos.juntadeandalucia.es/api/v0/boja"
OFFICIAL_CALENDAR="https://www.juntadeandalucia.es/eboja/"
MONTHS_ES={
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
}
RELEVANT=re.compile(r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|almacenamiento|bater[ií]a|hibridaci[oó]n|aerogenerador",re.I)
EXCLUDE=re.compile(r"contrataci[oó]n|licitaci[oó]n|adjudicaci[oó]n|autoconsumo|instalaci[oó]n\s+de\s+paneles\s+fotovoltaicos\s+en\s+(?:edificios|cubiertas)",re.I)

class BOJACollector:
    code="BOJA"

    def __init__(self,timeout:int=30,user_agent:str="SpainRenewablesRadar/0.1"):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers.update({"User-Agent":user_agent,"Accept":"application/json"})
        # Retry transient GET failures only. A 400 still requires independent
        # calendar verification; restricted/forbidden bodies are not bypassed.
        retry=Retry(total=3,connect=3,read=2,status=2,backoff_factor=0.8,
                    status_forcelist=(429,500,502,503,504),
                    allowed_methods=frozenset({'GET'}),raise_on_status=False)
        adapter=HTTPAdapter(max_retries=retry)
        self.session.mount('https://',adapter)
        self.session.mount('http://',adapter)
        self._official_year_calendars={}
        self._calendar_receipts=[]
        self._restricted_review=[]


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
    def parse_official_calendar(html,year):
        soup=BeautifulSoup(html,"html.parser")
        tables=soup.select("table.calendario_tabla")
        if len(tables)!=12:
            raise ValueError("BOJA official yearly calendar must expose 12 months")
        observed_months=set()
        dates={}
        for table in tables:
            caption=table.find("caption")
            month=MONTHS_ES.get((caption.get_text(" ",strip=True) if caption else "").casefold())
            if not month or month in observed_months:
                raise ValueError("BOJA calendar missing or duplicated month")
            observed_months.add(month)
            for link in table.select("td.dia-boja a[href]"):
                try:
                    n=int(link.get_text(" ",strip=True))
                    d=date(year,month,n)
                except ValueError as exc:
                    raise ValueError("BOJA calendar has invalid day number") from exc
                href=link.get("href") or ""
                parsed=re.fullmatch(r"/eboja/"+str(year)+r"/(\d{1,4})/index\.html",href)
                multiple=re.fullmatch(r"/eboja/"+str(year)+rf"{month:02d}{n:02d}\.html",href)
                if d in dates or (parsed is None and multiple is None):
                    raise ValueError("BOJA calendar issue URL or day identity invalid")
                # The official 'varios' page groups multiple bulletin editions.
                # A search HTTP 400 on such a published day cannot mean zero.
                dates[d]=parsed.group(1) if parsed else "MULTIPLE_OFFICIAL_EDITIONS"
        if len(dates)<150:
            raise ValueError("BOJA official yearly calendar is unexpectedly incomplete")
        return dates

    def _verified_nonpublication_day(self,day):
        year=day.year
        if year not in self._official_year_calendars:
            url=f"{OFFICIAL_CALENDAR}{year}.html"
            response=self.session.get(url,headers={'Accept':'text/html'},timeout=(8,max(self.timeout,40)),allow_redirects=False)
            response.raise_for_status()
            if response.status_code!=200 or response.url!=url:
                raise ValueError("BOJA official calendar refused or redirected")
            raw=response.content
            dates=self.parse_official_calendar(raw,year)
            self._official_year_calendars[year]=dates
            self._calendar_receipts.append({
                "year":year,"source_url":url,"retrieved_at":datetime.now(timezone.utc).isoformat(),
                "sha256":hashlib.sha256(raw).hexdigest(),"original_bytes":len(raw),
                "edition_days":len(dates),"source":"OFFICIAL_BOJA_YEARLY_EDITION_CALENDAR",
            })
            out=Path("reports/boja");out.mkdir(parents=True,exist_ok=True)
            (out/f"calendar_{year}.html").write_bytes(raw)
        if day in self._official_year_calendars[year]:
            raise ValueError("BOJA returned HTTP 400 on a date with an official edition")
        return True

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
                # Calendar verified independently on the official eBOJA
                # publication-year page. An HTTP400 alone is never a zero.
                self._verified_nonpublication_day(day)
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
            raise ValueError('BOJA detail identity missing')
        url=f"{API}/{quote(bid,safe='')}"
        # Exhausted retries must remain a source failure. A search summary
        # cannot replace an unavailable original body and certify full text.
        payload=self._get_json(url)
        text=self._flatten_text(payload)
        if not text:
            raise ValueError('BOJA detail returned no original source text')
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
        return text,public_url or url

    def collect_day(self,day:date):
        out=[]
        for row in self._day_rows(day):
            title=self._plain(row.get("summary") or row.get("title") or "")
            if not RELEVANT.search(title) or EXCLUDE.search(title):
                continue
            detail_text,source_url=self._detail(row)
            if "Texto de acceso restringido" in detail_text:
                # The official supplement is legally restricted after six
                # months. Preserve the actual title and visible notice, but
                # never infer a plant, MW, promoter or granted permit.
                self._restricted_review.append({
                    'source_code':self.code,'external_id':str(row.get('id') or ''),
                    'publication_date':day.isoformat(),'title':title,
                    'url':source_url,'raw_text':detail_text,
                    'reason':'OFFICIAL_NOTICE_BODY_RESTRICTED_ARTICLE_32',
                    'added_to_projects':False})
                continue
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

    def persist_metadata(self,conn):
        root=Path("reports/boja");root.mkdir(parents=True,exist_ok=True)
        reviews=sorted(self._restricted_review,key=lambda x:(x['publication_date'],x['external_id']))
        if len({x['external_id'] for x in reviews})!=len(reviews):
            raise ValueError("BOJA restricted notice identities are duplicated")
        report={'mode':'PUBLIC_METADATA_ONLY_NOT_COMPLETE_PERMIT_EVIDENCE',
                'restricted_document_count':len(reviews),
                'original_article_32_legal_scope':True,
                'cannot_be_counted_as_verified_project_events':True,
                'official_year_calendar_checks':self._calendar_receipts,
                'restricted_leads':reviews}
        (root/'historical_restricted_leads.json').write_text(
            json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print("BOJA_RESTRICTED_ARCHIVE_LEADS",len(reviews),flush=True)
