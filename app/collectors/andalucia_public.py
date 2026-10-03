"""Official Andalucia public-information archive; bulletin collectors stay independent."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.parser import parse_event

API = 'https://datos.juntadeandalucia.es/api/v0/public-documents'
ARCHIVE_URL = API + '/all?format=json'
COUNT_URL = API + '/count'
PUBLIC_BASE = 'https://www.juntadeandalucia.es/'
RELEVANT = re.compile(
    r'fotovolta|parque\s+e[oó]lico|planta\s+e[oó]lica|instalaci[oó]n\s+e[oó]lica|'
    r'\bbess\b|almacenamiento\s+(?:de\s+energ[ií]a|energ[eé]tic|el[eé]ctric)|'
    r'(?:sistema|planta|m[oó]dulo)\s+de\s+bater[ií]as', re.I)
EXCLUDE = re.compile(
    r'autoconsumo|licitaci[oó]n|adjudicaci[oó]n|fabricaci[oó]n\s+de\s+(?:bater[ií]as|paneles)|'
    r'almacenamiento\s+(?:de\s+)?(?:gas|hidrocarburos|di[oó]xido)|'
    r'reciclaje\s+de\s+(?:paneles|bater[ií]as)', re.I)
PUBLIC_INFO = re.compile(r'informaci[oó]n\s+p[uú]blica|tr[aá]mite\s+de\s+alegaciones', re.I)


def publication_date(value) -> str | None:
    """Accept observed source formats, never substitute update or consultation dates."""
    if not isinstance(value, str):
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def validate_archive(payload, expected_count: int) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise ValueError('Andalucia archive is not a nonempty JSON list')
    if len(payload) != expected_count:
        raise ValueError(f'Andalucia archive count mismatch: {len(payload)} != {expected_count}')
    identifiers = set()
    for record in payload:
        if not isinstance(record, dict) or not str(record.get('id', '')).isdigit() or not record.get('title'):
            raise ValueError('Andalucia archive has a malformed record')
        identifier = str(record['id'])
        if identifier in identifiers:
            raise ValueError('Duplicate Andalucia document id: ' + identifier)
        identifiers.add(identifier)
    return payload


def document_links(record: dict) -> list[dict]:
    result = []
    for attachment in record.get('documents') or []:
        for document in attachment.get('field_documento_p') or []:
            for media in document.get('field_media_file') or []:
                uri = media.get('uri')
                if not uri:
                    continue
                url = urljoin(PUBLIC_BASE, uri)
                # Only documented official attachments. No fetching external links here.
                if url.startswith(PUBLIC_BASE):
                    result.append({'title': attachment.get('field_titulo'), 'url': url})
    return result


def relevant_record(record: dict) -> bool:
    title = record.get('title') or ''
    return bool(RELEVANT.search(title) and not EXCLUDE.search(title))


def event_from_record(record: dict):
    if not relevant_record(record):
        return None
    pub = publication_date(record.get('publication_date'))
    if pub is None:
        raise ValueError('Relevant Andalucia document has no valid publication date: ' + str(record.get('id')))
    title = record['title'].strip()
    # Typography such as CG- 870 is a spacing variant, not a different expediente.
    extraction_title = re.sub(r'(?<=[A-Za-z0-9])\s*([-\/])\s*(?=[0-9])', r'\1', title)
    url = PUBLIC_BASE + 'servicios/participacion/todos-documentos/detalle/' + str(record['id']) + '.html'
    event = parse_event(source_code='AND_PUBLIC', external_id=str(record['id']), publication_date=pub,
                        title=extraction_title, url=url, raw_text=extraction_title)
    if event.technology not in {'PV', 'WIND', 'BESS', 'HYBRID'}:
        return None
    # An attached AAC is evidence to read, not a new grant inferred from its filename.
    if PUBLIC_INFO.search(title) or PUBLIC_INFO.search(record.get('document_type') or ''):
        event.event_type = 'PUBLIC_INFO'
        event.commercial_stage = 'EARLY'
    event.ccaa = 'Andalucía'
    event.title = title
    event.raw_text = json.dumps(record, ensure_ascii=False, sort_keys=True)
    return event


class AndaluciaPublicCollector:
    code = 'AND_PUBLIC'

    def __init__(self, timeout=30, user_agent='SpainRenewablesRadar/0.2'):
        self.timeout = (10, max(timeout, 90))
        self.session = requests.Session()
        self.session.headers['User-Agent'] = user_agent
        retry = Retry(total=2, connect=2, read=1, status=2, backoff_factor=1,
                      status_forcelist=(429,500,502,503,504), allowed_methods=frozenset({'GET'}))
        self.session.mount('https://', HTTPAdapter(max_retries=retry))
        self._records = None
        self._fatal_error = None
        self.audit = {'source_code':self.code, 'complete':False, 'archive_records':0,
                      'expected_records':None, 'relevant_records':0, 'relevant_invalid_dates':[]}

    def _get_count(self):
        response = self.session.get(COUNT_URL, timeout=self.timeout)
        response.raise_for_status()
        value = response.json()['count']['result']
        if not isinstance(value, int) or value <= 0:
            raise ValueError('Invalid Andalucia count response')
        return value

    def _load(self):
        if self._records is not None:
            return
        if self._fatal_error:
            raise RuntimeError(self._fatal_error)
        output = Path('reports/andalucia_public'); output.mkdir(parents=True, exist_ok=True)
        try:
            expected = self._get_count()
            response = self.session.get(ARCHIVE_URL, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            after = self._get_count()
            if expected != after:
                raise ValueError('Andalucia catalogue changed during snapshot; retry a fresh run')
            records = validate_archive(payload, expected)
            self.audit.update(archive_records=len(records), expected_records=expected,
                              retrieved_at=datetime.now(timezone.utc).isoformat(), source_url=ARCHIVE_URL,
                              download_url=response.url, sha256=hashlib.sha256(response.content).hexdigest())
            selected = [record for record in records if relevant_record(record)]
            self.audit['relevant_records'] = len(selected)
            invalid = [str(r['id']) for r in selected if publication_date(r.get('publication_date')) is None]
            self.audit['relevant_invalid_dates'] = invalid
            (output/'source_records.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')
            (output/'documents.json').write_text(json.dumps([
                {'external_id':str(r['id']), 'documents':document_links(r)} for r in selected
            ], ensure_ascii=False, indent=2), encoding='utf-8')
            if invalid:
                raise ValueError(f'Andalucia relevant documents with missing publication dates: {invalid}')
            self.audit['complete'] = True
            self._records = selected
        except Exception as exc:
            self._fatal_error = str(exc)
            raise
        finally:
            (output/'coverage.json').write_text(json.dumps(self.audit, ensure_ascii=False, indent=2), encoding='utf-8')

    def collect_day(self, day: date):
        self._load()
        return [event for record in self._records
                if publication_date(record.get('publication_date')) == day.isoformat()
                for event in [event_from_record(record)] if event is not None]
