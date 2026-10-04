"""Reconcile the complete dated DOGC index via two official read-only routes.

This is index acquisition, not a project collector: document bodies are not read,
project/lifecycle fields are not inferred, and nothing is inserted into the radar.
"""
from __future__ import annotations
import argparse
import calendar
import hashlib
import html
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from app.catalunya_inventory import atomic_json, canonical
from scripts.probe_dogc_services import SERVICE, WEB, VerifiedDOGCTLSAdapter

PAGE_SIZE = 50
ENERGY = re.compile(r'fotovolta|e[oòó]lic|\bbess\b|bateri|emmagatzem|almacenamiento|hibrid', re.I)


def source_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{2}/\d{2}/\d{4}', value):
        raise ValueError('Unrecognized official publication date')
    return datetime.strptime(value, '%d/%m/%Y').date()


def plain_title(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing official disposition title')
    title = ' '.join(BeautifulSoup(value, 'html.parser').get_text(' ', strip=True).split())
    if not title:
        raise ValueError('Disposition title contains no readable text')
    return title


def one_parameter(url, name):
    values = parse_qs(urlsplit(url).query).get(name, [])
    if len(values) != 1 or not re.fullmatch(r'\d+', values[0]):
        raise ValueError('Missing or ambiguous source identifier: ' + name)
    return values[0]


def parse_calendar(data, year, month):
    rows = data.get('calendar') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError('Calendar is not a valid source response')
    days = {}
    for row in rows:
        day = source_date(row['date'])
        if (day.year, day.month) != (year, month) or day in days or type(row.get('hasDOGC')) is not bool:
            raise ValueError('Wrong month, repeated day or invalid publication flag')
        link = row.get('linkDOGC')
        if row['hasDOGC']:
            if not isinstance(link, str) or not link.startswith('?'):
                raise ValueError('Edition missing its official calendar link')
            if int(one_parameter(link, 'selectedYear')) != year or int(one_parameter(link, 'selectedMonth')) != month:
                raise ValueError('Calendar link disagrees with requested month')
            days[day] = one_parameter(link, 'numDOGC')
        else:
            if link is not None:
                raise ValueError('No-publication flag contradicts edition link')
            days[day] = None
    expected = {date(year, month, n) for n in range(1, calendar.monthrange(year, month)[1] + 1)}
    if set(days) != expected:
        raise ValueError('Incomplete official monthly calendar')
    return days


def summary_scopes(data, edition, day):
    """Principal edition plus explicitly identified same-day official annexes."""
    summaries = data.get('sumaris') if isinstance(data, dict) else None
    if not isinstance(summaries, list) or not summaries or not re.fullmatch(r'\d+', edition):
        raise ValueError('Edition summary is missing or has an invalid base identity')
    seen = set()
    scopes = []
    for summary in summaries:
        if not isinstance(summary, dict):
            raise ValueError('Invalid edition header')
        identity = summary.get('numDOGC')
        if not isinstance(identity, str) or identity in seen or source_date(summary.get('dateDOGC')) != day:
            raise ValueError('Repeated edition identity or publication date differs from calendar')
        if identity != edition:
            suffix = identity[len(edition):] if identity.startswith(edition) else ''
            if not re.fullmatch(r'[A-Z]', suffix) or summary.get('title') != 'Annex ' + suffix:
                raise ValueError('Unrelated edition cannot be included as an annex')
        # Both identity and attachment link must corroborate the source scope.
        url = summary.get('linkDownloadDOGCPDF')
        if not isinstance(url, str):
            raise ValueError('Edition lacks its original download identity')
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.hostname != 'portaldogc.gencat.cat'
                or parts.username or parts.password or parts.port not in (None, 443)
                or parts.path != '/utilsEADOP/AppJava/PdfProviderServlet'
                or parse_qs(parts.query).get('dogcId') != [identity]):
            raise ValueError('Original download link disagrees with edition or annex identity')
        if not isinstance(summary.get('section'), list) or not summary['section']:
            raise ValueError('Edition has no section structure')
        seen.add(identity)
        scopes.append((identity, summary))
    if edition not in seen:
        raise ValueError('Annex-only response cannot replace the requested principal edition')
    return scopes


