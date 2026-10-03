from __future__ import annotations

import html
import json
import re
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    r"autoconsumo|instalaci[oó]n\s+de\s+paneles\s+fotovoltaicos\s+en\s+(?:edificios|cubiertas)|"
    r"gigafactor[ií]a\s+de\s+bater[ií]as\s+para\s+veh[ií]culos|fabricaci[oó]n\s+de\s+veh[ií]culos",
    re.I,
)

URL_RE = re.compile(r"https?://[^\s\x60]+", re.I)
MULTI_QUOTED_PROJECT = re.compile(
    r'["«](Planta\s+(?:solar\s+)?fotovoltaica|Parque\s+e[oó]lico)\s+([^"»]{3,120})["»]',
    re.I,
)


class BOACollector:
    code = "BOA"

    def __init__(self, timeout: int = 30, user_agent: str = "SpainRenewablesRadar/0.1"):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        retry=Retry(
            total=4,
            connect=4,
            read=2,
            status=3,
            backoff_factor=0.8,
            status_forcelist=(429,500,502,503,504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter=HTTPAdapter(max_retries=retry)
        self.session.mount("https://",adapter)
        self.session.mount("http://",adapter)

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

        try:
            rows = json.loads(body)
        except json.JSONDecodeError:
            # BOA occasionally emits raw backslashes inside JSON strings.
            # Escape only backslashes that are not valid JSON escape starters.
            repaired = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', body)
            rows = json.loads(repaired)
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

    @classmethod
    def events_from_row(cls, day: date, row: dict):
        title = cls._clean(row.get("Titulo"))
        detail = cls._clean(row.get("Texto"))

        # Some expropriation/payment notices group several plants in one BOA
        # disposition. Preserve one event per plant instead of silently
        # collapsing the document to the first project.
        if STRONG_TITLE.search(title):
            matches = list(MULTI_QUOTED_PROJECT.finditer(detail))
            unique = []
            seen = set()
            for match in matches:
                name = match.group(2).strip(" ,.;:-")
                key = name.casefold()
                if key not in seen:
                    seen.add(key)
                    unique.append((match, name))

            if len(unique) > 1:
                events = []
                for idx, (match, name) in enumerate(unique, start=1):
                    next_start = unique[idx][0].start() if idx < len(unique) else len(detail)
                    segment = detail[match.start():next_start]
                    kind = match.group(1)
                    base_title = re.sub(
                        r"expedientes?\s+(?:n[uú]mero\s*)?[^.]*\.?",
                        "",
                        title,
                        flags=re.I,
                    )
                    synthetic_title = f'{base_title} | {kind} "{name}"'
                    external_id = cls._clean(row.get("DOCN")) or f"BOA-{day.isoformat()}"
                    event = parse_event(
                        source_code=cls.code,
                        external_id=f"{external_id}#{idx}",
                        publication_date=day.isoformat(),
                        title=synthetic_title,
                        url=cls._source_url(row),
                        raw_text=segment,
                    )
                    if event.technology:
                        events.append(event)
                if events:
                    return events

        event = cls.event_from_row(day, row)
        return [event] if event else []

    def collect_day(self, day: date):
        events = []
        for row in self._day_rows(day):
            events.extend(self.events_from_row(day, row))
        return events
