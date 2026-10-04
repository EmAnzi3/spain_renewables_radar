"""Read-only exploration of the DOGC's observed public service contracts.

No project/event is inserted. This probe deliberately does not certify coverage.
Service host and routes were read from the official linked scripts and inputs.
"""
from __future__ import annotations
import hashlib
import json
import re
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo
import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

OUT = Path('reports/dogc_contract_probe')
WEB = 'https://dogc.gencat.cat'
SERVICE = 'https://portaldogc.gencat.cat'
ROUTES = {'calendarDOGC', 'summaryDOGC', 'summaryLastPublishedDOGC', 'searchDOGC'}


class VerifiedDOGCTLSAdapter(HTTPAdapter):
    """Observed server cipher compatibility; hostname and CA checks stay enabled."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers('DEFAULT:!aNULL:!eNULL:!EXPORT:!RC4:!3DES:@SECLEVEL=2')
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)


def compact(value):
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items()}
    if isinstance(value, list):
        return {'length': len(value), 'first': [compact(v) for v in value[:3]]}
    return value[:1800] if isinstance(value, str) else value


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.mount(SERVICE + '/', VerifiedDOGCTLSAdapter())
    session.headers['User-Agent'] = 'SpainRenewablesRadar/0.6 (public read-only source verification)'
    acquisitions, failures = [], []

    def request(url, *, form=None, payload=None):
        method = 'POST' if form is not None or payload is not None else 'GET'
        for _ in range(4):
            p = urlsplit(url)
            if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
                raise ValueError('Non-public destination')
            if method == 'POST':
                if p.hostname != 'portaldogc.gencat.cat' or p.path not in {'/eadop-rest/api/dogc/' + x for x in ROUTES}:
                    raise ValueError('Not an observed read-only service operation')
            elif p.hostname != 'dogc.gencat.cat':
                raise ValueError('Unapproved public document destination')
            response = session.request(method, url, data=form, json=payload, timeout=(8, 45), allow_redirects=False, stream=True)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('Location'); response.close()
                if method != 'GET' or not location:
                    raise ValueError('Unexpected service redirect')
                url = urljoin(url, location); continue
            try:
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 6_000_000:
                        raise ValueError('Response exceeds probe limit')
                    chunks.append(chunk)
                raw = b''.join(chunks); sha = hashlib.sha256(raw).hexdigest()
                (OUT / (sha + '.bin')).write_bytes(raw)
                acquisitions.append({'url': url, 'method': method, 'parameters': form if form is not None else payload,
                                     'status': response.status_code, 'sha256': sha, 'bytes': size,
                                     'retrieved_at': datetime.now(timezone.utc).isoformat()})
                print('ACQUISITION', json.dumps(acquisitions[-1], ensure_ascii=False), flush=True)
                response.raise_for_status()
                return raw
            finally:
                response.close()
        raise ValueError('Too many public document redirects')

    try:
        home = WEB + '/ca/inici/'
        soup = BeautifulSoup(request(home), 'html.parser')
        config = {t.get('id'): t.get('value') for t in soup.select('input[id]')}
        scripts = {Path(urlsplit(urljoin(home, t['src'])).path).name: urljoin(home, t['src']) for t in soup.select('script[src]')}
        constants = request(scripts['constants.js']).decode('utf-8')
        host = re.search(r'\bHOST_PRO\s*=\s*[\x27\x22]([^\x27\x22]+)', constants)
        if not host or host[1] != 'portaldogc.gencat.cat':
            raise ValueError('Public production service host changed')
        for field, expected in [('uriCalendar', 'calendarDOGC'), ('uriCerDogc', 'searchDOGC'), ('uriUltimDOGCPublicat', 'summaryLastPublishedDOGC')]:
            if config.get(field) != '/eadop-rest/api/dogc/' + expected:
                raise ValueError('Public route contract changed: ' + field)
        text = request(scripts['fpca_calendari_dogc.js']).decode('utf-8')
        print('CALENDAR_MONTH_CONTRACT', json.dumps([line.strip() for line in text.splitlines() if 'selectedMonth' in line or 'getMonth' in line]))
        end = datetime.now(ZoneInfo('Europe/Madrid')).date() - timedelta(days=1)
        start = end - timedelta(days=29)
        for year, month in sorted({(start.year, start.month), (end.year, end.month)}):
            raw = request(SERVICE + config['uriCalendar'], form={'month': month, 'year': year, 'language': 'ca'})
            data = json.loads(raw)
            (OUT / f'calendar-{year}-{month}.json').write_bytes(raw)
            print('CALENDAR_RESPONSE', json.dumps(data, ensure_ascii=False), flush=True)
            if not isinstance(data, dict) or not isinstance(data.get('calendar'), list):
                raise ValueError('Invalid calendar response')
        raw = request(SERVICE + config['uriUltimDOGCPublicat'], form={'language': 'ca'})
        latest = json.loads(raw)
        print('LATEST_RESPONSE', json.dumps(compact(latest), ensure_ascii=False), flush=True)
        if not latest.get('sumaris'):
            raise ValueError('No latest edition returned')
        edition = latest['sumaris'][0]['numDOGC']
        raw = request(SERVICE + '/eadop-rest/api/dogc/summaryDOGC', form={'numDOGC': edition, 'language': 'ca'})
        summary = json.loads(raw)
        (OUT / 'edition-sample.json').write_bytes(raw)
        print('EDITION_RESPONSE', json.dumps(compact(summary), ensure_ascii=False), flush=True)
        payload = {'typeSearch': '1', 'value': '', 'title': False, 'current': False, 'range': [], 'issuingAuthority': [],
                   'publicationDateInitial': start.strftime('%d/%m/%Y'), 'publicationDateFinal': end.strftime('%d/%m/%Y'),
                   'dispositionDateInitial': '', 'dispositionDateFinal': '', 'sectionDOGC': [], 'thematicDescriptor': [],
                   'organizationDescriptor': [], 'geographicDescriptor': [], 'aranese': False, 'expandSearchFullText': False,
                   'noCurrent': False, 'orderBy': '3', 'page': '1', 'numResultsByPage': '50', 'advanced': True, 'language': 'ca'}
        raw = request(SERVICE + config['uriCerDogc'], payload=payload)
        data = json.loads(raw)
        (OUT / 'search-sample.json').write_bytes(raw)
        print('SEARCH_RESPONSE', json.dumps(compact(data), ensure_ascii=False), flush=True)
        if not isinstance(data.get('resultSearch'), list) or 'numResultSearch' not in data:
            raise ValueError('Invalid search response')
        print('SEARCH_ENERGY_SAMPLE', json.dumps([r for r in data['resultSearch'] if re.search(r'fotovolta|e[oò]lic|bateri|emmagatzem|hibrid', r.get('title', ''), re.I)], ensure_ascii=False), flush=True)
        result = {'service_responses_observed': True, 'window_start': str(start), 'window_end': str(end),
                  'search_count': data['numResultSearch'], 'search_rows_downloaded': len(data['resultSearch']),
                  'collector_implemented': False, 'backfill_certified': False}
        (OUT / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        failures.append({'type': type(exc).__name__, 'error': str(exc)})
        raise
    finally:
        (OUT / 'acquisitions.json').write_text(json.dumps(acquisitions, ensure_ascii=False, indent=2), encoding='utf-8')
        (OUT / 'failures.json').write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
