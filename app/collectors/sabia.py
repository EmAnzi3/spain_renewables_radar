from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.geo import PROVINCE_TO_CCAA, find_province
from app.lifecycle import commercial_stage
from app.parser import ParsedEvent, build_project_key, detect_technology, extract_power_mw, extract_project_name

SEARCH_URL = 'https://sede.miteco.gob.es/portal/site/seMITECO/navServicioContenido'
DETAIL_URL = SEARCH_URL
TYPE_CODES = {'FTV': 'PV', 'EOL': 'WIND', 'EOM': 'WIND', 'HIB': 'HYBRID', 'ALM': 'BESS'}
# Discovery deliberately has NO state filter. Environmental procedures are not plants.
TYPE_TEXT_TO_TECH = {
    'FOTOVOLTAICOS': 'PV', 'PARQUES EOLICOS': 'WIND', 'EOLICOS MARINOS': 'WIND',
    'HIBRIDOS ENERGIAS RENOVABLES': 'HYBRID', 'ALMACENAMIENTO DE ENERGIA': 'BESS',
}
PARSER_VERSION = 'sabia-2'
FIELD_LABELS = (
    'Código de Evaluación Ambiental', 'Código para el Órgano Sustantivo', 'Título del proyecto',
    'Órgano Sustantivo', 'Promotor', 'NIF', 'CIF', 'Tipo de proyecto', 'Legislación aplicable',
    'Legislación estatal de EIA', 'Ámbito de aplicación geográfica', 'Comunidad autónoma',
    'Provincia', 'Municipio', 'Página Web', 'Medio de publicación', 'Fecha autorización',
    'Fecha publicación autorización', 'Fecha inicio ejecución proyecto', 'Estado de tramitación',
    'Fecha de entrada', 'Fecha inicio de consultas', 'Fecha de resolución',
    'Fecha de publicación en el BOE', 'Fecha del documento de alcance',
    'Sentido de la resolución', 'Estudio de impacto ambiental',
)
FIELD_RE = re.compile('|'.join(re.escape(x) + r'\s*:' for x in sorted(FIELD_LABELS, key=len, reverse=True))
                      + r'|\bDocumentación\b|\bFechas relevantes\b', re.I)


def _norm(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '')
    return re.sub(r'\s+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip().upper()


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r'\s*(\d{2}/\d{2}/\d{4})\s*', value)
    return datetime.strptime(match[1], '%d/%m/%Y').date().isoformat() if match else None


def parse_search_html(html_text: str, source_type: str | None = None) -> list[dict]:
    soup = BeautifulSoup(html_text, 'html.parser')
    text = ' '.join(soup.stripped_strings)
    if 'SE HA PRODUCIDO UN ERROR' in _norm(text):
        raise RuntimeError('SABIA application error; not an empty result')
    table = soup.find('table', id='tablaResultados')
    if table is None:
        raise RuntimeError('SABIA result table missing; not an empty result')
    # A new server-side paginator must never silently reduce coverage to page one.
    for control in soup.select('a[href], button, input[type=button]'):
        signal = ' '.join([control.get_text(' ', strip=True), str(control.get('onclick', '')),
                           str(control.get('href', '')), str(control.get('value', ''))])
        if re.search(r'\b(siguiente|anterior|next|previous|pagin\w*)\b', signal, re.I):
            raise RuntimeError('SABIA pagination detected; traversal must be implemented before certification')
    result = {}
    for tr in table.find_all('tr'):
        cells = [' '.join(td.stripped_strings) for td in tr.find_all('td')]
        if not cells:
            continue
        if len(cells) < 3 or not re.fullmatch(r'\d{8}', cells[0]) or not cells[1]:
            raise RuntimeError('Malformed SABIA result row: ' + repr(cells)[:250])
        row = dict(code=cells[0], title=cells[1], state=cells[2], source_type=source_type)
        if cells[0] in result and result[cells[0]] != row:
            raise RuntimeError('Conflicting SABIA index rows: ' + cells[0])
        result[cells[0]] = row
    return list(result.values())


