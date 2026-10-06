"""GVA energy archive: official dated acts, not inferred permits.

Reconcile all index pages. Read linked top-level legal acts only for requested
publication days. Preserve full original bytes, extraction scope and discrepancies.
"""
from __future__ import annotations
import csv
import hashlib
import html
import io
import json
import math
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE='https://mediambient.gva.es/es/web/energia/informacion-publica'
CCAA='Comunitat Valenciana'
REFERENCE=re.compile(r'\b(AT(?:ALFE|MOFE|REGI)\s*[/ ]\s*\d{4}\s*/\s*\d+(?:\s*/\s*\d{2})?)\b',re.I)
QUOTED=r'[«“"]\s*([^»”"\n]{2,150}?)\s*[»”"]'
NUMBER=re.compile(r'(?<![\w.,])(?P<value>\d+(?:[.,]\d+)*)\s*(?P<unit>kWp|kWn|kW|MWp|MWn|MW)\b',re.I)
LEGAL_LABEL=re.compile(r'resol|publica|anunci|desist|infopub',re.I)


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value or '') if not unicodedata.combining(c)).casefold()


def flatten(value):
    value=re.sub(r'(?<=\w)-\s*\n\s*(?=\w)','',value or '')
    return ' '.join(value.split())


def official_url(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.gva.es'):
        raise ValueError('GVA link or redirect is outside the official HTTPS domain')
    if parsed.username or parsed.password:raise ValueError('Credentials are not allowed in source URLs')
    return url


def parse_listing(raw,response_url):
    soup=BeautifulSoup(raw,'html.parser');iterator=soup.select_one('.taglib-page-iterator')
    if iterator is None:raise ValueError('GVA pagination missing; not a valid empty catalogue')
    match=re.search(r'Mostrando\s+(\d+)\s*-\s*(\d+)\s+de\s+(\d+)\s+resultados',iterator.get_text(' ',strip=True),re.I)
    if not match:raise ValueError('GVA declared result accounting missing')
    bounds=tuple(map(int,match.groups()));first,last,total=bounds
    if not 1<=first<=last<=total:raise ValueError('GVA invalid page bounds')
    records=[]
    for box in soup.select('.asset-abstract'):
        link=box.select_one('.asset-title a[href]');published=box.select_one('.metadata-publish-date')
        if link is None or published is None or not link.get_text(' ',strip=True):
            raise ValueError('GVA publication has no source title/date')
        url=official_url(urljoin(response_url,link['href']))
        ids=[value for key,value in parse_qsl(urlsplit(url).query) if key.endswith('_assetEntryId')]
        if len(ids)!=1 or not ids[0].isdigit():raise ValueError('GVA source identity missing or ambiguous')
        pub=datetime.strptime(published.get_text(' ',strip=True),'%d/%m/%Y').date().isoformat()
        summary=box.select_one('.asset-summary')
        records.append({'external_id':ids[0],'title':link.get_text(' ',strip=True),'publication_date':pub,'url':url,
                        'summary':summary.get_text(' ',strip=True) if summary else '',
                        'categories':[n.get_text(' ',strip=True) for n in box.select('.metadata-categories strong')]})
    if len(records)!=last-first+1 or len({r['external_id'] for r in records})!=len(records):
        raise ValueError('GVA declared page count differs from unique source rows')
    paging=None
    for link in iterator.select('a[href]'):
        url=urljoin(response_url,link['href'])
        if any(key.endswith('_cur') for key,_ in parse_qsl(urlsplit(url).query)):
            paging=official_url(url);break
    if last<total and not paging:raise ValueError('GVA archive paginated but next-page route missing')
    return records,bounds,paging


def page_url(route,page):
    parsed=urlsplit(route);args=parse_qsl(parsed.query,keep_blank_values=True)
    keys=[key for key,_ in args if key.endswith('_cur')]
    if len(keys)!=1:raise ValueError('GVA pagination parameter is not unique')
    args=[(key,str(page) if key==keys[0] else value) for key,value in args]
    return official_url(urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode(args),'')))


def decimal_es(value):
    if ',' in value:
        whole,fraction=value.split(',')
        if not fraction.isdigit() or ('.' in whole and not re.fullmatch(r'\d{1,3}(?:\.\d{3})+',whole)):
            raise ValueError('Unrecognized Spanish number')
        return float(whole.replace('.','')+'.'+fraction)
    if re.fullmatch(r'[1-9]\d{0,2}(?:\.\d{3})+',value):return float(value.replace('.',''))
    return float(value)


