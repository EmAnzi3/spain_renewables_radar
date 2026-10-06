"""Bounded official BOPV navigation probe; never a coverage certificate."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urljoin, urldefrag
from zoneinfo import ZoneInfo
import hashlib
import json
import re

import requests
from bs4 import BeautifulSoup

ORIGIN = 'https://www.euskadi.eus/bopv2/datos/Ultimo.shtml'


def allowed(url):
    p = urlsplit(url)
    return (p.scheme == 'https' and p.hostname == 'www.euskadi.eus'
            and p.port in (None, 443) and not p.username and not p.password)


def form_fields(form):
    fields = []
    for tag in form.select('input,select,button'):
        options = [{'value': o.get('value'), 'text': o.get_text(' ', strip=True),
                    'selected': o.has_attr('selected')} for o in tag.select('option')]
        fields.append({'name': tag.get('name'), 'type': tag.get('type'),
                       'value': tag.get('value'), 'checked': tag.has_attr('checked'),
                       'options': options})
    return fields



def result_page(soup, number, start, end, expected_total=None):
    form = soup.find('form', id='formularioID') or soup.find('form', attrs={'name': 'avanzada'})
    if form is None:
        raise ValueError('Search result form missing')
    payload = {i['name']: i.get('value', '') for i in form.select('input[type=hidden][name]')}
    total_text = payload.get('numeroRegistrosEncontrados', '')
    if not total_text.isdecimal() or not 0 < int(total_text) < 1000:
        raise ValueError('Search total absent, empty or beyond verified service limit')
    total = int(total_text)
    if expected_total is not None and total != expected_total:
        raise ValueError('Search total changed during pagination')
    expected = {'paginaActual': str(number), 'numeroRegistrosPagina': '10',
                'buscarPorFechaBoletin': 'true', 'tipoBusquedaFecha': '5',
                'desdeFechaBoletin': start.strftime('%d/%m/%Y'),
                'hastaFechaBoletin': end.strftime('%d/%m/%Y'),
                'textoTitulo': '', 'textoDisposicion': ''}
    if any(payload.get(k) != v for k, v in expected.items()):
        raise ValueError('Pagination altered the original date-search scope')
    rows = []
    for paragraph in soup.find_all('p', id=re.compile(r'^parrafo\d+$')):
        links = paragraph.find_all('a', onclick=True)
        if len(links) != 1:
            raise ValueError('Ambiguous disposition link')
        link = links[0]
        match = re.fullmatch(r"return cargarDisposicion\('([^']+)',\s*\d+\);", link['onclick'])
        identity = link.get_text(' ', strip=True)
        if not match or not re.fullmatch(r'\d{4}/\d{5}', identity):
            raise ValueError('Unrecognized official disposition identity')
        url = urljoin(ORIGIN, match[1])
        path = re.fullmatch(r'/web01-bopv/es/bopv2/datos/(\d{4})/(\d{2})/(\d{2})(\d{5})a\.shtml', urlsplit(url).path)
        if not allowed(url) or not path or identity != path[1] + '/' + path[4] or path[1][2:] != path[3]:
            raise ValueError('Disposition identifier differs from source URL')
        cleaned = BeautifulSoup(str(paragraph), 'html.parser')
        for tag in cleaned.select('script,a'):
            tag.decompose()
        title = cleaned.get_text(' ', strip=True)
        if not title:
            raise ValueError('Missing disposition title')
        rows.append({'external_id': identity, 'source_url': url, 'title': title,
                     'publication_date': None, 'date_basis': 'SEARCH_WINDOW_ONLY_PENDING_DOCUMENT_HEADER'})
    remaining = total - (number - 1) * 10
    if not 1 <= remaining or len(rows) != min(10, remaining):
        raise ValueError('Incomplete or wrong result page')
    if len({r['external_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate source identity within page')
    page_count = (total + 9) // 10
    max_pages = {int(t['data-max-page']) for t in soup.select('[data-max-page]')}
    if max_pages != {page_count}:
        raise ValueError('Paginator disagrees with declared source count')
    return rows, total, page_count, form, payload


def main():
    root = Path('reports/bopv_date_probe')
    (root / 'raw').mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers['User-Agent'] = 'SpainRenewablesRadar/0.7 (official dated-index probe)'
    acquisitions, pages = [], []
    end = datetime.now(ZoneInfo('Europe/Madrid')).date() - timedelta(days=1)
    start = end - timedelta(days=29)
    result = {'source_code': 'BOPV', 'window_start': str(start), 'window_end': str(end),
              'collector_implemented': False, 'events_created': 0, 'complete_coverage_certified': False}

    def request(label, url, data=None):
        for hop in range(3):
            if not allowed(url):
                raise ValueError('Unverified destination')
            meta = {'label': label, 'url': url, 'method': 'POST' if data is not None else 'GET',
                    'started_at': datetime.now(timezone.utc).isoformat()}
            acquisitions.append(meta)
            with session.request(meta['method'], url, data=data, timeout=(15, 45),
                                 allow_redirects=False, stream=True) as response:
                meta['status'] = response.status_code
                if 300 <= response.status_code < 400:
                    target = urljoin(url, response.headers.get('Location', ''))
                    meta['location'] = target
                    if not allowed(target) or target == url:
                        raise ValueError('Unexpected redirect')
                    if response.status_code in (301, 302, 303):
                        data = None
                    url = target
                    continue
                response.raise_for_status()
                if response.status_code != 200 or 'html' not in response.headers.get('Content-Type', '').lower():
                    raise ValueError('Expected original HTML')
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 5_000_000:
                        raise ValueError('Bounded HTML limit exceeded')
                    chunks.append(chunk)
                raw = b''.join(chunks)
                sha = hashlib.sha256(raw).hexdigest()
                (root / 'raw' / (sha + '.html')).write_bytes(raw)
                encoding = response.encoding or 'utf-8'
                meta.update(sha256=sha, bytes=len(raw), encoding=encoding,
                            retrieved_at=datetime.now(timezone.utc).isoformat())
                soup = BeautifulSoup(raw.decode(encoding, errors='strict'), 'html.parser')
                links = [{'text': a.get_text(' ', strip=True),
                          'url': urldefrag(urljoin(url, a['href']))[0]}
                         for a in soup.select('a[href]') if allowed(urljoin(url, a['href']))]
                forms = [{'action': urljoin(url, f.get('action') or ''), 'method': f.get('method'),
                          'name': f.get('name'), 'fields': form_fields(f)} for f in soup.select('form')]
                text = '\n'.join(soup.stripped_strings)
                page = {'label': label, 'url': url, 'sha256': sha, 'text': text,
                        'links': links, 'forms': forms,
                        'headings': [h.get_text(' ', strip=True) for h in soup.select('h1,h2,h3')]}
                pages.append(page)
                print('BOPV_DATE_PAGE', json.dumps(dict(page, text=text[:1800], links=links[:65]), ensure_ascii=False), flush=True)
                return soup, page
        raise ValueError('Redirect budget exhausted')

    try:
        home, home_info = request('home', ORIGIN)
        calendars = re.findall(r"src=['\"](/bopv2/datos/Cal[^'\"]+)", str(home))
        if not calendars:
            raise ValueError('Observed calendar embed missing')
        _, calendar = request('calendar', urljoin(ORIGIN, calendars[0]))
        previous = [x for x in calendar['links'] if re.search(r'anterior|prev|septiembre', x['text'], re.I)]
        for index, item in enumerate(previous[:2]):
            request('previous-calendar-' + str(index), item['url'])
        searches = [x for x in home_info['links'] if x['text'] == 'Consulta avanzada']
        if len(searches) != 1:
            raise ValueError('Ambiguous advanced search navigation')
        soup, page = request('form', searches[0]['url'])
        form = soup.find('form', id='formularioID')
        if form is None:
            raise ValueError('Official date-search form missing')
        payload = {i['name']: i.get('value', '') for i in form.select('input[type=hidden][name]')}
        for select in form.select('select[name]'):
            option = select.find('option', selected=True) or select.find('option')
            if option is not None:
                payload[select['name']] = option.get('value', '')
        payload.update(buscarPorFechaBoletin='true', tipoBusquedaFecha='5',
                       desdeFechaBoletin=start.strftime('%d/%m/%Y'),
                       hastaFechaBoletin=end.strftime('%d/%m/%Y'),
                       textoTitulo='', textoDisposicion='', submit='Buscar')
        for key in ('buscarPorNumeroBoletin', 'buscarPorDisposicion', 'buscarPorAnoNumeroDisposicion', 'buscarPorFechaDisposicion'):
            payload.pop(key, None)
        result['date_search_parameters'] = {k: v for k, v in payload.items() if 'fecha' in k.lower() or k.startswith('texto')}
        found, found_page = request('publication-window-search', urljoin(page['url'], form.get('action') or ''), payload)
        for tag in found.select('a,input,button'):
            signal = ' '.join(str(v) for v in tag.attrs.values()) + ' ' + tag.get_text(' ', strip=True)
            if re.search(r'pagin|siguiente|anterior|orden|encontrad|resultado|recuperad', signal, re.I):
                print('BOPV_RESULT_CONTROL', json.dumps({'tag': tag.name, 'attrs': tag.attrs,
                      'text': tag.get_text(' ', strip=True)}, ensure_ascii=False), flush=True)
        rows, total, page_count, page_form, parameters = result_page(found, 1, start, end)
        inventory = {row['external_id']: row for row in rows}
        for number in range(2, page_count + 1):
            parameters.update(paginaActual=str(number), submit='Paginar')
            target = urljoin(found_page['url'], page_form.get('action') or '')
            found, found_page = request('results-page-' + str(number), target, parameters)
            rows, _, _, page_form, parameters = result_page(found, number, start, end, total)
            if set(inventory).intersection(row['external_id'] for row in rows):
                raise ValueError('Overlapping result pages; no silent deduplication')
            inventory.update({row['external_id']: row for row in rows})
        if len(inventory) != total:
            raise ValueError('Full result inventory does not match declared count')
        (root / 'window_index.json').write_text(json.dumps(list(inventory.values()), ensure_ascii=False, indent=2), encoding='utf-8')
        candidates = [row for row in inventory.values() if re.search(r'fotovolta|e[oó]lic|almacenamiento|bater[ií]a|hibrid', row['title'], re.I)]
        (root / 'title_candidates.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding='utf-8')
        for candidate in candidates[:6]:
            request('candidate-' + candidate['external_id'].replace('/', '-'), candidate['source_url'])
        result.update(probe_success=True, pages_acquired=len(pages), search_response_received=True,
                      search_pages_verified=page_count, declared_dispositions=total, unique_index_dispositions=len(inventory),
                      title_candidates=len(candidates), candidate_bodies_sampled=min(len(candidates), 6),
                      search_pagination_complete=True, individual_publication_dates_verified=False)

    except Exception as exc:
        result.update(probe_success=False, error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        session.close()
        for filename, value in [('acquisitions.json', acquisitions), ('pages.json', pages), ('probe.json', result)]:
            (root / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        print('BOPV_DATE_PROBE_RESULT', json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
