"""Explicit named storage plants in a shared act, not one invented hybrid plant.

Accept only a full plant list repeated in the operative decision, with each-plant
power/energy independently corroborated by the current technical description.
No developer-to-plant allocation is inferred. Group references remain shared.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import re

from app.dogc_semantics import Document, NUMBER, decimal_number, normalized, technical_ranges, verify_evidence
from app.parser import ParsedEvent

COUNTS = {'dues': 2, 'tres': 3, 'quatre': 4, 'cinc': 5, 'sis': 6, 'set': 7, 'vuit': 8, 'nou': 9, 'deu': 10}
HEAD = re.compile(r"les plantes d'emmagatzematge\s+(?P<names>BESS .+?), de potència instal·lada(?: de)?\s+(?P<mw>" + NUMBER + r")\s*MW i\s+(?P<mwh>" + NUMBER + r")\s*MWh cadascuna", re.I)
TECH = re.compile(r"implantació de (?P<count>dues|tres|quatre|cinc|sis|set|vuit|nou|deu|[2-9]|10) plantes d'emmagatzematge d'energia de\s+(?P<mw>" + NUMBER + r")\s*MW de potència instal·lada unitària i\s+(?P<mwh>" + NUMBER + r")\s*MWh de capacitat d'emmagatzematge.{0,60}?cadascuna", re.I)


def plant_names(value):
    names = re.split(r',\s*|\s+i\s+(?=BESS\b)', value)
    if not 2 <= len(names) <= 10 or len(set(names)) != len(names):
        raise ValueError('Ambiguous or duplicated named-plant list')
    if any(not re.fullmatch(r'BESS\s+[\wÀ-ÿ .\'-]{2,90}', name) for name in names):
        raise ValueError('Plant names must be individually explicit; ranges are not expanded')
    return names


def extract_named_assets(doc, title, decision):
    head = HEAD.search(title)
    if not head or not decision:
        raise ValueError('Multi-plant act lacks explicit each-plant heading/decision')
    names = plant_names(head['names'])
    operative = normalized(' '.join(span['quote'] for span in decision['evidence']))
    current = HEAD.search(operative)
    if not current or set(plant_names(current['names'])) != set(names):
        raise ValueError('Current operative plant list differs from heading')
    ranges = technical_ranges(doc, 'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA')
    technical = [match for a,b in ranges for match in TECH.finditer(doc.text,a,b)]
    if len(technical) != 1:
        raise ValueError('Each-plant quantities not uniquely corroborated in technical body')
    body = technical[0]
    count = COUNTS.get(body['count'].lower()) or int(body['count'])
    if count != len(names):
        raise ValueError('Explicit plant count and plant list disagree')
    for unit in ('mw','mwh'):
        values = {decimal_number(m[unit]) for m in (head,current,body)}
        if len(values) != 1 or next(iter(values)) <= 0:
            raise ValueError('Multi-plant source capacity conflict: '+unit)
    heading = doc.find(re.escape(head[0]), before=len(doc.pages[0].text))
    if not heading:
        raise ValueError('Group heading is absent from the original first page')
    promoter = doc.find(r"promogudes per les empreses\s+(.{2,350}?)(?=\.\s|[—–]2|$)", before=doc.text.find('Marc normatiu'))
    # Retain a group statement, never pretend the first company owns every plant.
    promoters = doc.value(promoter[1],promoter,1) if promoter else None
    return {'plants':[doc.value(name,doc.find(re.escape(name)+r'(?!\w)',before=len(doc.pages[0].text))) for name in sorted(names)],
            'plant_count':count,'per_plant_power_mw':str(decimal_number(head['mw'])),
            'per_plant_energy_mwh':str(decimal_number(head['mwh'])),
            'quantity_evidence':{'heading':doc.evidence(*heading.span()),'technical':doc.evidence(*body.span()),
                                 'operative':decision['evidence']},
            'scope':'EACH_EXPLICITLY_NAMED_PLANT_NOT_GROUP_TOTAL',
            'group_promoters':promoters, 'individual_promoter_allocation':None,
            'sum_as_additional_group_project':False}


def project_named_assets(record, pages, catalog):
    from app.dogc_projection import EVENTS, project_geography
    verify_evidence(record,pages)
    group = record['named_asset_group']
    if not record.get('document_classified') or record['category']!='ENERGY_PROJECT' or record['technologies']!=['BESS'] or record['event'] not in EVENTS:
        raise ValueError('Named-plant projection requires a classified BESS act')
    rebuilt=extract_named_assets(Document(pages),normalized(record['source_title']),record['decision'])
    if rebuilt!=group:
        raise ValueError('Named-plant allocation differs from original source')
    refs=sorted({x['value'] for x in record['primary_references']})
    # Do not choose one of several proceedings or lift an unrelated body reference.
    if len(refs)!=1 or not re.fullmatch(r'OTA[A-Z]{3}\d{8}|FUE-\d{4}-\d{8}',refs[0]):
        raise ValueError('Named-plant shared administrative identity is ambiguous')
    geography=project_geography(record['source_title'],catalog)
    province=geography['provinces'][0] if geography['status']=='RESOLVED' else None
    kind,stage=EVENTS[record['event']];out=[]
    for plant in group['plants']:
        name=plant['value']
        # Full normalized name, not ordinal position in a list; repeated acts accumulate.
        identity=hashlib.sha256((refs[0]+'|'+normalized(name).casefold()).encode()).hexdigest()[:24]
        event=ParsedEvent(source_code='DOGC',external_id=record['document_id']+':asset:'+identity,
            publication_date=record['publication_date'], title=record['source_title'],url=record['source_url'],
            raw_text='\n\n'.join(p['text'] for p in pages),technology='BESS',
            power_mw=float(Decimal(group['per_plant_power_mw'])),project_name=name,promoter=None,
            expediente=refs[0],province=province,ccaa='Cataluña',event_type=kind,commercial_stage=stage,
            project_key=hashlib.sha1(('DOGC|named-asset|'+identity).encode()).hexdigest()[:20])
        flags=[{'code':f,'severity':'WARN' if f=='SOURCE_CAPACITY_CONFLICT' else 'INFO'} for f in record['flags']]
        flags.extend([{'code':'SHARED_ACT_REFERENCE_NOT_UNIQUE_PLANT_REFERENCE','severity':'INFO'},
                      {'code':'GROUP_PROMOTERS_NOT_ALLOCATED_TO_INDIVIDUAL_PLANTS','severity':'INFO'}])
        evidence={'source_document_id':record['document_id'],
            'extraction':{'semantic_record':record,'geography':geography,'current_references':refs,
                'identity_rule':'shared exact administrative reference + explicit full plant name',
                'named_asset':plant,'named_asset_count':group['plant_count'],
                'capacity_selection':{'status':'EXPLICIT_EACH_PLANT_CORROBORATED',
                    'basis':'PER_PLANT_INSTALLED_POWER','power_mw':event.power_mw,
                    'storage_energy_mwh':group['per_plant_energy_mwh'],
                    'evidence':group['quantity_evidence'],'group_total_not_repeated':True}},
            'quality_flags':flags,'legal_documents':[{'url':record['source_url'],'pdf_url':record['source_pdf_url'],
                'sha256':record['pdf_sha256'],'format':'PDF','page_count':record['page_count'],
                'retrieved_at':record['source_retrieved_at']}]}
        out.append((event,evidence))
    return out