def power_candidates(text):
    result=[];text=flatten(text)
    for match in NUMBER.finditer(text):
        before=fold(text[max(0,match.start()-115):match.start()]);after=fold(text[match.end():match.end()+65])
        unit=match['unit'];value=decimal_es(match['value'])/(1000 if unit.lower().startswith('kw') else 1)
        if value<=0 or not math.isfinite(value):continue
        markers=[]
        for kind,pattern in (
            ('grid_access',r'capacidad\s+de\s+acceso|\bca\s+concedida'),
            ('storage_module',r'almacenamiento(?:\s+bess)?|baterias'),
            ('pv_inverters',r'\binversores\b|\bpnom\b'),
            ('installed',r'potencia\s+instalada|pot\s*\.?\s*inst\b|potencia\s+a\s+instalar')):
            markers.extend((m.start(),kind) for m in re.finditer(pattern,before))
        kind=max(markers)[1] if markers else None
        if re.match(r'\s*de\s+capacidad\s+de\s+acceso',after):kind='grid_access'
        elif re.match(r'\s*de\s+potencia\s+instalada',after):kind=kind if kind=='storage_module' else 'installed'
        elif re.match(r'\s*de\s+(?:potencia\b|pins\b)',after):kind=kind or 'project_power'
        if unit.lower().endswith('p'):kind='pv_peak'
        if kind:result.append({'value_mw':value,'basis':kind,'original_value':match['value'],'original_unit':unit,
                               'evidence':text[max(0,match.start()-115):match.end()+65]})
    return result


def act_header(text):
    return re.split(r'\b(?:antecedentes|antecedents|hechos)\b',flatten(text),maxsplit=1,flags=re.I)[0][:6000]


def explicit_name(text):
    flat=flatten(text)
    for pattern in [r'denominad[oa]\s*'+QUOTED,
                    r'(?:central\s+fotovoltaica(?:\s+hibridada)?|\bcf|instalaci[oó]n\s+fv)\s*[:\-]?\s*'+QUOTED,
                    r'denominaci[oó]n\s+(?:(?:de\s+la\s+)?instalaci[oó]n)?\s*:\s*([^\n•–]+?)(?=\s*[-•–]\s*(?:tecnolog|emplaz|potencia)|\.\s*(?:tecnolog|ubicaci)|$)']:
        match=re.search(pattern,flat,re.I)
        if match:
            name=match[1].strip(' .;«»“”"')
            if 2<=len(name)<=150:return name
    return None


def classify_current_title(title):
    low=fold(flatten(title))
    if re.search(r'informacion\s+publica|\bip\s+solicitudes',low):return 'PUBLIC_INFO','EARLY'
    # GVA prefixes some current resolutions with a municipality and underscore:
    # 'CHESTE_Res.'. An underscore is not a word boundary in Python regexes.
    if not re.search(r'resolucion|(?<![a-z0-9])res\.',low):return 'OTHER','EARLY'
    if re.search(r'acepta(?:r)?(?:\s+de\s+plano)?\s+el\s+desistimiento|acepta\s+desistimiento',low):return 'WITHDRAWN','BLOCKED'
    if re.search(r'\bdeniega\b|\bdenegacion\b',low):return 'DENIED','BLOCKED'
    # A current resolution dismissing the application for AAP/AAC is a denial,
    # not a new request. Match the first operative predicate, not an appeal,
    # rejected allegations or an older decision quoted later in the title.
    predicate=re.search(r'\bpor la que\s+(.+)',low)
    if predicate and re.match(
        r'se desestima la solicitud\s+'
        r'(?:(?:presentada|formulada)\s+por\s+.{2,200}?[, ]+)?'
        r'de\s+(?:aap\b|aac\b|autorizacion\s+administrativa\s+(?:previa\b|de\s+construccion\b))',
        predicate[1]):
        return 'DENIED','BLOCKED'
    if re.search(r'perdida\s+sobrevenida|desaparicion\s+sobrevenida|terminacion\s+(?:del\s+)?procedimiento',low):return 'PROCEDURE_ENDED','BLOCKED'
    grant=re.search(r'\bse\s+otorga\s+a\b|\botorgando\s+a\b|\bde\s+otorgamiento\s+a\b',low)
    if re.search(r'\bno\s+se\s+otorga\b',low):grant=None
    if grant and re.search(r'\baac\b|construccion',low):return 'CONSTRUCTION_AUTH','AUTHORIZED'
    if grant and re.search(r'\baap\b|autorizacion\s+administrativa\s+previa',low):return 'PRIOR_AUTH','PERMITTING'
    return 'OTHER','EARLY'


