"""Reconcile official BOPV calendars/edition summaries with a fresh full search.

No collector is enabled and no database/project/lifecycle record is written.
Every matched disposition retains an observed publication date and original URL.
"""
from __future__ import annotations

import ast
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
from urllib.parse import urljoin, urlsplit, parse_qsl

import requests
from bs4 import BeautifulSoup

HOST = 'https://www.euskadi.eus'
ORIGIN = HOST + '/bopv2/datos/Ultimo.shtml'
MONTHS = {name: n for n, name in enumerate(('enero','febrero','marzo','abril','mayo','junio',
          'julio','agosto','septiembre','octubre','noviembre','diciembre'), 1)}
DAY_RE = re.compile(r',\s*(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+'
                    r'(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})$', re.I)
ARTICLE = re.compile(r'(?:/web01-bopv/es)?/bopv2/datos/(\d{4})/(\d{2})/(\d{2})(\d{5})a\.shtml$')


def allowed(url):
    p = urlsplit(url)
    return p.scheme == 'https' and p.hostname == 'www.euskadi.eus' and p.port in (None,443) and not p.username and not p.password and not p.fragment


def article_id(url):
    p = urlsplit(url); match = ARTICLE.fullmatch(p.path)
    # The official search emits three fixed presentation flags. Keep the
    # original URL, accept only this exact observed contract or no query.
    query = parse_qsl(p.query, keep_blank_values=True)
    presentation = [('BOPV_NOT_IN_PORTAL', ''), ('BOPV_HIDE_CALENDAR', ''), ('R01HNoPortal', 'true')]
    valid_query = not p.query or (len(query) == 3 and sorted(query) == sorted(presentation))
    if not allowed(url) or not valid_query or not match or match[1][2:] != match[3] or not 1 <= int(match[2]) <= 12:
        raise ValueError('Unexpected official Spanish disposition URL')
    return match[1] + '/' + match[4]


def publication_header(soup, *, summary):
    prefix = r'Sumario\s+n\.[º°]\s+(\d+)' if summary else r'N\.[º°]\s+(\d+)'
    # Historical summaries also use tituGeneral for the sidebar search labels.
    # Require one actual edition masthead, not one generic style class.
    nodes = [node for node in soup.select('h2.tituGeneral')
             if re.match(prefix, ' '.join(node.get_text(' ', strip=True).split()), re.I)]
    if len(nodes) != 1:
        raise ValueError('Missing or ambiguous source masthead')
    title = ' '.join(nodes[0].get_text(' ', strip=True).split())
    number = re.match(prefix, title, re.I); match = DAY_RE.search(title)
    if not number or not match or match[3].lower() not in MONTHS:
        raise ValueError('Unrecognized official publication date/edition')
    day = date(int(match[4]), MONTHS[match[3].lower()], int(match[2]))
    weekday = ('lunes','martes','miércoles','jueves','viernes','sábado','domingo')[day.weekday()]
    if match[1].casefold() != weekday:
        raise ValueError('Publication weekday conflicts with calendar date')
    return day, int(number[1])


def parse_calendar(text, year, month):
    if not re.search(r"var\s+bopvIdioma\s*=\s*'es'", text):
        raise ValueError('Unexpected calendar language')
    # Year and month must be explicitly present even for a month without editions.
    if not re.search(r'var\s+year\s*=\s*'+str(year)+r'\s*;', text) or not re.search(r'var\s+month\s*=\s*'+str(month-1)+r'\s*;', text):
        raise ValueError('Calendar month/year scope changed')
    arrays = []
    for name in ('diasHabilitados','enlaces'):
        matches = re.findall(r'var\s+'+name+r'\s*=\s*(\[[^;]*\])\s*;', text)
        if len(matches) != 1 or len(matches[0]) > 20000:
            raise ValueError('Calendar literal absent or above bounded size')
        value = ast.literal_eval(matches[0])
        if not isinstance(value,list) or len(value)>31:
            raise ValueError('Unexpected calendar array')
        arrays.append(value)
    days, files = arrays
    if len(days) != len(files) or len(set(days)) != len(days):
        raise ValueError('Calendar days and editions disagree')
    out = {}; seen = set()
    for value, editions in zip(days,files):
        if not isinstance(value,str) or not re.fullmatch(r'\d{8}',value):
            raise ValueError('Invalid source calendar day')
        day = datetime.strptime(value,'%Y%m%d').date()
        if (day.year,day.month) != (year,month):
            raise ValueError('Source calendar contains another month')
        editions = editions if isinstance(editions,list) else [editions]
        if not editions or len(editions)>10 or any(not isinstance(e,str) or not re.fullmatch(r's'+str(year)[2:]+r'_\d{4}\.shtml',e) for e in editions):
            raise ValueError('Malformed official edition filename')
        if len(set(editions))!=len(editions) or seen.intersection(editions):
            raise ValueError('Duplicate source edition')
        seen.update(editions);out[day]=editions
    return out