def parse_summary(data, edition, day):
    result = {}
    def walk(node, scope):
        if isinstance(node, list):
            for child in node: walk(child, scope)
        elif isinstance(node, dict):
            if 'linkDownloadDocumentPDF' in node:
                url = node['linkDownloadDocumentPDF']; p = urlsplit(url)
                if (p.scheme != 'https' or p.hostname != 'portaldogc.gencat.cat' or p.username or p.password
                        or p.port not in (None, 443) or p.path != '/utilsEADOP/AppJava/PdfProviderServlet'):
                    raise ValueError('Unrecognized official document link')
                identity = one_parameter(url, 'documentId')
                record = {'document_id': identity, 'publication_date': day.isoformat(), 'edition': scope,
                          'base_edition': edition, 'edition_kind': 'PRINCIPAL' if scope == edition else 'ANNEX',
                          'title': plain_title(node.get('title')), 'source_title': node['title'],
                          'source_url': url, 'body_acquired': False}
                key = (identity, day.isoformat())
                if key in result and result[key] != record:
                    raise ValueError('Conflicting disposition identity across edition scopes')
                result[key] = record
            for value in node.values():
                if isinstance(value, (list, dict)): walk(value, scope)
    for scope, summary in summary_scopes(data, edition, day):
        walk(summary['section'], scope)
    if not result:
        raise ValueError('Published edition has no identifiable dispositions')
    return result


def search_parameters(start, end, page):
    return {'typeSearch': '1', 'value': '', 'title': False, 'current': False,
            'range': [], 'issuingAuthority': [], 'publicationDateInitial': start.strftime('%d/%m/%Y'),
            'publicationDateFinal': end.strftime('%d/%m/%Y'), 'dispositionDateInitial': '',
            'dispositionDateFinal': '', 'sectionDOGC': [], 'thematicDescriptor': [],
            'organizationDescriptor': [], 'geographicDescriptor': [], 'aranese': False,
            'expandSearchFullText': False, 'noCurrent': False, 'orderBy': '3', 'page': str(page),
            'numResultsByPage': str(PAGE_SIZE), 'advanced': True, 'language': 'ca'}


def parse_search(data, start, end, page):
    if not isinstance(data, dict) or data.get('error'):
        raise ValueError('Search service returned an application error')
    total = data.get('numResultSearch'); rows = data.get('resultSearch')
    if type(total) is not int or not 0 <= total <= 50000 or not isinstance(rows, list):
        raise ValueError('Missing or invalid search count/results')
    if len(rows) != min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE)):
        raise ValueError('Truncated or wrong search page length')
    result = {}
    for row in rows:
        identity = row.get('idDocument'); day = source_date(row.get('date'))
        if not isinstance(identity, str) or not re.fullmatch(r'\d+', identity) or row.get('tipusDiari') != 'DOGC':
            raise ValueError('Unexpected document identity or journal')
        if not start <= day <= end:
            raise ValueError('Search returned an out-of-window publication')
        link = row.get('linkTitle')
        if not isinstance(link, str) or not link.startswith('?') or one_parameter(link, 'documentId') != identity:
            raise ValueError('Search identity differs from its source link')
        key = (identity, day.isoformat())
        if key in result:
            raise ValueError('Duplicate publication within search page')
        result[key] = {'document_id': identity, 'publication_date': day.isoformat(),
                       'title': plain_title(row.get('title')), 'source_record': row}
    return total, result


def compare_indexes(summary, search):
    missing = sorted(set(summary) - set(search)); extra = sorted(set(search) - set(summary))
    title_conflicts = sorted(k for k in set(summary) & set(search) if summary[k]['title'] != search[k]['title'])
    return {'only_in_edition_summaries': missing, 'only_in_search': extra, 'title_conflicts': title_conflicts}