def record_fields(record):
    from app.parser import detect_technology,build_project_key
    from app.geo import find_province
    title=flatten(record['title']);documents=record.get('legal_documents',[])
    texts=[d.get('text','') for d in documents if d.get('text')];headers=[act_header(t) for t in texts]
    flags=[{'code':'LEGAL_ACT_IMAGE_ONLY','severity':'INFO','source_url':d['url']} for d in documents if d.get('text_status')=='IMAGE_OR_NO_TEXT']
    cf_scope=bool(REFERENCE.search(title) and re.search(r'(?:para|de)\s+(?:una\s+)?CF\b',title,re.I))
    generation=cf_scope or bool(re.search(r'(?:central|planta|parque|instalaci[oó]n)(?:\s+solar)?\s+(?:fotovoltaic|e[oó]lic|fv)|\bcf\s+(?:denominada|hibridada)|\bbess\b|hibridaci[oó]n\s+con',title,re.I))
    if not generation and re.search(r'subestaci[oó]n|l[ií]nea.*tensi[oó]n',title,re.I):return {'disposition':'GRID_CONTEXT_ONLY'},flags
    if re.search(r'gas\s+natural|\bglp\b|hidrocarburos|autoconsumo',title,re.I):return {'disposition':'NON_TARGET'},flags
    technology=detect_technology(title+'\n'+'\n'.join(headers)+'\n'+'\n'.join(t[:6000] for t in texts))
    if technology is None and cf_scope:technology='PV'
    if technology not in {'PV','WIND','BESS','HYBRID'}:return {'disposition':'NON_TARGET'},flags
    if re.search(r'hibridaci[oó]n|hibridada',title,re.I):technology='HYBRID'
    name=explicit_name(title);name_origin='publication_title'
    if not name:
        candidates=sorted({n for n in (explicit_name(t[:6000]) for t in texts) if n})
        if len(candidates)==1:name=candidates[0];name_origin='linked_official_act'
        elif len(candidates)>1:flags.append({'code':'SOURCE_NAME_DISAGREEMENT','severity':'WARN','values':candidates})
    event_type,stage=classify_current_title(title)
    if event_type=='OTHER':flags.append({'code':'SOURCE_LIFECYCLE_UNMAPPED','severity':'WARN','evidence':title})
    refs=REFERENCE.findall(title)
    reference=re.sub(r'\s*[/ ]\s*','/',refs[0]).upper() if len(set(refs))==1 else None
    if not reference:
        first_refs=[REFERENCE.findall(h) for h in headers];refs=[r[0] for r in first_refs if len(set(r))==1]
        canonical={re.sub(r'\s*[/ ]\s*','/',r).upper() for r in refs}
        if len(canonical)==1:reference=canonical.pop()
    suffix=r'(?:S\.?\s*L\.?(?:\s*U\.?)?|S\.?\s*A\.?(?:\s*U\.?)?)(?!\w)'
    owner_pattern=re.compile(r'(?:otorga\s+a|otorgando\s+a|otorgamiento\s+a|promovid[ao]\s+por|presentada\s+por|solicitud\s+de|de\s+la\s+mercantil)\s+(?:la\s+mercantil\s+)?(.{2,180}?\b'+suffix+r')',re.I)
    owner=None
    for text in [title]+headers:
        match=owner_pattern.search(text)
        if match:owner=match[1].strip(' ,;');break
    province=None
    for text in [title]+headers+[flatten(t[:6000]) for t in texts]:
        candidate,_=find_province(text)
        if candidate in {'Alicante','Alicante/Alacant','Castellón','Castelló','Valencia','València'}:
            province={'Castelló':'Castellón','València':'Valencia','Alicante/Alacant':'Alicante'}.get(candidate,candidate);break
    province_origin='source_text' if province else None
    # Only exact geographic metadata may fill a gap. The source's generic
    # 'Instalaciones autorizadas' category is NEVER evidence for the lifecycle.
    category_provinces=sorted(set(record.get('categories',[])) & {'Valencia','Alicante','Castellón'})
    if len(category_provinces)==1:
        category_province=category_provinces[0]
        if province is None:
            province=category_province;province_origin='official_geographic_category'
        elif province!=category_province:
            flags.append({'code':'SOURCE_PROVINCE_DISAGREEMENT','severity':'WARN',
                          'source_text_province':province,'official_category_province':category_province})
    elif len(category_provinces)>1:
        flags.append({'code':'MULTIPLE_OFFICIAL_PROVINCE_CATEGORIES','severity':'WARN','values':category_provinces})
    main_power=power_candidates(title)
    header_power=[dict(item,source_url=doc['url']) for doc in documents for item in power_candidates(act_header(doc.get('text','')))]
    addition=bool(re.search(r'hibridaci[oó]n.*(?:almacenamiento|bater[ií]as)',title,re.I))
    if technology=='HYBRID' and addition:
        chosen=[p for p in main_power+header_power if p['basis']=='storage_module'];basis='new_storage_module'
    elif technology=='HYBRID':
        chosen=[];basis=None
        if main_power or header_power:flags.append({'code':'MULTI_COMPONENT_POWER_NOT_SUMMED','severity':'INFO'})
    else:
        chosen=[p for p in main_power if p['basis'] in {'installed','project_power'}]
        corroboration=[p for p in header_power if p['basis']=='installed']
        if chosen and corroboration:chosen=chosen+corroboration
        elif not chosen:chosen=corroboration
        basis='installed_or_explicit_project_power'
    powers={round(p['value_mw'],9) for p in chosen};power=next(iter(powers)) if len(powers)==1 else None
    if len(powers)>1:flags.append({'code':'SOURCE_POWER_DISAGREEMENT','severity':'WARN','values_mw':sorted(powers),'evidence':chosen})
    fields={'disposition':'TARGET','project_name':name,'technology':technology,'power_mw':power,'promoter':owner,
            'expediente':reference,'province':province,'ccaa':CCAA,'event_type':event_type,'commercial_stage':stage,
            'evidence':{'name_origin':name_origin if name else None,'reference_original':refs,
                        'power_basis':basis if power is not None else None,'power_assertions':main_power+header_power,
                        'lifecycle_origin':'current_publication_title','explicit_cf_scope':cf_scope,
                        'province_origin':province_origin,'official_province_categories':category_provinces}}
    fields['project_key']=build_project_key(name,technology,province,record['external_id'],reference)
    return fields,flags