def parse_summary(text, url, day, filename):
    soup = BeautifulSoup(text,'html.parser')
    observed_day, edition = publication_header(soup,summary=True)
    if observed_day!=day or int(filename[4:8])!=edition:
        raise ValueError('Summary publication date/number differs from calendar')
    pdf_path = '/bopv2/datos/'+day.strftime('%Y/%m/')+filename.replace('.shtml','.pdf')
    pdf_links = {urljoin(url,a['href']) for a in soup.select('.listaFormatos .formatoPdf a[href]')}
    if pdf_links != {HOST+pdf_path}:
        raise ValueError('Summary original-PDF link does not confirm calendar edition')
    titles = soup.select('.BOPVSumarioTitulo')
    if not titles or len(titles)>2000:
        raise ValueError('Summary missing disposition list or beyond bounded size')
    rows = {}
    for node in titles:
        anchors = node.select('a[href]')
        if len(anchors)!=1:
            raise ValueError('Ambiguous disposition in summary')
        anchor = anchors[0];target = urljoin(url,anchor['href']);identity=article_id(target)
        title = anchor.get_text(' ',strip=True)
        number = node.parent.select('.BOPVSumarioOrden')
        if (not title or len(number)!=1 or number[0].get_text(strip=True)!=str(int(identity.split('/')[1]))
                or identity in rows or not target.endswith('a.shtml')):
            raise ValueError('Summary title or disposition identity missing/duplicated')
        if not urlsplit(target).path.endswith(day.strftime('%Y/%m/')+day.strftime('%y')+identity.split('/')[1]+'a.shtml'):
            raise ValueError('Disposition URL month differs from its edition')
        rows[identity]={'external_id':identity,'source_url':target,'title':title,
                        'publication_date':str(day),'edition':edition,'summary_url':url}
    return rows


def body_provenance(text, url, expected):
    soup=BeautifulSoup(text,'html.parser');day,edition=publication_header(soup,summary=False)
    identities=soup.select('input#bopvNumOrden')
    title=soup.select('.BOPVTitulo')
    if (len(identities)!=1 or identities[0].get('value')!=expected['external_id'].replace('/','0')
            or article_id(url)!=expected['external_id'] or str(day)!=expected['publication_date']
            or edition!=expected['edition'] or len(title)!=1 or title[0].get_text(' ',strip=True)!=expected['title']):
        raise ValueError('Candidate body identity/date/title differs from its summary')
    return {'external_id':expected['external_id'],'publication_date':str(day),'edition':edition,
            'body_header_verified':True,'semantic_classification':'NOT_VALIDATED'}


def reconcile(summary_rows, search_rows):
    if set(summary_rows)!=set(search_rows):
        raise ValueError('Summary/search identity mismatch: '+json.dumps({
            'only_in_summaries':sorted(set(summary_rows)-set(search_rows)),
            'only_in_search':sorted(set(search_rows)-set(summary_rows))}))
    for key,row in summary_rows.items():
        if row['title']!=search_rows[key]['title'] or article_id(search_rows[key]['source_url'])!=key:
            raise ValueError('Summary/search title or URL identity mismatch: '+key)


