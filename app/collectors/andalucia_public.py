"""Official Andalucia public-information archive with explicit source-data gaps."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.parser import parse_event
from app.and_public_catalogue import acquire_catalogue, replay_catalogue

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
    """Never replace missing publication dates with update or allegation dates."""
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
    for index, record in enumerate(payload):
        if not isinstance(record, dict) or not str(record.get('id', '')).isdigit():
            raise ValueError(f'Andalucia archive malformed identity at row {index}: {record!r}')
        identifier = str(record['id'])
        if identifier in identifiers:
            raise ValueError('Duplicate Andalucia document id: ' + identifier)
        if record.get('title') is not None and not isinstance(record['title'], str):
            raise ValueError('Invalid Andalucia title type: ' + identifier)
        identifiers.add(identifier)
    return payload


def public_url(identifier) -> str:
    return PUBLIC_BASE + 'servicios/participacion/todos-documentos/detalle/' + str(identifier) + '.html'


def document_links(record: dict) -> list[dict]:
    result = []
    for attachment in record.get('documents') or []:
        for document in attachment.get('field_documento_p') or []:
            for media in document.get('field_media_file') or []:
                uri = media.get('uri')
                if uri:
                    url = urljoin(PUBLIC_BASE, uri)
                    if url.startswith(PUBLIC_BASE):
                        result.append({'title': attachment.get('field_titulo'), 'url': url})
    return result


def relevant_record(record: dict) -> bool:
    title = record.get('title') or ''
    return bool(RELEVANT.search(title) and not EXCLUDE.search(title))


def partition_archive(records: list[dict]) -> dict:
    """Account for EVERY source identity. Missing source metadata is never fabricated."""
    result = {'dated': [], 'undated': [], 'missing_title': [], 'non_target': []}
    for record in records:
        if not (record.get('title') or '').strip():
            result['missing_title'].append(record)
        elif not relevant_record(record):
            result['non_target'].append(record)
        elif publication_date(record.get('publication_date')) is None:
            result['undated'].append(record)
        else:
            result['dated'].append(record)
    assert sum(len(rows) for rows in result.values()) == len(records)
    return result


def write_source_gaps(parts: dict, output: Path) -> list[dict]:
    gaps = []
    for bucket, reason in (('missing_title','SOURCE_MISSING_TITLE'), ('undated','SOURCE_MISSING_PUBLICATION_DATE')):
        for record in parts[bucket]:
            gaps.append({'source_code':'AND_PUBLIC', 'external_id':str(record['id']),
                         'reason':reason, 'url':public_url(record['id']), 'raw_record':record})
    (output/'source_gaps.json').write_text(json.dumps(gaps,ensure_ascii=False,indent=2),encoding='utf-8')
    body = ''.join('<tr><td>'+html.escape(gap['external_id'])+'</td><td>'+html.escape(gap['reason'])
                   +'</td><td>'+html.escape(gap['raw_record'].get('title') or 'Titolo non pubblicato')
                   +'</td><td><a href="'+html.escape(gap['url'],quote=True)+'">Fonte ufficiale</a></td></tr>' for gap in gaps)
    (output/'source_gaps.html').write_text(
        '<!doctype html><html lang="it"><meta charset="utf-8"><title>Andalucía — dati mancanti alla fonte</title>'
        '<style>body{font:15px system-ui;margin:30px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:10px;text-align:left}</style>'
        '<h1>Andalucía — schede da verificare</h1><p>Le schede senza data non sono presentate come nuove pubblicazioni. '
        'I record originali sono conservati integralmente: nessuna data o denominazione è ricostruita.</p>'
        '<table><tr><th>ID fonte</th><th>Problema</th><th>Titolo fonte</th><th>Documento</th></tr>'+body+'</table></html>',encoding='utf-8')
    return gaps


def event_from_record(record: dict):
    if not relevant_record(record):
        return None
    pub = publication_date(record.get('publication_date'))
    if pub is None:
        raise ValueError('Relevant Andalucia document has no valid publication date: ' + str(record.get('id')))
    title = record['title'].strip()
    extraction_title = re.sub(r'(?<=[A-Za-z0-9])\s*([-\/])\s*(?=[0-9])', r'\1', title)
    event = parse_event(source_code='AND_PUBLIC', external_id=str(record['id']), publication_date=pub,
                        title=extraction_title, url=public_url(record['id']), raw_text=extraction_title)
    if event.technology not in {'PV', 'WIND', 'BESS', 'HYBRID'}:
        return None
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
        retry = Retry(total=0)  # The catalogue reader owns the single bounded retry budget.
        self.session.mount('https://', HTTPAdapter(max_retries=retry))
        self._records = None
        self._fatal_error = None
        self.audit = {'source_code':self.code, 'complete':False, 'archive_records':0,
                      'expected_records':None, 'relevant_records':0, 'relevant_invalid_dates':[],
                      'dated_coverage_complete':False, 'scope':'DATED_PUBLICATIONS_WITH_UNDATED_INVENTORY'}

    def _load(self):
        if self._records is not None:
            return
        if self._fatal_error:
            raise RuntimeError(self._fatal_error)
        output = Path('reports/andalucia_public'); output.mkdir(parents=True, exist_ok=True)
        try:
            records, acquisition = acquire_catalogue(self.session, output, self.timeout)
            records = validate_archive(records, acquisition['expected_records'])
            self.audit.update(acquisition)
            if replay_catalogue(output, self.audit) != records:
                raise ValueError('Live catalogue did not reproduce its original responses')
            self.audit['source_replay_verified'] = True
            parts = partition_archive(records)
            self.audit.update(partitions={key:len(value) for key,value in parts.items()})
            selected = parts['dated'] + parts['undated']
            gaps = write_source_gaps(parts, output)
            self.audit.update(relevant_records=len(selected), source_gaps=len(gaps),
                              relevant_invalid_dates=[str(r['id']) for r in parts['undated']],
                              source_missing_titles=[str(r['id']) for r in parts['missing_title']],
                              dated_coverage_complete=not gaps)
            (output/'source_records.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
            (output/'documents.json').write_text(json.dumps([
                {'external_id':str(r['id']), 'documents':document_links(r)} for r in selected
            ],ensure_ascii=False,indent=2),encoding='utf-8')
            # complete means source snapshot acquired/reconciled, NOT complete source metadata.
            self.audit['complete'] = True
            self._records = parts['dated']
            print(f"AND_PUBLIC snapshot={len(records)}; dated={len(parts['dated'])}; source gaps={len(gaps)}; acquisition={self.audit['mode']}",flush=True)
        except Exception as exc:
            self._fatal_error = str(exc)
            self.audit.update(complete=False, error=str(exc))
            raise
        finally:
            (output/'coverage.json').write_text(json.dumps(self.audit,ensure_ascii=False,indent=2),encoding='utf-8')

    def collect_day(self, day: date):
        self._load()
        return [event for record in self._records
                if publication_date(record.get('publication_date')) == day.isoformat()
                for event in [event_from_record(record)] if event is not None]
