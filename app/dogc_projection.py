"""Project only evidenced DOGC energy acts; keep local leads and corrections separate.

No changes to the semantic record, the original pages or a previous event.
A screening is not a DIA, a municipal approval is not an energy permit, and
PV/BESS powers are never added. INE is the sole authority for municipality links.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import re
import unicodedata

from app.dogc_semantics import normalized, verify_evidence
from app.parser import ParsedEvent, build_project_key

EVENTS = {
    'PRIOR_AND_CONSTRUCTION_AUTH': ('CONSTRUCTION_AUTH', 'AUTHORIZED'),
    'PUBLIC_UTILITY_GRANTED': ('PUBLIC_UTILITY', 'AUTHORIZED'),
    'ENVIRONMENTAL_DIA_COMPATIBLE': ('DIA', 'PERMITTING'),
    'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA': ('ENVIRONMENTAL_SCREENING', 'PERMITTING'),
    'ORDINARY_EIA_REQUIRED': ('ENVIRONMENTAL_SCREENING', 'PERMITTING'),
    'PUBLIC_INFO_AUTHORIZATION_REQUEST': ('PUBLIC_INFO', 'EARLY'),
    'PUBLIC_INFO_PUBLIC_UTILITY': ('PUBLIC_INFO', 'EARLY'),
    'PUBLIC_INFO_LAND_USE': ('PUBLIC_INFO', 'EARLY'),
}
PROVINCES = {'Barcelona', 'Girona', 'Lleida', 'Tarragona'}


def place_norm(value):
    value = unicodedata.normalize('NFKD', value).casefold()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def place_aliases(name):
    aliases = {place_norm(name)}
    if ',' in name:
        base, article = name.rsplit(',', 1)
        article = article.strip()
        if place_norm(article) in {'el','la','els','les','l'}:
            aliases.add(place_norm(article + (' ' if not article.endswith("'") else '') + base.strip()))
    # The location clause expands Catalan "del" for leading article names.
    # Apply the same exact grammar transformation to official INE names too,
    # including internal contractions (Parets del Vallès, Cabra del Camp).
    # Keep original aliases; homonymous code matches remain unresolved.
    aliases.update(re.sub(r"\bdel\s+", "de el ", alias) for alias in tuple(aliases))
    return aliases


def project_geography(title, catalog):
    """Longest exact official names within the current title's location clause.

    Strip county/province labels, not municipality names; never consult applicant
    addresses or a signature. Residual place words keep the province unresolved.
    """
    title = normalized(title)
    anchor = re.search(r"als? termes? municipals?\s+", title, re.I)
    if not anchor:
        return {'status':'UNRESOLVED', 'municipalities':[], 'provinces':[], 'source_quote':None,
                'unresolved_text':None, 'ambiguous_codes':[]}
    scope = re.split(r'\(exp\.?|\(ref\.?', title[anchor.end():], maxsplit=1, flags=re.I)[0]
    scope = re.split(r",?\s+i la seva infraestructura", scope, maxsplit=1, flags=re.I)[0]
    view = re.sub(r"(?:a la\s+)?(?:comarca|província)\s+(?:de |del |d')?[^;,()]+", '', scope, flags=re.I)
    view = re.sub(r'\([^)]*\)', '', view)
    view = place_norm(re.sub(r'\bdel\s+', 'de el ', view, flags=re.I))
    hits=[]
    for town in catalog:
        if town.province not in PROVINCES: continue
        for alias in place_aliases(town.name):
            if len(alias)<3: continue
            for match in re.finditer(r'(?<!\w)'+re.escape(alias)+r'(?!\w)', view):
                hits.append((match.start(),match.end(),town))
    # Prefer the longest complete municipality, e.g. Brunyola i Sant Martí Sapresa.
    selected=[]; occupied=set(); ambiguous=[]
    for a,b,town in sorted(hits,key=lambda h:(-(h[1]-h[0]),h[0],h[2].code)):
        if any(p in occupied for p in range(a,b)): continue
        same={h[2].code for h in hits if h[0]==a and h[1]==b}
        if len(same)>1: ambiguous.extend(sorted(same))
        selected.append(town);occupied.update(range(a,b))
    residual=''.join(' ' if i in occupied else c for i,c in enumerate(view))
    residual=' '.join(word for word in residual.split() if word not in {'i','de','del','d','l','el','la','els','les','al','als'})
    unique={town.code:town for town in selected}
    provinces=sorted({t.province for t in unique.values()})
    status=('UNRESOLVED' if residual or ambiguous or not unique else 'MULTI_PROVINCE' if len(provinces)>1 else 'RESOLVED')
    return {'status':status,'municipalities':[{'code':t.code,'name':t.name,'province':t.province} for t in sorted(unique.values(),key=lambda t:t.code)],
            'provinces':provinces,'source_quote':scope,'unresolved_text':residual or None,'ambiguous_codes':sorted(set(ambiguous))}


def scalar_capacity(record, technology):
    """Use a project-level headline assertion, retaining its basis and evidence.

    No sum, device count multiplication, typographical unit repair or scalar for
    mixed components. Body assertions corroborate but cannot replace a conflicting
    headline. A headline-only quantity remains explicitly labelled as such.
    """
    if record['capacity_conflicts'] or len(record['technologies'])!=1:
        return None, {'status':'CONFLICT' if record['capacity_conflicts'] else 'MULTI_COMPONENT_NO_SCALAR'}
    if any(c['role']!='PROJECT_COMPONENT' for c in record['components']):
        return None, {'status':'EXISTING_OR_EXPANSION_NO_SCALAR'}
    heads=[q for q in record['capacity_observations'] if q['scope']=='INDEX_TITLE'
           and q['component']==technology and q['normalized_unit']=='MW'
           and q['basis'] in {'NOMINAL_AC','UNSPECIFIED_POWER','PEAK_DC','INSTALLED_POWER'}]
    for basis in ('NOMINAL_AC','INSTALLED_POWER','UNSPECIFIED_POWER','PEAK_DC'):
        candidates=[q for q in heads if q['basis']==basis]
        values={Decimal(q['normalized_value']) for q in candidates}
        if len(values)>1: return None, {'status':'AMBIGUOUS_PROJECT_LEVEL_CAPACITY'}
        if len(values)==1:
            value=next(iter(values))
            if value<=0: return None, {'status':'NONPOSITIVE_SOURCE_VALUE'}
            chosen=candidates[0]
            return float(value), {'status':'EXPLICIT_PROJECT_HEADLINE','basis':basis,
                'source_number':chosen['source_number'],'source_unit':chosen['source_unit'],
                'evidence':chosen['evidence'],'aggregation_rule':'one project only; never components or provinces'}
    return None, {'status':'NO_UNAMBIGUOUS_PROJECT_HEADLINE_POWER'}


def event_from_record(record, pages, catalog):
    """Return (event or None, evidence). Non-energy records remain audited leads."""
    verify_evidence(record,pages)
    if not record.get('document_classified') or record['category']=='REVIEW_REQUIRED':
        raise ValueError('DOGC unresolved operative decision: '+record['document_id'])
    if record['category']!='ENERGY_PROJECT':
        return None, {'disposition':record['category'],'semantic_record':record}
    if record['event'] not in EVENTS or not record.get('decision'):
        raise ValueError('DOGC event has no validated lifecycle mapping')
    name=(record.get('project_name') or {}).get('value')
    if not name or not record['technologies']:
        raise ValueError('Energy act lacks evidenced plant identity or technology')
    references=sorted({x['value'] for x in record['primary_references']})
    fue=[ref for ref in references if re.fullmatch(r'FUE-\d{4}-\d{8}',ref)]
    fallback=[ref for ref in references if re.fullmatch(r'OTA[A-Z]{3}\d{8}|\d{4}/\d{6}/[A-Z]',ref)]
    chosen=fue or fallback
    if not chosen:
        raise ValueError('No reliable current administrative reference; retain for identity review')
    technologies=record['technologies']
    existing_pv=any(c['role']=='EXISTING_PV_CONTEXT' for c in record['components'])
    technology='BESS' if existing_pv and 'BESS' in technologies else technologies[0] if len(technologies)==1 else 'HYBRID'
    geography=project_geography(record['source_title'],catalog)
    province=geography['provinces'][0] if geography['status']=='RESOLVED' else None
    power,capacity=scalar_capacity(record,technology)
    event_type,stage=EVENTS[record['event']]
    external_id=record['document_id']
    if len(fue)>1:
        # The current act explicitly treats both dossiers as one hybrid project.
        key=hashlib.sha1(('DOGC|joint-project|'+'|'.join(fue)).encode()).hexdigest()[:20]
        expediente=None
    else:
        expediente=chosen[0]
        key=build_project_key(name,technology,province,'DOGC:'+external_id,expediente)
    event=ParsedEvent(source_code='DOGC',external_id=external_id,publication_date=record['publication_date'],
        title=record['source_title'],url=record['source_url'],raw_text='\n\n'.join(p['text'] for p in pages),
        technology=technology,power_mw=power,project_name=name,promoter=(record.get('proponent') or{}).get('value'),
        expediente=expediente,province=province,ccaa='Cataluña',event_type=event_type,commercial_stage=stage,project_key=key)
    flags=[{'code':code,'severity':'WARN' if code=='SOURCE_CAPACITY_CONFLICT' else 'INFO'} for code in record['flags']]
    if len(fue)>1:flags.append({'code':'JOINT_DOSSIERS_PRESERVED_NO_SINGLE_EXPEDIENTE','severity':'INFO','references':fue})
    if geography['status']=='UNRESOLVED':flags.append({'code':'DOGC_GEOGRAPHY_UNRESOLVED','severity':'INFO','unresolved_text':geography['unresolved_text']})
    evidence={'extraction':{'semantic_record':record,'geography':geography,'capacity_selection':capacity,
             'current_references':references,'identity_rule':'exact current dossier; explicit joint dossiers kept together'},
        'quality_flags':flags,'legal_documents':[{'url':record['source_url'],'pdf_url':record['source_pdf_url'],
             'sha256':record['pdf_sha256'],'format':'PDF','page_count':record['page_count'],'retrieved_at':record['source_retrieved_at']} ]}
    return event,evidence