class Client:
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session(); self.session.mount(SERVICE + '/', VerifiedDOGCTLSAdapter())
        self.session.headers['User-Agent'] = 'SpainRenewablesRadar/0.6 (official dated index audit)'
        self.manifest = []

    def request(self, label, url, *, form=None, payload=None):
        p = urlsplit(url); method = 'POST' if form is not None or payload is not None else 'GET'
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            raise ValueError('Unexpected audit destination')
        if method == 'POST':
            if p.hostname != 'portaldogc.gencat.cat' or p.path not in {'/eadop-rest/api/dogc/' + r for r in ('calendarDOGC','summaryDOGC','searchDOGC')}:
                raise ValueError('Unapproved service operation')
        elif p.hostname != 'dogc.gencat.cat' or not (p.path == '/ca/inici/' or p.path.endswith('/common/js/constants.js')):
            raise ValueError('Unapproved public contract document')
        for attempt in range(3):
            response = None
            try:
                response = self.session.request(method, url, data=form, json=payload,
                    timeout=(8,45), allow_redirects=False, stream=True)
                if response.status_code in (429,500,502,503,504):
                    raise requests.ConnectionError('Transient source HTTP ' + str(response.status_code))
                if 300 <= response.status_code < 400:
                    raise ValueError('Unexpected redirect; source contract needs review')
                response.raise_for_status()
                chunks = []; size = 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 6_000_000: raise ValueError('Response exceeds bounded size')
                    chunks.append(chunk)
                raw = b''.join(chunks); sha = hashlib.sha256(raw).hexdigest()
                (self.root / (sha + '.bin')).write_bytes(raw)
                self.manifest.append({'label':label,'url':url,'method':method,'parameters':form if form is not None else payload,
                    'status':response.status_code,'sha256':sha,'bytes':size,'retrieved_at':datetime.now(timezone.utc).isoformat()})
                time.sleep(.1)
                return raw
            except requests.exceptions.SSLError:
                raise
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
                if attempt == 2: raise
                time.sleep(attempt + 1)
            finally:
                if response is not None: response.close()
                atomic_json(self.root/'acquisitions.json', self.manifest)
        raise RuntimeError('Unreachable audit retry state')

    def post(self, label, route, *, form=None, payload=None):
        return json.loads(self.request(label, SERVICE + '/eadop-rest/api/dogc/' + route, form=form, payload=payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--until'); parser.add_argument('--output', default='reports/dogc_index_audit')
    args = parser.parse_args(); root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    end = date.fromisoformat(args.until) if args.until else datetime.now(ZoneInfo('Europe/Madrid')).date()-timedelta(days=1)
    if end >= datetime.now(ZoneInfo('Europe/Madrid')).date():
        raise ValueError('Only complete Spanish calendar days can be audited')
    start = end-timedelta(days=29); client = Client(root/'raw')
    result = {'head_sha':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID'),
              'window_start':str(start),'window_end':str(end),'dated_collector_enabled':False,
              'project_events_created':0,'document_bodies_acquired':0,'index_complete':False}
    try:
        home = BeautifulSoup(client.request('contract:home', WEB+'/ca/inici/'), 'html.parser')
        scripts = {Path(urlsplit(t['src']).path).name:urljoin(WEB,t['src']) for t in home.select('script[src]')}
        constants = client.request('contract:constants',scripts['constants.js']).decode('utf-8')
        host = re.search(r'\bHOST_PRO\s*=\s*[\x27\x22]([^\x27\x22]+)',constants)
        if not host or host[1] != 'portaldogc.gencat.cat': raise ValueError('Official production host changed')
        inputs = {t.get('id'):t.get('value') for t in home.select('input[id]')}
        if inputs.get('uriCalendar') != '/eadop-rest/api/dogc/calendarDOGC' or inputs.get('uriCerDogc') != '/eadop-rest/api/dogc/searchDOGC':
            raise ValueError('Official service routes changed')
        months = sorted({(start.year,start.month),(end.year,end.month)})
        days = {}; summaries = {}; editions = 0; annexes = 0
        for year, month in months:
            data = client.post(f'calendar:{year}:{month}','calendarDOGC',form={'year':year,'month':month,'language':'ca'})
            days.update({d:e for d,e in parse_calendar(data,year,month).items() if start <= d <= end})
        if len(days) != 30: raise ValueError('Not all thirty days accounted for')
        for day, edition in sorted(days.items()):
            if edition is not None:
                data = client.post('edition:'+str(day),'summaryDOGC',form={'numDOGC':edition,'language':'ca'})
                records = parse_summary(data,edition,day); editions += 1
                annexes += sum(scope != edition for scope, _ in summary_scopes(data,edition,day))
                if set(summaries) & set(records): raise ValueError('Duplicate dated edition')
                summaries.update(records)
            print('DOGC_INDEX_DAY',day,edition or 'NO_EDITION',flush=True)
        atomic_json(root/'edition_index.json',list(summaries.values()))
        total, first = parse_search(client.post('search:1','searchDOGC',payload=search_parameters(start,end,1)),start,end,1)
        search = dict(first); pages = max(1,(total + PAGE_SIZE - 1)//PAGE_SIZE)
        for page in range(2,pages+1):
            count, records = parse_search(client.post(f'search:{page}','searchDOGC',payload=search_parameters(start,end,page)),start,end,page)
            if count != total or set(records) & set(search): raise ValueError('Search count changed or pagination repeats publications')
            search.update(records)
        if len(search) != total: raise ValueError('Search count is not reconciled')
        count, recheck = parse_search(client.post('search:recheck','searchDOGC',payload=search_parameters(start,end,1)),start,end,1)
        if count != total or {k:v['title'] for k,v in recheck.items()} != {k:v['title'] for k,v in first.items()}:
            raise ValueError('Search changed while being acquired')
        for year, month in months:
            data = client.post(f'calendar:recheck:{year}:{month}','calendarDOGC',form={'year':year,'month':month,'language':'ca'})
            check = {d:e for d,e in parse_calendar(data,year,month).items() if start <= d <= end}
            if check != {d:e for d,e in days.items() if (d.year,d.month)==(year,month)}:
                raise ValueError('Published calendar changed while being acquired')
        atomic_json(root/'search_index.json',list(search.values()))
        differences = compare_indexes(summaries,search); atomic_json(root/'reconciliation.json',differences)
        if any(differences.values()): raise ValueError('Dated edition/search reconciliation failed: '+canonical({k:len(v) for k,v in differences.items()}))
        # Reparse original saved bytes and check identities/titles against live parsing.
        rebuilt = {}; rebuilt_search = {}
        for item in client.manifest:
            raw = (client.root/(item['sha256']+'.bin')).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['sha256'] or len(raw)!=item['bytes']:
                raise ValueError('Original acquisition integrity failure')
            label = item['label']
            if label.startswith('edition:'):
                day = date.fromisoformat(label.split(':',1)[1])
                rebuilt.update(parse_summary(json.loads(raw),days[day],day))
            elif re.fullmatch(r'search:\d+',label):
                _, records = parse_search(json.loads(raw),start,end,int(label.split(':')[1])); rebuilt_search.update(records)
        if rebuilt != summaries or rebuilt_search != search: raise ValueError('Original-byte replay differs from acquired indexes')
        candidates = [dict(r,review_status='UNREVIEWED_TITLE_CANDIDATE') for r in summaries.values() if ENERGY.search(r['title'])]
        atomic_json(root/'candidates.json',candidates)
        rows = ''.join('<tr><td>'+html.escape(r['publication_date'])+'</td><td>'+html.escape(r['title'])+'</td><td><a href="'+html.escape(r['source_url'],quote=True)+'">Fonte ufficiale</a></td></tr>' for r in candidates)
        (root/'index.html').write_text('<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DOGC — verifica indice</title><h1>DOGC — avvisi candidati</h1><p>Finestra '+str(start)+' — '+str(end)+'. Solo indice: testi integrali non acquisiti, pertinenza e progetti da verificare. Nessun nuovo evento inserito nel radar.</p><table><tr><th>Pubblicazione</th><th>Titolo originale</th><th>Documento</th></tr>'+rows+'</table></html>',encoding='utf-8')
        result.update(index_complete=True,source_days=30,publication_editions=editions,annex_editions=annexes,no_edition_days=30-editions,
                      edition_dispositions=len(summaries),search_reported_count=total,search_pages=pages,
                      title_candidates=len(candidates),independent_index_reconciliation=True,original_byte_replay_verified=True,
                      index_sha256=hashlib.sha256(canonical(sorted((k[0],k[1],r['title']) for k,r in summaries.items())).encode()).hexdigest())
        for record in candidates: print('DOGC_TITLE_CANDIDATE',json.dumps(record,ensure_ascii=False),flush=True)
        print('DOGC_INDEX_AUDIT',json.dumps(result,ensure_ascii=False),flush=True)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,error=str(exc)); raise
    finally:
        atomic_json(root/'audit.json',result)


if __name__ == '__main__': main()
