from __future__ import annotations

import html
import json
import re
from datetime import date

import requests

from app.parser import parse_event

API = "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI"
RELEVANT = re.compile(
    r"fotovolta|parque\s+e[oó]lico|instalaci[oó]n\s+e[oó]lica|m[oó]dulo\s+e[oó]lico|"
    r"m[oó]dulo\s+de\s+almacenamiento|sistema\s+de\s+almacenamiento|"
    r"almacenamiento\s+(?:de\s+energ[ií]a|energ[eé]tico|el[eé]ctric|electroqu[ií]mic)|"
    r"bater[ií]a|hibridaci[oó]n|aerogenerador|repotenciaci[oó]n",
    re.I,
)
STRONG_TITLE = re.compile(
    r"instalaci[oó]n\s+de\s+producci[oó]n\s+de\s+energ[ií]a\s+el[eé]ctrica|"
    r"levantamiento\s+de\s+actas|actas\s+de\s+pago|expropiaci[oó]n",
    re.I,
)
EXCLUDE = re.compile(
    r"contrataci[oó]n|licitaci[oó]n|adjudicaci[oó]n|"
    r"autoconsumo|instalaci[oó]n\s+de\s+paneles\s+fotovoltaicos\s+en\s+(?:edificios|cubiertas)",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s]+", re.I)


class BOACollector:
    code = "BOA"

    def __init__(self, timeout: int = 30, user_agent: str = "SpainRenewablesRadar/0.1"):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def _day_rows(self, day: date) -> list[dict]:
        d = day.strftime("%Y%m%d")
        params = {
            "CMD": "VERLST",
            "OUTPUTMODE": "JSON",
            "BASE": "BOLE",
            "DOCS": "1-500",
            "SEC": "OPENDATABOAJSON",
            "SORT": "-PUBL",
            "SEPARADOR": "",
            "@PUBL-GE": d,
            "@PUBL-LE": d,
        }
        response = self.session.get(API, params=params, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = "iso-8859-1"
        body = response.text.strip()

        if not body.startswith("["):
            if "No se han recuperado documentos" in body:
                return []
            raise RuntimeError("BOA OpenData did not return JSON")

        rows = json.loads(body)
        return rows if isinstance(rows, list) else []

    @staticmethod
    def _clean(value) -> str:
        return html.unescape(str(value or "")).replace("\ufffd", "").strip()

    @classmethod
    def _source_url(cls, row: dict) -> str:
        for key in ("UrlPdf", "UrlBCOM", "UriEli"):
            value = cls._clean(row.get(key))
            match = URL_RE.search(value)
            if match:
                return match.group(0).strip("'\"")

        docn = cls._clean(row.get("DOCN"))
        if docn:
            return (
                "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI"
                f"?BASE=BOLE&CMD=VERDOC&DOCN={docn}&SEC=BUSQUEDA_AVANZADA"
            )
        return "https://www.boa.aragon.es/"

    @classmethod
    def event_from_row(cls, day: date, row: dict):
        title = cls._clean(row.get("Titulo"))
        detail = cls._clean(row.get("Texto"))
        combined = title + "\n" + detail

        if EXCLUDE.search(title):
            return None
        if not RELEVANT.search(combined):
            return None
        if not RELEVANT.search(title) and not STRONG_TITLE.search(title):
            return None

        external_id = cls._clean(row.get("DOCN")) or (
            f"BOA-{day.isoformat()}-{cls._clean(row.get('NOrden'))}"
        )
        event = parse_event(
            source_code=cls.code,
            external_id=external_id,
            publication_date=day.isoformat(),
            title=title,
            url=cls._source_url(row),
            raw_text=detail,
        )
        return event if event.technology else None

    def collect_day(self, day: date):
        events = []
        for row in self._day_rows(day):
            event = self.event_from_row(day, row)
            if event:
                events.append(event)
        return events
