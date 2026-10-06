"""Conservative BOPV act classification with exact source-paragraph evidence.

Pure projection, no collector enablement or database writes. Different plants
inside an act remain distinct; project values never come from equipment sums,
other projects, promoter addresses or a historical authorization reference.
"""
from __future__ import annotations
from decimal import Decimal
from datetime import date
import hashlib
import re
from bs4 import BeautifulSoup

FLAGS=re.I
QUOTE=r'[«“"]([^»”"\n]{1,160})[»”"]'
NUM=r'\d+(?:[.,]\d+)*'
REF=re.compile(r'\b\d{2}\s*[-–]\s*GE\s*[-–]\s*Y\s*[-–]\s*\d{4}\s*[-–]\s*\d{5}\b')
UNIT=re.compile(r'(?<![\w.,])('+NUM+r')\s*(kVAn|kVA|MVA|MWh|kWh|MWp|kWp|MWn|kWn|MW|kW|Wp|W)\b',re.I)


def clean(value):return ' '.join(value.split()).strip()


def number(value):
    if not isinstance(value,str) or not re.fullmatch(NUM,value):raise ValueError('Invalid source number')
    if ',' in value:
        if not re.fullmatch(r'(?:\d+|\d{1,3}(?:\.\d{3})+),\d+',value):raise ValueError('Invalid source number')
        return Decimal(value.replace('.','').replace(',','.'))
    if re.fullmatch(r'[1-9]\d{0,2}(?:\.\d{3})+',value):return Decimal(value.replace('.',''))
    result=Decimal(value)
    if not result.is_finite():raise ValueError('Nonfinite source number')
    return result


def paragraphs_from_html(raw,encoding):
    soup=BeautifulSoup(raw.decode(encoding,errors='strict'),'html.parser')
    nodes=soup.select('p.BOPVTitulo, p[class^="BOPVDetalle"], .BOPVClave, p.BOPVFirmaLugFec')
    if not nodes or len(nodes)>20000 or len(soup.select('.BOPVTitulo'))!=1:
        raise ValueError('Missing BOPV original article paragraphs')
    return [{'index':n,'text':node.get_text('',strip=False),'source_class':node.get('class',[])} for n,node in enumerate(nodes)]


def evidence(paragraph,start=0,end=None):
    text=paragraph['text'];end=len(text) if end is None else end
    if not 0<=start<end<=len(text):raise ValueError('Invalid original evidence span')
    return {'paragraph':paragraph['index'],'start':start,'end':end,'quote':text[start:end],
            'paragraph_sha256':hashlib.sha256(text.encode()).hexdigest()}


def check_evidence(paragraphs,span):
    p=paragraphs[span['paragraph']]
    if evidence(p,span['start'],span['end'])!=span:raise ValueError('Evidence differs from original paragraph')


def find(paragraphs,pattern):
    return [(p,m) for p in paragraphs if (m:=re.search(pattern,p['text'],FLAGS))]


def reference(paragraphs):
    hits=find(paragraphs,r'^\s*[•–-]?\s*Expediente\s*:?\s*('+REF.pattern+r')')
    if len(hits)!=1:return None,[]
    p,m=hits[0]
    return m[1],[evidence(p,m.start(1),m.end(1))]


def applicant(paragraphs):
    hits=find(paragraphs,r'(?:Solicitante|Peticionario):\s*(.+?)(?:\s*\((?:CIF|NIF):|,\s*con\s+CIF|$)')
    if len(hits)!=1:return None,[]
    p,m=hits[0];return clean(m[1]),[evidence(p,m.start(1),m.end(1))]


def location(paragraphs,title):
    # Site clauses only. Routing towns for evacuation are kept separately.
    patterns=[r'ubicados\s+en\s+el\s+t[eé]rmino\s+municipal\s+de\s+([^.(]+)',
              r'\ben\s+(?:el\s+t[eé]rmino\s+municipal|los\s+municipios|los\s+t[eé]rminos\s+municipales)\s+de\s+([^.(]+)',
              r'T[eé]rmino(?:s)?\s+municipal(?:es)?\s+afectado(?:s)?:\s*([^.(]+)']
    hits=[]
    for pattern in patterns:
        hits=find(paragraphs,pattern)
        if hits:break
    clause=None;ev=[]
    if hits:
        p,m=hits[0];clause=clean(m[1]);ev=[evidence(p,m.start(1),m.end(1))]
    provinces=set(re.findall(r'\((Álava|Araba|Gipuzkoa|Bizkaia)\)',title,FLAGS))
    province=next(iter(provinces)) if len(provinces)==1 else None
    return {'site_municipalities_text':clause,'province':province,'ccaa':'País Vasco'},ev


