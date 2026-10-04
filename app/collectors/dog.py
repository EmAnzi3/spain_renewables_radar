"""Dated DOG publications; archives, request dates and publication dates stay distinct."""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = 'https://www.xunta.gal/diario-oficial-galicia/'
REFERENCE = r'(?:IN\d{3}[A-Z]\s+\d{4}/\d+(?:-[A-Z0-9]+)*|FV\s+\d+/\d{4})'
REF_RE = re.compile(r'\bexpediente\s*:?\s*(' + REFERENCE + r')\b', re.I)
ASSET_RE = re.compile(r'(?:parque\s+e[oó]lico|(?:planta|parque|instalaci[oó]n)\s+(?:solar\s+)?fotovoltaic[ao]|(?:sistema|planta|m[oó]dulo)\s+de\s+almacenamiento(?:\s+de\s+energ[ií]a)?)(?:\s+denominad[oa])?\s+[«“\"]?(.{2,160}?)(?=[»”\"]|,|\s+\(|\s+(?:situad[oa]|ubicad[oa]|emplazad[oa]|a\s+\d+|de\s+\d+|con\s+sus?\s+infraestructuras|y\s+sus?\s+infraestructuras)\b|$)', re.I)
TARGET_RE = re.compile(r'fotovolta|e[oó]lic|aerogenerador|\bbess\b|\bbater[ií]as?\b|almacenamiento\s+(?:el[eé]ctrico|energ[eé]tico|de\s+energ[ií]a)|hibridaci[oó]n', re.I)
PROVINCES = ('A Coruña', 'Lugo', 'Ourense', 'Pontevedra')


def compact(text):
    return ' '.join(text.split())


def norm(text):
    return compact(''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).casefold())


def official_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname != 'www.xunta.gal' or p.username or p.password
            or p.port not in (None, 443) or not p.path.startswith(('/dog/Publicados/', '/diario-oficial-galicia/'))):
        raise ValueError('Unapproved DOG source URL')
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))


def document_identity(url):
    p = urlsplit(official_url(url))
    m = re.fullmatch(r'/dog/Publicados/(\d{4})/(\d{8})/(Anuncio[^/]+)_(?:es|gl|pt)\.(?:html|pdf)', p.path)
    if not m:
        raise ValueError('Unrecognized DOG document identity')
    day = datetime.strptime(m[2], '%Y%m%d').date()
    if str(day.year) != m[1]:
        raise ValueError('Inconsistent DOG document date')
    return f'{m[2]}/{m[3]}', day.isoformat()


def parse_calendar(payload, year, month):
    if not isinstance(payload, list) or not payload:
        raise ValueError('DOG calendar missing or malformed; not a valid empty month')
    rows, seen = [], set()
    for row in payload:
        if not isinstance(row, dict) or not isinstance(row.get('fecha'), str) or not isinstance(row.get('url'), str):
            raise ValueError('Malformed DOG calendar row')
        day = datetime.strptime(row['fecha'], '%d/%m/%Y').date()
        if (day.year, day.month) != (year, month):
            raise ValueError('DOG returned a different calendar month')
        url = official_url(urljoin(ROOT, html.unescape(row['url'])))
        if url in seen:
            raise ValueError('Duplicate calendar edition')
        seen.add(url)
        rows.append(dict(date=day.isoformat(), url=url, original=row))
    return rows