def event_from_record(record):
    from app.parser import ParsedEvent
    fields,flags=record_fields(record);record['extraction']=fields;record['quality_flags']=flags
    if fields['disposition']!='TARGET':return None
    pub=date.fromisoformat(record['publication_date']).isoformat();raw=json.dumps(record,ensure_ascii=False,sort_keys=True)
    return ParsedEvent(source_code='GVA_PUBLIC',external_id=record['external_id'],publication_date=pub,
                       title=record['title'],url=record['url'],raw_text=raw,
                       **{k:fields[k] for k in ('technology','power_mw','project_name','promoter','expediente','province','ccaa','event_type','commercial_stage','project_key')})


class GVAPublicCollector:
    code='GVA_PUBLIC'

    def __init__(self,timeout=30,user_agent='SpainRenewablesRadar/0.4',out_dir='reports/gva_public'):
        self.timeout=(8,max(timeout,35));self.output=Path(out_dir)
        self.session=requests.Session();self.session.headers['User-Agent']=user_agent
        retry=Retry(total=2,connect=2,read=1,status=2,backoff_factor=.8,status_forcelist=(429,500,502,503,504),allowed_methods=frozenset({'GET'}))
        self.session.mount('https://',HTTPAdapter(max_retries=retry))
        self.inventory=None;self._fatal=None;self.records={};self._events={}
        self.audit={'source_code':self.code,'source_url':BASE,'complete':False,'detail_errors':{},'processed_days':{},'acquisitions':[],
                    'scope':'OFFICIAL_PUBLISHED_ENTRIES_WITH_TOP_LEVEL_LEGAL_ACTS',
                    'pdf_field_extraction_scope':'first_two_pages; no OCR; full original bytes preserved'}

    def _get(self,url,limit=12000000):
        url=official_url(url)
        for _ in range(5):
            response=self.session.get(url,timeout=self.timeout,allow_redirects=False,stream=True)
            if response.status_code in (301,302,303,307,308):
                location=response.headers.get('Location');response.close()
                if not location:raise ValueError('Official redirect lacks a destination')
                url=official_url(urljoin(url,location));continue
            response.raise_for_status();chunks=[];size=0
            try:
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>limit:raise ValueError('Official source exceeds bounded download size')
                    chunks.append(chunk)
            finally:response.close()
            raw=b''.join(chunks);self.output.mkdir(parents=True,exist_ok=True)
            digest=hashlib.sha256(raw).hexdigest();extension='.pdf' if raw.startswith(b'%PDF-') else '.html'
            filename=digest+extension;(self.output/filename).write_bytes(raw)
            self.audit['acquisitions'].append({'url':url,'file':filename,'sha256':digest,'bytes':len(raw),'retrieved_at':datetime.now(timezone.utc).isoformat()})
            return raw,url
        raise ValueError('Too many GVA redirects')

    def _save(self):
        self.output.mkdir(parents=True,exist_ok=True)
        self.audit['processed_publications']=len(self.records)
        self.audit['target_events']=sum(r.get('extraction',{}).get('disposition')=='TARGET' for r in self.records.values())
        self.audit['source_quality_flags']=sum(len(r.get('quality_flags',[])) for r in self.records.values())
        flags=[dict(external_id=r['external_id'],publication_date=r['publication_date'],source_url=r['url'],severity=f['severity'],code=f['code'],detail=json.dumps(f,ensure_ascii=False)) for r in self.records.values() for f in r.get('quality_flags',[])]
        with (self.output/'source_flags.csv').open('w',newline='',encoding='utf-8-sig') as handle:
            writer=csv.DictWriter(handle,fieldnames=['external_id','publication_date','source_url','severity','code','detail']);writer.writeheader();writer.writerows(flags)
        body=''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row.values())+'</tr>' for row in flags)
        (self.output/'source_flags.html').write_text('<!doctype html><meta charset="utf-8"><title>GVA — verifica fonti</title><h1>GVA — discrepanze e limiti della fonte</h1><p>Nessuna correzione automatica dei dati dubbi.</p><table><tr><th>ID</th><th>Data</th><th>Fonte</th><th>Livello</th><th>Codice</th><th>Dettaglio</th></tr>'+body+'</table>',encoding='utf-8')
        for filename,data in [('coverage.json',self.audit),('records.json',list(self.records.values()))]:
            (self.output/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

    def _load(self):
        if self.inventory is not None:return
        if self._fatal:raise RuntimeError(self._fatal)
        try:
            raw,url=self._get(BASE);rows,bounds,route=parse_listing(raw,url);first,last,total=bounds
            if first!=1:raise ValueError('GVA archive did not start at first row')
            size=last;pages=math.ceil(total/size)
            if pages>250:raise ValueError('GVA source exceeds reviewed page bound')
            inventory=list(rows)
            for page in range(2,pages+1):
                raw,url=self._get(page_url(route,page));found,bounds,_=parse_listing(raw,url)
                if bounds!=(1+(page-1)*size,min(page*size,total),total):raise ValueError('GVA pagination ignored or catalogue changed')
                inventory.extend(found);time.sleep(.1)
            if len(inventory)!=total or len({r['external_id'] for r in inventory})!=total:raise ValueError('GVA archive missing or duplicate source identities')
            raw,url=self._get(BASE);final,bounds,_=parse_listing(raw,url)
            if bounds[2]!=total or [(r['external_id'],r['publication_date']) for r in final]!=[(r['external_id'],r['publication_date']) for r in rows]:raise ValueError('GVA archive changed during acquisition')
            self.inventory=inventory
            self.audit.update(complete=True,declared_records=total,archive_records=len(inventory),pages=pages,distinct_ids=len({r['external_id'] for r in inventory}))
            (self.output/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as exc:self._fatal=str(exc);raise
        finally:self._save()

    def _detail(self,item):
        record=dict(item);raw,url=self._get(item['url'])
        soup=BeautifulSoup(raw,'html.parser');article=soup.select_one('.asset-full-content')
        if article is None:raise ValueError('GVA detail body missing: '+item['external_id'])
        record['detail_dates']=[t.get_text(' ',strip=True) for t in article.select('.date-info')]
        for tag in article.select('script,style'):tag.decompose()
        record['article_text']=article.get_text('\n',strip=True);record['legal_documents']=[];record['technical_document_links']=[]
        seen=set();directory_links=[urljoin(url,a['href']) for a in article.select('.iframe-error-protocol a[href]')]
        for directory in dict.fromkeys(directory_links):
            content,document_url=self._get(directory)
            if content.startswith(b'%PDF-'):links=[(document_url,'Directly linked official act')]
            else:
                ds=BeautifulSoup(content,'html.parser');links=[]
                for a in ds.select('a[href]'):
                    link=urljoin(document_url,a['href']);path=unquote(urlsplit(link).path)
                    if not path.lower().endswith('.pdf'):continue
                    label=a.get_text(' ',strip=True) or path.rsplit('/',1)[-1];official_url(link)
                    if LEGAL_LABEL.search(label):links.append((link,label))
                    else:record['technical_document_links'].append({'url':link,'label':label})
            for link,label in links:
                if link in seen:continue
                seen.add(link);pdf=content if content.startswith(b'%PDF-') and link==document_url else self._get(link)[0]
                if not pdf.startswith(b'%PDF-'):raise ValueError('Linked GVA legal PDF returned non-PDF content')
                from pypdf import PdfReader
                reader=PdfReader(io.BytesIO(pdf));text='\n'.join(p.extract_text() or '' for p in list(reader.pages)[:2])
                record['legal_documents'].append({'url':link,'label':label,'sha256':hashlib.sha256(pdf).hexdigest(),'text':text,
                    'pages_total':len(reader.pages),'pages_extracted':min(len(reader.pages),2),'text_status':'READABLE' if len(text.strip())>50 else 'IMAGE_OR_NO_TEXT'})
        return record

    def collect_day(self,day):
        self._load()
        if day.isoformat() in self._events:return self._events[day.isoformat()]
        if day.isoformat() in self.audit['detail_errors']:raise RuntimeError(self.audit['detail_errors'][day.isoformat()])
        selected=[r for r in self.inventory if r['publication_date']==day.isoformat()];events=[]
        try:
            for item in selected:
                record=self._detail(item);event=event_from_record(record);self.records[item['external_id']]=record
                if event is not None:events.append(event)
            self._events[day.isoformat()]=events
            self.audit['processed_days'][day.isoformat()]={'status':'OK','publications':len(selected),'target_events':len(events)}
            return events
        except Exception as exc:
            self.audit['detail_errors'][day.isoformat()]=str(exc)
            self.audit['processed_days'][day.isoformat()]={'status':'ERROR','publications':len(selected)}
            raise
        finally:self._save()

    def persist_metadata(self,conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS regional_public_metadata (
            source_code TEXT NOT NULL,external_id TEXT NOT NULL,project_key TEXT NOT NULL,
            web_publication_date TEXT NOT NULL,source_url TEXT NOT NULL,evidence_json TEXT NOT NULL,
            PRIMARY KEY(source_code,external_id),FOREIGN KEY(project_key) REFERENCES projects(project_key))''')
        for record in self.records.values():
            event=conn.execute('SELECT project_key FROM events WHERE source_code=? AND external_id=?',(self.code,record['external_id'])).fetchone()
            if event is None:continue
            conn.execute('''INSERT INTO regional_public_metadata VALUES (?,?,?,?,?,?)
                ON CONFLICT(source_code,external_id) DO UPDATE SET project_key=excluded.project_key,
                web_publication_date=excluded.web_publication_date,source_url=excluded.source_url,evidence_json=excluded.evidence_json''',
                (self.code,record['external_id'],event['project_key'],record['publication_date'],record['url'],
                 json.dumps({'extraction':record['extraction'],'quality_flags':record['quality_flags'],
                             'legal_documents':[{k:v for k,v in d.items() if k!='text'} for d in record['legal_documents']]},ensure_ascii=False)))
        conn.commit()
