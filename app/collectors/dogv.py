"""DOGV — Diari Oficial de la Generalitat Valenciana (official JSON backend of dogv.gva.es).

Endpoints are the ones used by the official portal (https://dogv.gva.es/dogv-portal-frontend):
  GET /dogv-portal/dogv/calendar?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD  -> publication days
  GET /dogv-portal/dogv?date=YYYY-MM-DD&lang=es                           -> daily summary
  GET /dogv-portal/disposicion/{id}?lang=es                               -> full text (HTML)
A calendar day without a bulletin is an OK day with zero candidates; any HTTP or
schema failure is raised so the day is recorded as ERROR (fail closed).
"""
from __future__ import annotations

import re
from datetime import date

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.parser import parse_event

API = "https://dogv.gva.es/dogv-portal"
PDF_BASE = "https://dogv.gva.es/datos"

RELEVANT = re.compile(
    r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|central\s+e[oó]lica|aerogenerador|"
    r"planta\s+solar|almacenamiento\s+(?:de\s+energ|electroqu|mediante\s+bater|por\s+bater)|bater[ií]as?\b|"
    r"hibridaci[oó]n|repotenciaci[oó]n",
    re.I,
)
EXCLUDE = re.compile(
    r"contrataci[oó]n|licitaci[oó]n|adjudicaci[oó]n|formalizaci[oó]n\s+de\s+contrato|autoconsumo|"
    r"subvenci[oó]n|ayudas?\b|bases\s+reguladoras|convocatoria|premio|curso|oposici[oó]n|"
    r"plan\s+general|modificaci[oó]n\s+puntual\s+del\s+plan|instalaci[oó]n\s+de\s+paneles\s+fotovoltaicos\s+en\s+(?:edificios|cubiertas)",
    re.I,
)
SCOPE_SUFFIX = "\nComunitat Valenciana"


class DOGVCollector:
    code = "DOGV"

    def __init__(self, timeout: int = 30, user_agent: str = "SpainRenewablesRadar/0.1"):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        retry = Retry(total=4, connect=3, read=2, status=4, backoff_factor=0.8,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET"}),
                      raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self._calendar: dict[str, dict[str, bool]] = {}
        self.audit: list[dict] = []

    # ---------- HTTP
    def _json(self, path: str, params: dict):
        r = self.session.get(API + path, params=params, timeout=(10, max(self.timeout, 60)))
        r.raise_for_status()
        if "json" not in (r.headers.get("content-type") or ""):
            raise ValueError(f"DOGV non-JSON response for {path}: {r.headers.get('content-type')}")
        return r.json()

    # ---------- calendar (one request per month, cached)
    def publication_days(self, day: date) -> dict[str, bool]:
        key = day.strftime("%Y-%m")
        if key not in self._calendar:
            first = day.replace(day=1)
            nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
            last = date.fromordinal(nxt.toordinal() - 1)
            rows = self._json("/dogv/calendar", {"startDate": first.isoformat(), "endDate": last.isoformat()})
            if not isinstance(rows, list):
                raise ValueError("DOGV calendar: unexpected payload")
            self._calendar[key] = {str(r["fecha"])[:10]: bool(r.get("esBis")) for r in rows if r.get("fecha")}
        return self._calendar[key]

    # ---------- parsing helpers (pure, tested offline)
    @staticmethod
    def summary_candidates(payload: dict, day: date) -> list[dict]:
        if not isinstance(payload, dict) or "disposiciones" not in payload:
            raise ValueError("DOGV summary: missing 'disposiciones'")
        want = day.strftime("%d/%m/%Y")
        out = {}
        for d in payload["disposiciones"] or []:
            if str(d.get("fechaPublicacion") or "") != want:
                continue
            title = " ".join(str(d.get("titulo") or "").split())
            if not d.get("id") or not title:
                continue
            if not RELEVANT.search(title) or EXCLUDE.search(title):
                continue
            out[str(d["id"])] = {
                "id": str(d["id"]), "title": title,
                "codigo": str(d.get("codigoInsercion") or ""),
                "url_pdf": PDF_BASE + d["urlPdf"] if str(d.get("urlPdf") or "").startswith("/") else None,
                "seccion": (d.get("seccion") or {}).get("descripcion"),
                "organismo": d.get("organismo"),
            }
        return list(out.values())

    @staticmethod
    def detail_text(payload: dict) -> str:
        html = (payload or {}).get("texto") or ""
        text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
        return re.sub(r"\n{3,}", "\n\n", text)

    @staticmethod
    def external_id(item: dict, detail: dict | None) -> str:
        cve = (detail or {}).get("cve")
        if cve and cve != "None":
            return str(cve)
        if item.get("codigo"):
            return "DOGV-" + item["codigo"].replace("/", "-")
        return "DOGV-ID-" + item["id"]

    # ---------- collector contract
    def collect_day(self, day: date):
        days = self.publication_days(day)
        if day.isoformat() not in days:
            return []
        payload = self._json("/dogv", {"date": day.isoformat(), "lang": "es"})
        self.audit.append({"date": day.isoformat(), "bis": days[day.isoformat()],
                           "numeroDogv": (payload.get("cabecera") or {}).get("numeroDogv"),
                           "dispositions": len(payload.get("disposiciones") or [])})
        out = []
        for item in self.summary_candidates(payload, day):
            detail = self._json(f"/disposicion/{item['id']}", {"lang": "es"})
            body = self.detail_text(detail)
            if not RELEVANT.search(item["title"] + "\n" + body):
                continue
            url = item["url_pdf"] or f"https://dogv.gva.es/es/inici?id={item['id']}"
            event = parse_event(source_code=self.code, external_id=self.external_id(item, detail),
                                publication_date=day.isoformat(), title=item["title"], url=url,
                                raw_text=body + SCOPE_SUFFIX)
            if event.technology:
                out.append(event)
        return out