def verify_index(raw, day):
    soup = BeautifulSoup(raw, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    dates = [datetime.strptime(s, '%d/%m/%Y').date() for s in re.findall(r'\b\d{1,2}/\d{1,2}/\d{4}\b', title)]
    if day not in dates:
        raise ValueError('DOG index date not verified in page title')
    return soup


def section_urls(raw, url, day):
    soup = verify_index(raw, day)
    found = {}
    for a in soup.select('a[href]'):
        target = urljoin(url, a['href']); p = urlsplit(target)
        ruta = dict(parse_qsl(p.query)).get('ruta', '')
        if p.path.endswith('/mostrarContenido.do') and '/Secciones' in ruta:
            target = official_url(target)
            if f'/{day:%Y%m%d}/' not in ruta or not re.search(r'/Secciones\d+_es\.html$', ruta):
                continue
            found[ruta] = target
    if not found:
        raise ValueError('DOG dated section navigation missing')
    return sorted(found.values())


def parse_index(raw, url, day):
    soup = verify_index(raw, day); found = {}
    for a in soup.select('a[href]'):
        target = urljoin(url, a['href'])
        if not re.search(r'/Anuncio[^/]+_es\.html$', urlsplit(target).path):
            continue
        identity, published = document_identity(target)
        if published != day.isoformat():
            raise ValueError('DOG notice belongs to a different publication date')
        title = compact(a.get_text(' ', strip=True))
        if not title:
            raise ValueError('DOG notice title missing')
        item = dict(external_id=identity, publication_date=published, title=title, url=official_url(target))
        if identity in found and found[identity] != item:
            raise ValueError('Conflicting duplicate DOG notice')
        found[identity] = item
    return list(found.values())


def disposition_type(title):
    t = norm(title)
    if re.search(r'\b(?:se deniega|se deniegan|denegar)\b', t): return 'DENIED'
    if re.search(r'\b(?:se acepta|se aceptan)\b.*\b(?:renuncia|desistimiento)\b', t): return 'WITHDRAWN'
    if re.search(r'\b(?:se archiva|se declara.*(?:caducidad|terminacion))\b', t): return 'PROCEDURE_ENDED'
    if re.search(r'\b(?:informacion publica|se solicita|solicitud(?:es)? de)\b', t): return 'PUBLIC_INFO'
    if re.search(r'\b(?:actas previas|levantamiento de actas|ocupacion.*bienes)\b', t): return 'EXPROPRIATION'
    if re.search(r'\b(?:se otorga|se otorgan|se concede|se conceden)\b', t):
        if 'construccion' in t: return 'CONSTRUCTION_AUTH'
        if 'utilidad publica' in t: return 'PUBLIC_UTILITY'
        if 'autorizacion administrativa previa' in t: return 'PRIOR_AUTH'
    if re.search(r'\bse formula\b.*\bdeclaracion de impacto ambiental\b', t): return 'DIA'
    if re.search(r'\b(?:se modifica|se aprueba.*modificacion)\b', t): return 'MODIFICATION'
    return None


def spanish_number(raw):
    raw = raw.replace(' ', '')
    if not re.fullmatch(r'\d+(?:\.\d{3})*(?:,\d+)?|\d+(?:\.\d+)?', raw):
        raise ValueError('Invalid source power number')
    return float(raw.replace('.', '').replace(',', '.')) if ',' in raw or re.fullmatch(r'\d{1,3}(?:\.\d{3})+', raw) else float(raw)


def power_evidence(text, title=False):
    number = r'(\d+(?:[.,]\d+)*)'
    patterns = [r'potencia\s+(?:a\s+instalar|instalada|nominal)\s*:\s*' + number + r'\s*(MW|kW)\b']
    if title:
        patterns.insert(0, r'\b(?:a|de)\s+' + number + r'\s*(MW|kW)\s+de\s+potencia\s+(?:instalada|nominal)\b')
        patterns.append(r'\bde\s+' + number + r'\s*(MW|kW)\s*(?:,|\bde\s+potencia)')
    evidence = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            value = spanish_number(match[1]) / (1000 if match[2].lower() == 'kw' else 1)
            if value <= 0: raise ValueError('Non-positive source power')
            evidence.append(dict(mw=value, quote=match[0], basis='installed_or_nominal_not_access'))
    return evidence


def location_evidence(title, scope):
    quotes = []
    pattern = r'(?:ayuntamientos?\s+afectados|situaci[oó]n|ubicaci[oó]n)\s*:\s*([^\n.;]{2,250})'
    quotes.extend(m[0] for m in re.finditer(pattern, scope, re.I))
    pattern = r'(?:situad[oa]s?|ubicad[oa]s?|emplazad[oa]s?)\s+en\s+(?:(?:el|los|la|las)\s+)?(?:ayuntamientos?|municipios?|t[eé]rminos?\s+municipales?)\s+de\s+(.{2,240}?)(?=,\s*promovid|\s*\(expediente|\.|$)'
    quotes.extend(m[0] for m in re.finditer(pattern, title, re.I))
    provinces = sorted({p for p in PROVINCES if any(re.search(r'\(' + re.escape(p) + r'\)', q, re.I) for q in quotes)})
    towns = []
    for q in quotes:
        value = re.sub(r'^.*?:\s*', '', q)
        value = re.sub(r'^.*?\b(?:ayuntamientos?|municipios?|municipales?)\s+de\s+', '', value, flags=re.I)
        value = re.split(r'\s*\(', value)[0].strip(' ,.;')
        towns.extend(x.strip() for x in re.split(r',\s*|\s+y\s+', value) if x.strip())
    return provinces, sorted(set(towns)), quotes


def extract_records(title, text):
    kind = disposition_type(title)
    matches = list(ASSET_RE.finditer(title))
    if not kind or not matches:
        return [], 'REVIEW_NO_EXPLICIT_PROJECT_OR_OPERATIVE_EVENT'
    block_re = re.compile(r'\b\d+[º°]\.\s*(?:parque|planta|instalaci[oó]n|sistema)\b.{0,450}?\(\s*expediente\s+(' + REFERENCE + r')\s*\)', re.I | re.S)
    blocks = list(block_re.finditer(text)); records = []
    for i, match in enumerate(matches):
        segment = title[match.start():matches[i+1].start() if i+1<len(matches) else len(title)]
        refs = list(dict.fromkeys(compact(x[1]) for x in REF_RE.finditer(segment)))
        if len(refs) != 1:
            return [], 'REVIEW_MISSING_OR_AMBIGUOUS_ADMINISTRATIVE_REFERENCE'
        ref = refs[0]; name = compact(match[1]).strip(' ,.;«»“”\"')
        if len(name) < 3 or len(name) > 140 or re.match(r'^(?:de |existente|por |en |\d)', norm(name)):
            return [], 'REVIEW_UNRESOLVED_PROJECT_NAME'
        own_blocks = [(j, b) for j, b in enumerate(blocks) if norm(b[1]) == norm(ref)]
        if len(matches) > 1:
            if len(own_blocks) != 1:
                return [], 'REVIEW_MULTI_PROJECT_WITHOUT_UNIQUE_BODY_SECTIONS'
            j, b = own_blocks[0]
            scope = text[b.end():blocks[j+1].start() if j+1<len(blocks) else len(text)]
        else:
            operative = list(re.finditer(r'\bRESUELVO\s*:', text, re.I))
            scope = text[operative[-1].end():] if operative else text
        tech_part = norm(segment)
        tech = 'WIND' if 'eolic' in tech_part else ('PV' if 'fotovolta' in tech_part else 'BESS')
        if 'hibrid' in tech_part: tech = 'HYBRID'
        powers = power_evidence(segment, title=True) + power_evidence(scope)
        values = {p['mw'] for p in powers}
        flags = []
        power = next(iter(values)) if len(values) == 1 else None
        if len(values) > 1: flags.append(dict(code='SOURCE_POWER_DISAGREEMENT', severity='WARN', values_mw=sorted(values)))
        provinces, towns, location_quotes = location_evidence(segment, scope)
        if not provinces and len(matches)==1:
            provinces, towns, location_quotes = location_evidence(segment, text)
        promoter_match = re.search(r'(?:solicitante(?:/promotor[ae])?|promotor[ae])\s*:\s*([^\n]{2,160})', scope, re.I)
        promoter = compact(promoter_match[1]) if promoter_match else None
        if promoter:
            promoter = re.split(r'\s*\((?:CIF|NIF)|\s+Domicilio', promoter, flags=re.I)[0].strip(' .;')
        else:
            pm = re.search(r'promovid[oa]s?\s+por\s+(.{2,140}?)(?=\s*\(\s*expediente|$)', segment, re.I)
            promoter = compact(pm[1]).strip(' .;') if pm else None
        duration = re.search(r'plazo\s+de\s+ejecuci[oó]n\s*:\s*([^\n.;]{1,200})', scope, re.I)
        duration_quote = duration[0] if duration else None
        duration_match = re.search(r'(?:\((\d{1,3})\)|(\d{1,3}))\s*meses', duration[1], re.I) if duration else None
        months = int(duration_match[1] or duration_match[2]) if duration_match else None
        expansion = 'ampliacion' in norm(title)
        if expansion: flags.append(dict(code='EXPANSION_CAPACITY_IS_RESULTING_PLANT_NOT_INCREMENT', severity='INFO'))
        records.append(dict(project_name=name, expediente=ref, technology=tech, power_mw=power,
                            promoter=promoter, province=provinces[0] if len(provinces)==1 else None,
                            ccaa='Galicia', event_type=kind, municipalities=towns, provinces=provinces,
                            execution_duration_months=months, execution_duration_quote=duration_quote,
                            work_start=None, work_end=None, power_evidence=powers,
                            power_scope='resulting_plant_capacity' if expansion else 'project_capacity',
                            location_evidence=location_quotes, quality_flags=flags))
    if len({norm(r['expediente']) for r in records})!=len(records):
        raise ValueError('Repeated administrative reference in different project sections')
    return records, None


def parse_notice(raw, notice):
    soup = BeautifulSoup(raw, 'html.parser')
    page_title = compact(soup.title.get_text(' ', strip=True)) if soup.title else ''
    header = re.match(r'DOG\s+\d+\s+del\s+(\d{1,2}/\d{1,2}/\d{4})\s*-\s*(.+)', page_title, re.I)
    if not header or datetime.strptime(header[1], '%d/%m/%Y').date().isoformat()!=notice['publication_date']:
        raise ValueError('DOG detail publication date cannot be verified')
    if norm(header[2]) != norm(notice['title']):
        raise ValueError('DOG detail title differs from dated index')
    main = soup.find('main')
    if main is None: raise ValueError('DOG legal text container missing')
    for tag in main.select('script,style,nav'): tag.decompose()
    text = main.get_text('\n', strip=True)
    records, review = extract_records(notice['title'], text)
    return dict(notice, raw_text=text, records=records, review_reason=review,
                original_html_sha256=hashlib.sha256(raw).hexdigest())


def events_from_notice(notice):
    from app.parser import ParsedEvent
    from app.lifecycle import commercial_stage
    events = []
    for row in notice['records']:
        suffix = ':' + hashlib.sha256(norm(row['expediente']).encode()).hexdigest()[:12] if len(notice['records'])>1 else ''
        key = hashlib.sha1(('DOG|' + norm(row['expediente'])).encode()).hexdigest()[:20]
        fields = {k:row[k] for k in ('project_name','technology','power_mw','promoter','expediente','province','ccaa','event_type')}
        events.append(ParsedEvent(source_code='DOG', external_id=notice['external_id']+suffix,
            publication_date=notice['publication_date'], title=notice['title'], url=notice['url'],
            raw_text=notice['raw_text'], commercial_stage=commercial_stage(row['event_type']), project_key=key, **fields))
    return events


def archive_links(notices, snapshot):
    if snapshot is None: return dict(status='ARCHIVE_NOT_LOADED', matches=[])
    if snapshot.get('source')!='XUNTA_PUBLIC' or not snapshot.get('complete'):
        raise ValueError('Galicia archive snapshot incomplete')
    links=[]
    for notice in notices:
        identity,_=document_identity(notice['url'])
        for row in snapshot['records']:
            exact_link=False
            for doc in row.get('documents',[]):
                try: other,_=document_identity(doc['url'])
                except (ValueError, KeyError): continue
                if identity==other: exact_link=True
            refs={norm(m[1]) for m in REF_RE.finditer(row['title'])}
            common=sorted(refs & {norm(r['expediente']) for r in notice['records']})
            if exact_link or common:
                links.append(dict(dog_external_id=notice['external_id'], dog_url=notice['url'],
                    verified_dog_publication_date=notice['publication_date'], archive_record_key=row['record_key'],
                    archive_url=row['url'], rule='EXACT_OFFICIAL_DOCUMENT' if exact_link else 'EXACT_ADMINISTRATIVE_REFERENCE',
                    shared_references=common, archive_web_publication_date=row.get('web_publication_date')))
    return dict(status='COMPARED', matches=links, archive_records=len(snapshot['records']),
                note='Links are evidence only; no automatic project merge or archive web date changes.')


class DOGCollector:
    code='DOG'

    def __init__(self, timeout=30, user_agent='SpainRenewablesRadar/0.5', *, session=None, output_dir='reports/dog'):
        self.session=session or requests.Session()
        self.session.headers['User-Agent']=user_agent
        self.timeout=timeout;self.output=Path(output_dir);self.output.mkdir(parents=True,exist_ok=True)
        (self.output/'raw').mkdir(exist_ok=True)
        self._calendar={};self._days={};self._failures={};self._responses={};self.notices={};self.metadata={}
        self.audit=dict(source_code=self.code, acquisitions=[], days={}, notices=[], review=[], calendar_months={})

    def _save(self):
        self.audit['notices']=list(self.notices.values())
        (self.output/'coverage.json').write_text(json.dumps(self.audit,ensure_ascii=False,indent=2),encoding='utf-8')

    def _request(self,url,data=None):
        url=official_url(url);key=url+'|'+json.dumps(data,sort_keys=True)
        if key in self._responses:return self._responses[key]
        if key in self._failures:raise RuntimeError(self._failures[key])
        last=None
        for attempt in range(3):
            current=url;payload=data;parts=[];size=0;response=None
            evidence=dict(url=url,method='POST' if data is not None else 'GET',payload=data,attempt=attempt+1,
                          retrieved_at=datetime.now(timezone.utc).isoformat(),redirects=[])
            try:
                for _ in range(5):
                    response=self.session.request('POST' if payload is not None else 'GET',current,data=payload,
                        timeout=(8,self.timeout),allow_redirects=False,stream=True)
                    evidence['status']=response.status_code
                    if response.status_code in (301,302,303,307,308):
                        target=official_url(urljoin(current,response.headers.get('Location','')))
                        evidence['redirects'].append(dict(from_url=current,to_url=target,status=response.status_code))
                        response.close();current=target
                        if response.status_code==303:payload=None
                        continue
                    response.raise_for_status()
                    for part in response.iter_content(65536):
                        size+=len(part)
                        if size>12_000_000:raise ValueError('DOG response exceeds bounded size')
                        parts.append(part)
                    raw=b''.join(parts)
                    expected=response.headers.get('Content-Length')
                    if expected and not response.headers.get('Content-Encoding') and int(expected)!=len(raw):
                        raise requests.exceptions.ChunkedEncodingError('DOG incomplete response body')
                    evidence.update(final_url=current,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),complete=True)
                    (self.output/'raw'/(evidence['sha256']+'.bin')).write_bytes(raw)
                    self.audit['acquisitions'].append(evidence);self._save()
                    self._responses[key]=(raw,current)
                    return raw,current
                raise ValueError('Too many DOG redirects')
            except (requests.RequestException,ValueError) as exc:
                last=exc;raw=b''.join(parts)
                evidence.update(error=str(exc)[:500],error_class=type(exc).__name__,bytes=len(raw),complete=False)
                if raw:
                    evidence['sha256']=hashlib.sha256(raw).hexdigest()
                    (self.output/'raw'/(evidence['sha256']+'.bin')).write_bytes(raw)
                self.audit['acquisitions'].append(evidence);self._save()
                code=getattr(getattr(exc,'response',None),'status_code',None)
                retry=isinstance(exc,requests.RequestException) and (code is None or code in (429,500,502,503,504))
                if not retry:break
                if attempt<2:time.sleep(2**attempt)
            finally:
                if response is not None:response.close()
        self._failures[key]=str(last)
        raise RuntimeError('DOG acquisition failed: '+str(last)) from last

    def _month(self,day):
        key=(day.year,day.month)
        if key not in self._calendar:
            self._request(ROOT+'portalPublicoHome.do?lang=es')
            raw,_=self._request(ROOT+'portalPublicoHome.do?method=getDiasDog',dict(mes=day.month,ano=day.year,idioma='es'))
            records=parse_calendar(json.loads(raw),*key)
            self._calendar[key]=records
            self.audit['calendar_months'][f'{day.year}-{day.month:02}']=dict(editions=len(records),records=records)
        return self._calendar[key]

    def collect_day(self,day):
        stamp=day.isoformat()
        if stamp in self._days:return self._days[stamp]
        if stamp in self._failures:raise RuntimeError(self._failures[stamp])
        stats=dict(status='ERROR',editions=0,sections=0,index_notices=0,candidates=0,events=0)
        try:
            editions=[r for r in self._month(day) if r['date']==stamp];all_notices={}
            stats['editions']=len(editions)
            for edition in editions:
                raw,url=self._request(edition['url'])
                sections=section_urls(raw,url,day);stats['sections']+=len(sections)
                edition_count=0
                for section in sections:
                    raw,url=self._request(section)
                    for notice in parse_index(raw,url,day):
                        old=all_notices.get(notice['external_id'])
                        if old is not None and old!=notice:raise ValueError('DOG edition identity conflict')
                        all_notices[notice['external_id']]=notice;edition_count+=1
                if not edition_count:raise ValueError('DOG published edition has no readable dispositions')
            stats['index_notices']=len(all_notices);events=[]
            for item in all_notices.values():
                if not TARGET_RE.search(item['title']):continue
                stats['candidates']+=1
                raw,_=self._request(item['url']);notice=parse_notice(raw,item)
                self.notices[item['external_id']]=notice
                if notice['review_reason']:
                    self.audit['review'].append({k:notice[k] for k in ('external_id','title','url','publication_date','review_reason')})
                    continue
                parsed=events_from_notice(notice)
                for event,record in zip(parsed,notice['records']):self.metadata[event.external_id]=(notice,record)
                events.extend(parsed)
            stats.update(status='OK',edition_status='PUBLISHED' if editions else 'NO_EDITION_IN_OFFICIAL_CALENDAR',events=len(events))
            self._days[stamp]=events
            return events
        except Exception as exc:
            stats['error']=str(exc);self._failures[stamp]=str(exc);raise
        finally:
            self.audit['days'][stamp]=stats;self._save()

    def persist_metadata(self,conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS regional_public_metadata (
            source_code TEXT NOT NULL,external_id TEXT NOT NULL,project_key TEXT NOT NULL,
            web_publication_date TEXT NOT NULL,source_url TEXT NOT NULL,evidence_json TEXT NOT NULL,
            PRIMARY KEY(source_code,external_id),FOREIGN KEY(project_key) REFERENCES projects(project_key))''')
        for external_id,(notice,record) in self.metadata.items():
            event=conn.execute('SELECT * FROM events WHERE source_code=? AND external_id=?',(self.code,external_id)).fetchone()
            if event is None or event['url']!=notice['url'] or event['publication_date']!=notice['publication_date']:
                raise ValueError('DOG evidence must correspond to a persisted immutable event')
            evidence=dict(extraction=record,quality_flags=record['quality_flags'],legal_documents=[dict(
                url=notice['url'],sha256=notice['original_html_sha256'],format='HTML',original_external_id=notice['external_id'])])
            conn.execute('''INSERT INTO regional_public_metadata VALUES (?,?,?,?,?,?)
                ON CONFLICT(source_code,external_id) DO UPDATE SET project_key=excluded.project_key,evidence_json=excluded.evidence_json''',
                (self.code,external_id,event['project_key'],notice['publication_date'],notice['url'],json.dumps(evidence,ensure_ascii=False)))
            if len(record['provinces'])>1:
                conn.execute('''INSERT INTO project_geo_enrichment
                  (project_key,municipalities_json,provinces_json,province,ccaa,status,source_code,source_url,reference_date)
                  VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_key) DO NOTHING''',
                  (event['project_key'],json.dumps(record['municipalities'],ensure_ascii=False),json.dumps(record['provinces'],ensure_ascii=False),
                   None,'Galicia','MULTI_PROVINCE','DOG',notice['url'],notice['publication_date']))
        conn.commit()
        path=Path('data/galicia_archive_baseline.json')
        links=archive_links(list(self.notices.values()),json.loads(path.read_text()) if path.exists() else None)
        (self.output/'galicia_links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),encoding='utf-8')