def original_search(root, module):
    audit=json.loads((root/'probe.json').read_text())
    if not audit.get('probe_success') or not audit.get('search_pagination_complete'):
        raise ValueError('Search acquisition not complete')
    start=date.fromisoformat(audit['window_start']);end=date.fromisoformat(audit['window_end'])
    if (end-start).days!=29:
        raise ValueError('Expected fixed thirty-day search')
    receipts=json.loads((root/'acquisitions.json').read_text());labels={};rows={}
    for receipt in receipts:
        if 'sha256' not in receipt:
            continue
        raw=(root/'raw'/(receipt['sha256']+'.html')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=receipt['sha256'] or len(raw)!=receipt['bytes'] or receipt['status']!=200:
            raise ValueError('Search original byte integrity failure')
        if receipt['label'] in labels:
            raise ValueError('Duplicate completed search acquisition label')
        labels[receipt['label']]=(raw,receipt)
    total=None
    for number in range(1,audit['search_pages_verified']+1):
        label='publication-window-search' if number==1 else 'results-page-'+str(number)
        raw,receipt=labels[label]
        batch,count,pages,_,_=module['result_page'](BeautifulSoup(raw.decode(receipt['encoding'],errors='strict'),'html.parser'),number,start,end,total)
        if total is None:total=count
        if pages!=audit['search_pages_verified'] or set(rows).intersection(r['external_id'] for r in batch):
            raise ValueError('Search page coverage mismatch')
        rows.update({row['external_id']:row for row in batch})
    saved=json.loads((root/'window_index.json').read_text())
    if len(rows)!=total or list(rows.values())!=saved or total!=audit['unique_index_dispositions']:
        raise ValueError('Search inventory does not rebuild from original pages')
    return start,end,rows,labels


class Client:
    def __init__(self,root):
        self.root=root;(root/'raw').mkdir(parents=True,exist_ok=True)
        self.session=requests.Session();self.session.headers['User-Agent']='SpainRenewablesRadar/0.7 (official index reconciliation)'
        self.receipts=[]
    def get(self,label,url):
        if not allowed(url):raise ValueError('Unverified destination')
        with self.session.get(url,timeout=(15,40),allow_redirects=False,stream=True) as response:
            response.raise_for_status()
            if response.status_code!=200:raise ValueError('Unexpected summary redirect or status')
            chunks=[];size=0
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>5000000:raise ValueError('Summary exceeds bounded size')
                chunks.append(chunk)
            raw=b''.join(chunks);sha=hashlib.sha256(raw).hexdigest()
            charset=response.encoding
            if not charset:raise ValueError('Source omitted encoding')
            text=raw.decode(charset,errors='strict')
            (self.root/'raw'/(sha+'.html')).write_bytes(raw)
            item={'label':label,'url':url,'status':200,'bytes':len(raw),'sha256':sha,'encoding':charset,
                  'retrieved_at':datetime.now(timezone.utc).isoformat()}
            self.receipts.append(item)
            (self.root/'acquisitions.json').write_text(json.dumps(self.receipts,indent=2))
            return text,item


def main():
    search_root=Path('reports/bopv_date_probe');root=Path('reports/bopv_reconciliation')
    root.mkdir(parents=True,exist_ok=True);client=Client(root)
    result={'head_sha':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID'),
            'collector_implemented':False,'events_created':0,'index_reconciled':False,'source_semantics_validated':False}
    try:
        module=runpy.run_path('.github/scripts/probe_bopv_dates.py')
        start,end,search,labels=original_search(search_root,module)
        result.update(window_start=str(start),window_end=str(end))
        days=[start+timedelta(days=n) for n in range(30)];calendars={};entries={};metrics=[]
        for year,month in sorted({(d.year,d.month) for d in days}):
            text,_=client.get(f'calendar-{year}-{month}',HOST+f'/bopv2/datos/{month:02d}{year}.shtml')
            calendars.update(parse_calendar(text,year,month))
        for day in days:
            files=calendars.get(day,[]);count=0
            for filename in files:
                url=HOST+'/bopv2/datos/'+day.strftime('%Y/%m/')+filename
                text,receipt=client.get('summary-'+filename,url)
                rows=parse_summary(text,url,day,filename)
                if set(entries).intersection(rows):raise ValueError('One disposition occurs in multiple editions')
                entries.update(rows);count+=len(rows)
                # Rebuild from saved original bytes before marking the day verified.
                raw=(root/'raw'/(receipt['sha256']+'.html')).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=receipt['sha256'] or parse_summary(raw.decode(receipt['encoding']),url,day,filename)!=rows:
                    raise ValueError('Summary original-byte replay mismatch')
            metric={'day':str(day),'editions':files,'dispositions':count,'no_edition_from_official_calendar':not files}
            metrics.append(metric);print('BOPV_EDITION_DAY',json.dumps(metric),flush=True)
        (root/'dispositions.json').write_text(json.dumps(list(entries.values()),ensure_ascii=False,indent=2),encoding='utf-8')
        (root/'day_coverage.json').write_text(json.dumps(metrics,indent=2))
        reconcile(entries,search)
        candidates=json.loads((search_root/'title_candidates.json').read_text())
        checked=[]
        for candidate in candidates:
            raw,receipt=labels['candidate-'+candidate['external_id'].replace('/','-')]
            checked.append(body_provenance(raw.decode(receipt['encoding']),receipt['url'],entries[candidate['external_id']]))
        (root/'candidate_date_checks.json').write_text(json.dumps(checked,indent=2))
        result.update(index_reconciled=True,source_days=30,search_dispositions=len(search),summary_dispositions=len(entries),
                      editions=sum(len(d['editions']) for d in metrics),no_edition_days=sum(not d['editions'] for d in metrics),
                      candidate_bodies=len(checked),candidate_publication_headers_verified=True,
                      original_byte_replay_verified=True,title_conflicts=0,missing_dispositions=0,
                      summary_url_basis='Source calendar edition basename in observed official year/month directory; returned masthead and original PDF link independently checked')
        print('BOPV_INDEX_RECONCILED',json.dumps(result),flush=True)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,error=str(exc));raise
    finally:
        client.session.close()
        (root/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
