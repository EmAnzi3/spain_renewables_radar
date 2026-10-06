from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.geo import PROVINCE_TO_CCAA, find_province
from app.collectors.sabia_assets import parse_assets, source_provinces, component_key, write_event_metadata
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
PARSER_VERSION = 'sabia-3'
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
        value = ' '.join(text[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)].split())
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
    assets = parse_assets(title)
    reference = detail.get('substantive_code') or detail['environmental_code']
    provinces = source_provinces(detail)
    province = provinces[0] if len(provinces) == 1 else None
    communities = {PROVINCE_TO_CCAA[p] for p in provinces}
    ccaa = next(iter(communities)) if len(communities) == 1 else None
    if not provinces:
        province, ccaa = find_province(title)
    result = []
    for asset in assets:
        key = (component_key(reference, asset) if len(assets) > 1 else
               build_project_key(asset.name, tech, province, detail['environmental_code'], reference))
        component_suffix = ':' + component_key(reference, asset) if len(assets) > 1 else ''
        common = dict(source_code='MITECO_SABIA', title=title, url=url,
                      raw_text=detail.get('raw_text') or title, technology=tech,
                      power_mw=asset.power_mw, project_name=asset.name,
                      promoter=detail.get('promoter'), expediente=reference,
                      province=province, ccaa=ccaa, project_key=key)
        # Dates are source milestones, never invented web publication dates.
        for field, suffix, kind in (('entry_date', 'ENTRY', 'OTHER'), ('consultation_start', 'CONSULT', 'PUBLIC_INFO')):
            if detail.get(field):
                result.append(ParsedEvent(external_id=f"{detail['environmental_code']}:{suffix}{component_suffix}",
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
        self._force_codes = set()
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

    def _fetch_index_html(self, kind: str) -> str:
        """One bounded budget for complete GET-form/POST-result transactions.

        requests may time out while consuming a response body after urllib3 has
        handed it back. The HTTP adapter cannot reliably retry that read. Retry
        the whole read-only search once, with a fresh anonymous form/session.
        No retry for TLS, denial, rate limits, malformed HTML or source semantics.
        """
        attempts=self.audit.setdefault('index_attempts', [])
        for number in (1,2):
            audit={'type':kind,'attempt':number,'started_at':datetime.now(timezone.utc).isoformat(),
                   'completed':False,'responses':[]}
            attempts.append(audit)
            try:
                with self._session() as session:
                    # No nested adapter retries: this method owns the total budget.
                    session.mount('https://',HTTPAdapter(max_retries=0))
                    def request(method, **kwargs):
                        audit['stage']=method
                        response=None
                        try:
                            response=getattr(session,method)(SEARCH_URL, timeout=(10,60), **kwargs)
                            response.raise_for_status()
                            if response.status_code!=200:raise RuntimeError('Unexpected SABIA index response')
                            raw=response.content
                            if len(raw)>20_000_000:raise RuntimeError('SABIA index response exceeds limit')
                            filename=kind+'-'+uuid.uuid4().hex+'-'+method+'-raw.html'
                            (self.cache_dir/filename).write_bytes(raw)
                            audit['responses'].append({'method':method.upper(),'endpoint':response.url,
                                'retrieved_at':datetime.now(timezone.utc).isoformat(),
                                'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'file':filename})
                            return response.text
                        finally:
                            if response is not None:response.close()
                    page=request('get')
                    form=BeautifulSoup(page,'html.parser').find('form',id='formulario')
                    if form is None:raise RuntimeError('SABIA search form missing')
                    payload={i['name']:i.get('value','') for i in form.select('input[name]') if i.get('type')=='hidden'}
                    payload.update(accion='proy_resultados',select_tipo=kind,select_estado_tramitacion='',
                                   select_comunidades='',codigo='',titulo='',select_organo_sustantivo='',select_promotor='')
                    html_text=request('post',data=payload)
                    if not parse_search_html(html_text,kind):raise RuntimeError('Unexpected zero SABIA inventory for type '+kind)
                    audit['completed']=True
                    return html_text
            except Exception as exc:
                audit.update(error_type=type(exc).__name__,error=str(exc)[:500])
                status=getattr(getattr(exc,'response',None),'status_code',None)
                transient=(isinstance(exc,(requests.ConnectionError,requests.Timeout,requests.exceptions.ChunkedEncodingError))
                           or isinstance(exc,requests.HTTPError) and status in (500,502,503,504))
                if isinstance(exc,requests.exceptions.SSLError) or not transient or number==2:
                    raise
                print(f'SABIA index {kind}: transient {type(exc).__name__}; retrying complete search once',flush=True)
                time.sleep(2)
            finally:
                audit['finished_at']=datetime.now(timezone.utc).isoformat()
                self._write_json(self.cache_dir/'index_attempts.json',attempts)
        raise RuntimeError('Unreachable SABIA retry state')

    def _load_candidates(self) -> dict[str, dict]:
        if self._candidate_rows is not None:
            return self._candidate_rows
        result = {}
        for kind in TYPE_CODES:
            cached = self.cache_dir / (kind + '-index.html')
            if cached.exists():
                html_text = cached.read_text(encoding='utf-8')
            else:
                html_text = self._fetch_index_html(kind)
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
        raw_path = self.cache_dir / (code + '.html')
        force_codes = self._force_codes | set(os.getenv('SABIA_FORCE_DETAIL_CODES', '').split(','))
        if cached.exists() and raw_path.exists() and code not in force_codes:
            value = json.loads(cached.read_text(encoding='utf-8'))
            retrieved = datetime.fromisoformat(value['retrieved_at'])
            age = (datetime.now(timezone.utc) - retrieved).total_seconds()
            raw_html = raw_path.read_text(encoding='utf-8')
            digest_ok = hashlib.sha256(raw_path.read_bytes()).hexdigest() == value.get('sha256')
            detail = parse_detail_html(raw_html)
            candidate = (self._candidate_rows or {}).get(code, {})
            compatible = (not candidate or (_norm(candidate['title']) == _norm(detail['title'])
                           and _norm(candidate['state']) == _norm(detail.get('state'))))
            if detail['environmental_code'] == code and compatible and digest_ok and 0 <= age < 86400:
                detail['retrieved_at'] = value['retrieved_at']
                detail['cache_reused'] = True
                return detail, value['url']
        with self._session() as session:
            params = {'accion':'proy_detalle', 'codigo_seleccionado':code, 'id_pagina_cargada':'RESULTADOS'}
            method = 'OFFICIAL_GET'
            try:
                r = session.get(DETAIL_URL, params=params, timeout=self.timeout)
                r.raise_for_status()
                detail = parse_detail_html(r.text)
                if detail['environmental_code'] != code:
                    raise ValueError('SABIA identity mismatch: ' + code)
            except (requests.RequestException, ValueError):
                # Some records require SABIA's session/form navigation, not a direct link.
                featured = 'https://sede.miteco.gob.es/portal/site/seMITECO/template.PAGE/navSabiaDestacados/navServicioContenido'
                def payload(response):
                    response.raise_for_status()
                    form = BeautifulSoup(response.text, 'html.parser').find('form', id='formulario')
                    if form is None:
                        raise ValueError('SABIA navigation form missing')
                    return {i['name']: i.get('value','') for i in form.select('input[name]') if i.get('type') == 'hidden'}
                data = payload(session.get(featured, timeout=self.timeout))
                data.update(accion='ea_detalle', codigo_seleccionado=code, id_pagina_cargada='DESTACADOS')
                data = payload(session.post(featured, data=data, timeout=self.timeout))
                if data.get('codigo_seleccionado') != code:
                    raise ValueError('SABIA intermediate identity mismatch: ' + code)
                data.update(accion='proy_detalle', codigo_seleccionado=code)
                r = session.post(featured, data=data, timeout=self.timeout)
                r.raise_for_status()
                detail = parse_detail_html(r.text)
                method = 'OFFICIAL_FORM_POST'
            if detail['environmental_code'] != code:
                raise RuntimeError('SABIA identity mismatch: ' + code)
            from urllib.parse import urlencode
            url = DETAIL_URL + '?' + urlencode(params)
            retrieved = datetime.now(timezone.utc).isoformat()
            detail['retrieved_at'] = retrieved
            detail['cache_reused'] = False
            raw_path.write_text(r.text, encoding='utf-8')
            self._write_json(cached, {'detail': detail, 'url': url, 'retrieved_at': retrieved,
                                     'retrieval_method': method, 'request_endpoint': r.url,
                                     'sha256': hashlib.sha256(r.content).hexdigest()})
            return detail, url

    def persist_metadata(self, conn):
        if self._details and self._candidate_rows:
            write_event_metadata(conn, self._details, self._candidate_rows, events_from_detail)

    def _build_cache(self):
        if self._events_by_date is not None:
            return
        if self._fatal_error:
            raise RuntimeError(self._fatal_error)
        report = Path('reports/sabia'); report.mkdir(parents=True, exist_ok=True)
        try:
            candidates = self._load_candidates()
            if os.getenv('SABIA_FORCE_LIVE_SAMPLE') == '1':
                for kind in TYPE_CODES:
                    codes=[code for code,row in candidates.items() if row['source_type']==kind]
                    if codes:self._force_codes.add(max(codes))
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
            dates = sorted(d[0].get('retrieved_at','') for d in self._details.values())
            self.audit.update(details_ok=len(self._details), detail_errors=errors,
                              detail_cache_reused=sum(bool(d[0].get('cache_reused')) for d in self._details.values()),
                              detail_retrieval_oldest=dates[0] if dates else None,
                              detail_retrieval_newest=dates[-1] if dates else None,
                              detail_cache_max_age_seconds=86400)
            if errors:
                raise RuntimeError(f'SABIA incomplete detail coverage: {len(errors)}/{len(candidates)}')
            events_by_date = {}
            date_basis = []
            for code in sorted(candidates):
                detail, url = self._details[code]
                for event in events_from_detail(detail, candidates[code]['source_type'], url):
                    events_by_date.setdefault(event.publication_date, []).append(event)
                    date_basis.append({'external_id':event.external_id, 'project_key':event.project_key,
                                       'event_date':event.publication_date, 'date_basis': 'ENTRY_DATE' if ':ENTRY' in event.external_id else 'CONSULTATION_START',
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