def quantities(paragraphs):
    out=[]
    for p in paragraphs:
        for m in UNIT.finditer(p['text']):
            unit=m[2];kind=('APPARENT_POWER' if 'va' in unit.lower() else 'ENERGY' if unit.lower().endswith('wh')
                  else 'SOLAR_PEAK_POWER' if unit.lower().endswith('p')
                  else 'NOMINAL_ACTIVE_POWER' if unit.lower().endswith('n') else 'ACTIVE_POWER')
            out.append({'original_value':m[1],'unit':unit,'value':str(number(m[1])),
                        'kind':kind,'automatically_summable':False,'evidence':evidence(p,m.start(),m.end())})
    return out


def classify_document(record,paragraphs):
    if (not paragraphs or any(p['index']!=i for i,p in enumerate(paragraphs))
            or clean(paragraphs[0]['text'])!=record['title']):
        raise ValueError('Original title/paragraph sequence mismatch')
    if not re.fullmatch(r'\d{4}/\d{5}',record['external_id']):raise ValueError('Invalid disposition identity')
    date.fromisoformat(record['publication_date'])
    title=record['title'];body=paragraphs[1:];assets=[];decisions=[]
    event,stage=None,None
    request=re.search(r'\bse\s+somet(?:e|en)\s+a\s+informaci[oó]n\s+p[uú]blica\b.{0,180}?\bsolicitud(?:es)?\b',title,FLAGS)
    if request and title.startswith('ANUNCIO'):
        confirms=find(body[:8],r'\bse\s+somet(?:e|en)\s+a\s+informaci[oó]n\s+p[uú]blica\b|\bse\s+anuncia\s+la\s+solicitud\b')
        if confirms:
            event,stage='PUBLIC_INFO','EARLY';decisions=[evidence(paragraphs[0],request.start(),request.end()),evidence(confirms[0][0])]
    operative=[i for i,p in enumerate(body) if clean(p['text']).upper()=='RESUELVO:']
    if title.startswith('RESOLUCIÓN') and len(operative)==1:
        current=body[operative[0]+1:]
        first=current[0] if current else None
        if first and re.match(r'Primero\.\s*[–-]\s*Formular,\s+a\s+los\s+solos\s+efectos\s+ambientales,\s+declaraci[oó]n\s+de\s+impacto\s+ambiental',first['text'],FLAGS):
            event,stage='DIA','PERMITTING';decisions=[evidence(first)]
            # Do not treat a negative environmental conclusion as permission.
            if re.search(r'\bdesfavorable\b',first['text'],FLAGS):stage='BLOCKED'
    if not event:
        return {'external_id':record['external_id'],'classification':'REVIEW_REQUIRED','reason':'UNSUPPORTED_OPERATIVE_DECISION','assets':[]}
    self_use=find(body[:20],r'Finalidad:.*\bpara\s+autoconsumo\b')
    group_applicant,app_ev=applicant(body[:15])
    group_ref,ref_ev=reference(body)
    shared_ref=False
    # Enumerated wind cluster: names are explicit, not a Roman-number expansion.
    clusters=find(body,r'Cl[uú]ster\s+e[oó]lico\s+formado\s+por\s+.{0,30}?\((\d+)\)\s+parques\s+e[oó]licos\s+(.+?)\.\s*Cada\s+uno\s+de\s+estos\s+parques\s+cuenta\s+con\s+una\s+potencia\s+instalada\s+de\s+('+NUM+r')\s*MW\b')
    definitions=[]
    if clusters:
        if len(clusters)!=1:raise ValueError('Ambiguous cluster definitions')
        p,m=clusters[0];names=re.findall(QUOTE,m[2]);shared_ref=True
        if len(names)!=int(m[1]) or len(set(names))!=len(names):raise ValueError('Cluster count/names disagree')
        for name in names:
            own=find(body,r'^\s*[–-]?\s*[«“"](?:PE\s+)?'+re.escape(name)+r'[»”"],\s*(.+)$')
            owner=clean(own[0][1][1]) if len(own)==1 else None
            owner_ev=[evidence(own[0][0])] if len(own)==1 else []
            definitions.append({'name':name,'tech':'WIND','power':float(number(m[3])),
                'power_evidence':[evidence(p,m.start(),m.end())],'scope':[p],
                'ref':group_ref,'ref_evidence':ref_ev,'owner':owner,'owner_evidence':owner_ev,
                'name_evidence':[evidence(p,m.start(2),m.end(2))]})
    else:
        named_power=list(re.finditer(QUOTE+r'\s*\(('+NUM+r')\s*MW\)',title,FLAGS))
        if len(named_power)>1 and 'fotovoltaic' in title.casefold():
            # A dossier heading opens a project section. References to shared
            # evacuation plants inside the section are not the project's ID.
            sections=[]
            for i,p in enumerate(body):
                if re.match(r'^\s*[•–-]?\s*Expediente\b',p['text'],FLAGS):sections.append(i)
            for name_power in named_power:
                name=name_power[1];matches=[]
                for j,start in enumerate(sections):
                    part=body[start:(sections[j+1] if j+1<len(sections) else len(body))]
                    hit=find(part,r'^\s*[•–-]?\s*Proyecto\s*[«“"]'+re.escape(name)+r'[»”"]\s+consistente\s+en')
                    if hit:matches.append((part,hit[0][0]))
                if len(matches)!=1:raise ValueError('No unique project/dossier section')
                part,name_p=matches[0];ref,rev=reference(part[:1])
                plant_paragraphs=[p for p in part if re.search(r'Planta\s+solar\s+fotovoltaica\s*[«“"]'+re.escape(name)+r'[»”"]',p['text'],FLAGS)]
                definitions.append({'name':name,'tech':'PV','power':float(number(name_power[2])),
                    'power_evidence':[evidence(paragraphs[0],name_power.start(),name_power.end())],
                    'scope':plant_paragraphs or part,'ref':ref,'ref_evidence':rev,'owner':group_applicant,'owner_evidence':app_ev,
                    'name_evidence':[evidence(name_p)]})
        elif event=='DIA':
            p=current[0]
            m=re.search(r'parque\s+e[oó]lico\s*'+QUOTE+r'\s*\(('+NUM+r')\s*MW\)',p['text'],FLAGS)
            if m:
                owner=re.search(r'promovido\s+por\s+(.+?),\s+en\s+los\s+t[eé]rminos',p['text'],FLAGS)
                definitions.append({'name':m[1],'tech':'WIND','power':float(number(m[2])),
                    'power_evidence':[evidence(p,m.start(),m.end())],'scope':[p],'ref':group_ref,'ref_evidence':ref_ev,
                    'owner':clean(owner[1]) if owner else None,'owner_evidence':[evidence(p,owner.start(1),owner.end(1))] if owner else [],
                    'name_evidence':[evidence(p,m.start(1),m.end(1))]})
        else:
            m=re.search(r'parque\s+e[oó]lico\s+(?:denominado\s+)?'+QUOTE,title,FLAGS)
            if m:
                power=find(body,r'Potencia\s+bruta\s+instalada:\s*('+NUM+r')\s*MW\b')
                values={number(x[1][1]) for x in power}
                definitions.append({'name':m[1],'tech':'WIND','power':float(next(iter(values))) if len(values)==1 else None,
                    'power_evidence':[evidence(p,x.start(),x.end()) for p,x in power],
                    'scope':body[:12],'ref':group_ref,'ref_evidence':ref_ev,'owner':group_applicant,'owner_evidence':app_ev,
                    'name_evidence':[evidence(paragraphs[0],m.start(1),m.end(1))]})
            elif self_use:
                name=find(body,r'Proyecto\s*'+QUOTE+r'\s+consistente\s+en')
                if len(name)==1:
                    p,m=name[0]
                    definitions.append({'name':m[1],'tech':'HYBRID','power':None,'power_evidence':[],
                        'scope':body[:20],'ref':group_ref,'ref_evidence':ref_ev,'owner':group_applicant,'owner_evidence':app_ev,
                        'name_evidence':[evidence(p,m.start(1),m.end(1))]})
    if not definitions:
        return {'external_id':record['external_id'],'classification':'REVIEW_REQUIRED','reason':'UNSUPPORTED_ASSET_STRUCTURE','assets':[]}
    for d in definitions:
        geo,gev=location(d['scope'],title)
        flags=[]
        if d['power'] is not None and (d['power'] < 0 or d['power'] > 100000):
            raise ValueError('Project power outside a reviewed range')
        # A current explicitly named title value must not contradict the
        # equally explicit per-plant/operative value. Keep both spans, not a sum.
        title_power=list(re.finditer(r'(?:[«“"])?'+re.escape(d['name'])+r'(?:[»”"])?\s*\(('+NUM+r')\s*MW\)',title,FLAGS))
        if title_power and d['power'] is not None and any(number(m[1])!=Decimal(str(d['power'])) for m in title_power):
            d['power']=None
            d['power_evidence']+= [evidence(paragraphs[0],m.start(),m.end()) for m in title_power]
            flags.append('EXPLICIT_TITLE_AND_CURRENT_PROJECT_POWER_CONFLICT')
        if event=='DIA':
            operative_name=re.search(r'parque\s+e[oó]lico\s+(?:[«“"])?'+re.escape(d['name'])+r'(?:[»”"])?\s*\(',title,FLAGS)
            if operative_name is None:raise ValueError('Title and operative plant identities differ')
        if not d['ref']:flags.append('OWN_EXPEDIENTE_NOT_REPORTED')
        if not d['owner']:flags.append('OWNER_NOT_UNAMBIGUOUS')
        if d['power'] is None:flags.append('NO_UNAMBIGUOUS_ACTIVE_PROJECT_MW')
        if any('Véase el .PDF' in p['text'] for p in paragraphs):flags.append('SOME_TABLES_AVAILABLE_ONLY_IN_OFFICIAL_PDF')
        normalized_ref=re.sub(r'\s*[-–]\s*','-',d['ref']) if d['ref'] else None
        basis=['BOPV',normalized_ref or record['external_id'],d['name']]
        assets.append({'source_code':'BOPV','document_external_id':record['external_id'],
            'source_url':record['source_url'],'publication_date':record['publication_date'],
            'project_name':d['name'],'technology':d['tech'],'power_mw':d['power'],
            'promoter':d['owner'],'applicant':group_applicant,'expediente':d['ref'],
            'expediente_shared_by_explicit_plants':shared_ref,'identity_basis':basis,
            'asset_key':hashlib.sha256(('\n'.join(basis)).encode()).hexdigest()[:24],
            'identity_is_provisional':d['ref'] is None,**geo,
            'event_type':event,'commercial_stage':stage,'permit_to_build_inferred':False,
            'epc_status':'EPC_UNKNOWN','epc':None,'work_start':None,'work_end':None,
            'power_basis':'explicit_source_project_active_power' if d['power'] is not None else None,
            'quality_flags':flags,'evidence':{'decision':decisions,'name':d['name_evidence'],
                'power':d['power_evidence'],'reference':d['ref_evidence'],'owner':d['owner_evidence'],'location':gev}})
    if len({a['asset_key'] for a in assets})!=len(assets):raise ValueError('Duplicate plant identity inside act')
    result={'external_id':record['external_id'],'classification':'SELF_CONSUMPTION_LEAD' if self_use else 'ENERGY_ACT',
        'source_url':record['source_url'],'publication_date':record['publication_date'],'assets':assets,
        'quantities':quantities(paragraphs),'scope_evidence':[evidence(p) for p,_ in self_use],
        'source_paragraphs':paragraphs,'source_text_sha256':hashlib.sha256('\n'.join(p['text'] for p in paragraphs).encode()).hexdigest(),
        'database_events_created':0,'collector_enabled':False}
    for asset in assets:
        for spans in asset['evidence'].values():
            for span in spans:check_evidence(paragraphs,span)
    return result