def parse_detail_html(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, 'html.parser')
    text = ' '.join(soup.stripped_strings)
    fields = {}
    matches = list(FIELD_RE.finditer(text))
    for i, match in enumerate(matches):
        key = _norm(match[0].rstrip(':').strip())
        value = text[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip()
        fields.setdefault(key, value or None)
    def field(label):
        return fields.get(_norm(label))
    code = field('Código de Evaluación Ambiental')
    title = field('Título del proyecto')
    if not code or not re.fullmatch(r'\d{8}', code) or not title:
        raise ValueError('SABIA detail missing environmental code or title')
    mapping = {
        'substantive_code': 'Código para el Órgano Sustantivo', 'substantive_body': 'Órgano Sustantivo',
        'promoter': 'Promotor', 'project_type': 'Tipo de proyecto', 'ccaa': 'Comunidad autónoma',
        'province': 'Provincia', 'municipality': 'Municipio', 'state': 'Estado de tramitación',
        'resolution_sense': 'Sentido de la resolución',
    }
    detail = {key: field(label) for key, label in mapping.items()}
    detail.update(environmental_code=code, title=title, raw_text=text)
    for key, label in {'entry_date': 'Fecha de entrada', 'consultation_start': 'Fecha inicio de consultas',
                       'resolution_date': 'Fecha de resolución', 'boe_publication_date': 'Fecha de publicación en el BOE',
                       'authorization_date': 'Fecha autorización', 'execution_start': 'Fecha inicio ejecución proyecto'}.items():
        detail[key] = _iso_date(field(label))
    return detail


def _technology(detail: dict, source_type: str | None) -> str | None:
    return (TYPE_TEXT_TO_TECH.get(_norm(detail.get('project_type')))
            or TYPE_CODES.get(source_type) or detect_technology(detail.get('title') or ''))


def _explicit_multi_province(title: str) -> bool:
    text = _norm(title)
    match = re.search(r'\bPROVINCIAS\s+DE\s+([^.;]+)', text)
    if not match:
        return False
    found = {p for p in PROVINCE_TO_CCAA if re.search(r'(?<!\w)' + re.escape(_norm(p)) + r'(?!\w)', match[1])}
    return len(found) > 1


def events_from_detail(detail: dict, source_type: str | None, url: str) -> list[ParsedEvent]:
    title = detail['title']
    tech = _technology(detail, source_type)
    if tech not in {'PV', 'WIND', 'BESS', 'HYBRID'}:
        return []
    name = extract_project_name(title)
    expediente = detail.get('substantive_code') or detail['environmental_code']
    province = (detail.get('province') or '').strip() or None
    ccaa = (detail.get('ccaa') or '').strip() or None
    if _explicit_multi_province(title):
        province = None
    elif not province:
        province, fallback_ccaa = find_province(title)
        ccaa = ccaa or fallback_ccaa
    ccaa = ccaa or PROVINCE_TO_CCAA.get(province)
    common = dict(source_code='MITECO_SABIA', title=title, url=url, raw_text=detail.get('raw_text') or title,
                  technology=tech, power_mw=extract_power_mw(title), project_name=name,
                  promoter=detail.get('promoter'), expediente=expediente, province=province, ccaa=ccaa,
                  project_key=build_project_key(name, tech, province, detail['environmental_code'], expediente))
    result = []
    # These are SOURCE milestone dates, not dates of web publication. The export records their basis.
    # A resolution mentioned in a project title is NOT evidence that it was granted.
    for field, suffix, kind in (('entry_date', 'ENTRY', 'OTHER'), ('consultation_start', 'CONSULT', 'PUBLIC_INFO')):
        if detail.get(field):
            result.append(ParsedEvent(external_id=f"{detail['environmental_code']}:{suffix}",
                                      publication_date=detail[field], event_type=kind,
                                      commercial_stage=commercial_stage(kind), **common))
    return result


class SABIACollector:
    code = 'MITECO_SABIA'

    def __init__(self, timeout: int = 30, user_agent: str = 'SpainRenewablesRadar/0.2'):
        self.timeout = (10, max(timeout, 30))
        self.user_agent = user_agent
        self._candidate_rows = None
        self._details = {}
        self._events_by_date = None
        self._fatal_error = None
        self.snapshot_day = datetime.now(timezone.utc).date().isoformat()
        self.cache_dir = Path(os.getenv('SABIA_CACHE_DIR', 'data/sabia_cache')) / self.snapshot_day / PARSER_VERSION
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.audit = {'snapshot_date': self.snapshot_day, 'scope': 'ALL_STATES_ALL_FIVE_TYPES',
                      'queries': [], 'candidates': 0, 'details_ok': 0, 'detail_errors': {}, 'complete': False}

    def _session(self):
        session = requests.Session()
        session.headers['User-Agent'] = self.user_agent
        retry = Retry(total=2, connect=2, read=1, status=2, backoff_factor=1,
                      status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({'GET','POST'}))
        session.mount('https://', HTTPAdapter(max_retries=retry))
        return session

    @staticmethod
    def _write_json(path: Path, payload):
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)

    def _load_candidates(self) -> dict[str, dict]:
        if self._candidate_rows is not None:
            return self._candidate_rows
        result = {}
        for kind in TYPE_CODES:
            cached = self.cache_dir / (kind + '-index.html')
            if cached.exists():
                html_text = cached.read_text(encoding='utf-8')
            else:
                with self._session() as session:
                    r = session.get(SEARCH_URL, timeout=self.timeout); r.raise_for_status()
                    form = BeautifulSoup(r.text, 'html.parser').find('form', id='formulario')
                    if form is None:
                        raise RuntimeError('SABIA search form missing')
                    payload = {i['name']: i.get('value','') for i in form.select('input[name]') if i.get('type') == 'hidden'}
                    payload.update(accion='proy_resultados', select_tipo=kind, select_estado_tramitacion='',
                                   select_comunidades='', codigo='', titulo='', select_organo_sustantivo='', select_promotor='')
                    r = session.post(SEARCH_URL, data=payload, timeout=(10,60)); r.raise_for_status()
                    html_text = r.text
            rows = parse_search_html(html_text, kind)
            if not rows:
                raise RuntimeError('Unexpected zero SABIA inventory for type ' + kind)
            cached.write_text(html_text, encoding='utf-8')
            self.audit['queries'].append({'type':kind, 'state_filter':None, 'rows':len(rows),
                                          'sha256':hashlib.sha256(html_text.encode()).hexdigest()})
            for row in rows:
                if row['code'] in result and result[row['code']]['title'] != row['title']:
                    raise RuntimeError('Conflicting cross-type index record ' + row['code'])
                result[row['code']] = row
            print(f'SABIA index {kind}: {len(rows)} records', flush=True)
        self._candidate_rows = result
        self.audit['candidates'] = len(result)
        self._write_json(self.cache_dir / 'inventory.json', list(result.values()))
        return result

    def _detail(self, code: str) -> tuple[dict, str]:
        cached = self.cache_dir / (code + '.json')
        if cached.exists():
            value = json.loads(cached.read_text(encoding='utf-8'))
            if value['detail']['environmental_code'] != code:
                raise RuntimeError('Invalid cached SABIA identity: ' + code)
            return value['detail'], value['url']
        with self._session() as session:
            r = session.get(DETAIL_URL, params={'accion':'proy_detalle', 'codigo_seleccionado':code,
                                                'id_pagina_cargada':'RESULTADOS'}, timeout=self.timeout)
            r.raise_for_status()
            detail = parse_detail_html(r.text)
            if detail['environmental_code'] != code:
                raise RuntimeError('SABIA identity mismatch: ' + code)
            (self.cache_dir / (code + '.html')).write_text(r.text, encoding='utf-8')
            self._write_json(cached, {'detail': detail, 'url': r.url,
                                     'retrieved_at': datetime.now(timezone.utc).isoformat(),
                                     'sha256': hashlib.sha256(r.content).hexdigest()})
            return detail, r.url

    def _build_cache(self):
        if self._events_by_date is not None:
            return
        if self._fatal_error:
            raise RuntimeError(self._fatal_error)
        report = Path('reports/sabia'); report.mkdir(parents=True, exist_ok=True)
        try:
            candidates = self._load_candidates()
            errors = {}
            workers = min(4, max(1, int(os.getenv('SABIA_WORKERS', '4'))))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                pending = {pool.submit(self._detail, code):code for code in sorted(candidates, reverse=True)}
                for future in as_completed(pending):
                    code = pending[future]
                    try:
                        self._details[code] = future.result()
                    except Exception as exc:
                        errors[code] = str(exc)[:500]
                    finished = len(self._details) + len(errors)
                    if finished % 100 == 0:
                        print(f'SABIA details: {finished}/{len(candidates)}, errors={len(errors)}', flush=True)
            # Retry only failed identities, never restart every source day.
            for code in list(errors):
                try:
                    self._details[code] = self._detail(code)
                    del errors[code]
                except Exception as exc:
                    errors[code] = str(exc)[:500]
            self.audit.update(details_ok=len(self._details), detail_errors=errors)
            if errors:
                raise RuntimeError(f'SABIA incomplete detail coverage: {len(errors)}/{len(candidates)}')
            events_by_date = {}
            date_basis = []
            for code in sorted(candidates):
                detail, url = self._details[code]
                for event in events_from_detail(detail, candidates[code]['source_type'], url):
                    events_by_date.setdefault(event.publication_date, []).append(event)
                    date_basis.append({'external_id':event.external_id, 'project_key':event.project_key,
                                       'event_date':event.publication_date, 'date_basis': 'ENTRY_DATE' if event.external_id.endswith(':ENTRY') else 'CONSULTATION_START',
                                       'source_current_state':detail.get('state'), 'environmental_code':code,
                                       'source_url':url, 'web_publication_date':None})
            self._write_json(report / 'date_basis.json', date_basis)
            self.audit['complete'] = True
            self._events_by_date = events_by_date
        except Exception as exc:
            self._fatal_error = str(exc)
            raise
        finally:
            self._write_json(report / 'coverage.json', self.audit)

    def collect_day(self, day: date):
        self._build_cache()
        return list(self._events_by_date.get(day.isoformat(), []))
