"""Conservative DOGC document classification with exact page-span evidence.

This module is pure: no network, database, lifecycle or publication writes.
It classifies the current operative act, not permits quoted in its history.
Unknown wording is retained as REVIEW_REQUIRED. Quantities are observations,
never an invitation to sum PV, storage, grid access or earlier plant capacities.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any

VERSION = 'dogc-semantic-v1'
TRANSLATE = str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'})
RENEWABLE = re.compile(r'fotovolta|panells solars|parc eòlic|bateries stand-alone|BESS|planta d.emmagatzematge', re.I)
NUMBER = r'(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)'
QUANTITY = re.compile(r'(?<![\w.,])(?P<number>' + NUMBER + r')\s*(?P<unit>(?:MW|kW)(?:h|p|n)?)(?![\w])')
REFERENCE = re.compile(r'FUE-\s*\d{4}-\s*\d{5,12}|OTA[A-Z]{3}\d{8}|\b\d{4}/\d{6}/[A-Z]\b')


def normalized(text: str) -> str:
    return re.sub(r'\s+', ' ', text.translate(TRANSLATE)).strip()


def decimal_number(value: str) -> Decimal:
    """Catalan/Spanish separators; a non-grouping dot remains decimal.

    The original number and unit remain in each observation. No magnitude-based
    unit correction is permitted, including apparent kW/MW source typos.
    """
    if not re.fullmatch(NUMBER, value):
        raise ValueError('Unsupported source number: ' + value)
    if ',' in value:
        value = value.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+', value):
        value = value.replace('.', '')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid source number') from exc
    if not number.is_finite() or number < 0:
        raise ValueError('Non-finite/negative source quantity')
    return number


@dataclass
class Page:
    number: int
    raw: str
    text: str
    positions: list[int]
    start: int


class Document:
    """Whitespace/quote comparison view mapped back to immutable page text."""
    def __init__(self, pages: list[dict]):
        if not pages or len(pages) > 150:
            raise ValueError('Missing or unbounded pages')
        self.pages: list[Page] = []
        chunks: list[str] = []
        position = 0
        for number, item in enumerate(pages, 1):
            if item.get('page') != number or not isinstance(item.get('text'), str):
                raise ValueError('Invalid or reordered page identity')
            raw = item['text']
            if len(raw) > 1_000_000:
                raise ValueError('Unbounded page text')
            chars: list[str] = []
            offsets: list[int] = []
            for offset, char in enumerate(raw):
                replacement = char.translate(TRANSLATE)
                if char.isspace():
                    if chars and chars[-1] != ' ':
                        chars.append(' '); offsets.append(offset)
                else:
                    chars.append(replacement); offsets.append(offset)
            if chars and chars[-1] == ' ':
                chars.pop(); offsets.pop()
            text = ''.join(chars)
            self.pages.append(Page(number, raw, text, offsets, position))
            chunks.append(text); position += len(text) + 1
        self.text = ' '.join(chunks)

    def find(self, pattern: str, after: int = 0, before: int | None = None,
             flags: int = re.I) -> re.Match | None:
        return re.compile(pattern, flags).search(self.text, after, len(self.text) if before is None else before)

    def evidence(self, start: int, end: int) -> list[dict]:
        if not 0 <= start < end <= len(self.text):
            raise ValueError('Evidence outside document')
        spans = []
        for page in self.pages:
            a, b = max(start, page.start), min(end, page.start + len(page.text))
            if a >= b:
                continue
            lo = page.positions[a - page.start]
            hi = page.positions[b - page.start - 1] + 1
            quote = page.raw[lo:hi]
            spans.append({'page': page.number, 'start': lo, 'end': hi, 'quote': quote,
                          'page_text_sha256': hashlib.sha256(page.raw.encode()).hexdigest()})
        if not spans:
            raise ValueError('Empty evidence span')
        return spans

    def value(self, value: Any, match: re.Match, group: int | str = 0) -> dict:
        return {'value': value, 'evidence': self.evidence(*match.span(group))}


def verify_evidence(record: dict, pages: list[dict]) -> int:
    """Rebuild every emitted quote from its source page, including its digest."""
    count = 0
    def walk(value):
        nonlocal count
        if isinstance(value, dict):
            if {'page', 'start', 'end', 'quote', 'page_text_sha256'} <= value.keys():
                number = value['page']
                if type(number) is not int or not 1 <= number <= len(pages):
                    raise ValueError('Evidence references an unknown page')
                text = pages[number - 1]['text']
                a, b = value['start'], value['end']
                if (type(a) is not int or type(b) is not int or not 0 <= a < b <= len(text)
                        or text[a:b] != value['quote']
                        or hashlib.sha256(text.encode()).hexdigest() != value['page_text_sha256']):
                    raise ValueError('Evidence does not match original page text')
                count += 1
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(record)
    return count


def event_classification(doc: Document, title: str) -> tuple[str, str, dict | None, list[str], dict | None]:
    """Return category, current event, operative evidence, flags and correction."""
    title = normalized(title)
    flags: list[str] = []
    correction = None
    exclusions = [
        (r'emmagatzematge de metalls', 'MATERIAL_STORAGE_NOT_ENERGY_STORAGE'),
        (r'emmagatzematge, processament i distribució de dades', 'DATA_CENTRE_NOT_RENEWABLE_PLANT'),
        (r'bases reguladores.*mobilitat elèctrica', 'MOBILITY_INCENTIVE_RULES_NOT_PLANT'),
    ]
    for pattern, reason in exclusions:
        if re.search(pattern, title, re.I):
            proof = doc.find(pattern)
            if proof:
                return 'OUT_OF_SCOPE', reason, doc.value(reason, proof), flags, None
    if not RENEWABLE.search(title):
        return 'REVIEW_REQUIRED', 'UNRECOGNIZED_SUBJECT', None, ['SUBJECT_NOT_CLASSIFIED'], None
    if title.startswith("Correcció d'errades"):
        old = doc.find(r'on diu:\s*(.*?)\s*ha de dir:', flags=re.I)
        new = doc.find(r'ha de dir:\s*(.*?)(?= Barcelona,| Girona,| Lleida,| Tortosa,|$)')
        if old and new:
            text = new[1]
            decision = ('ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA'
                        if re.search(r'no debe someterse a una evaluación de impacto ambiental ordinaria', text, re.I)
                        else 'CORRECTED_WORDING_REQUIRES_REVIEW')
            correction = {'previous_wording': doc.value(old[1], old, 1),
                          'replacement_wording': doc.value(text, new, 1),
                          'corrected_interpretation': decision,
                          'applies_to_source_title': title,
                          'automatic_project_merge': False, 'automatic_lifecycle_change': False}
            return 'CORRECTION', 'CORRECTION', doc.value('CORRECTION', new), ['CORRECTION_NOT_NEW_PLANT_OR_PERMIT'], correction
        return 'REVIEW_REQUIRED', 'UNPARSED_CORRECTION', None, ['CORRECTION_TEXT_MISSING'], None
    if "d'informe d'impacte ambiental" in title or "de declaració d'impacte ambiental" in title:
        # Start only at the operative body; historical consultations cannot pass.
        marker = doc.find(r"(?:Ponència d'Energies Renovables acorda:?|s'acorda:)\s*Primer")
        if marker:
            end = min(len(doc.text), marker.end() + 1800)
            decision = doc.find(r"(?:no s'ha de sotmetre|no cal sotmetre).{0,180}?avaluació d'impacte ambiental ordinària", marker.end(), end)
            if decision:
                proof = doc.evidence(marker.start(), decision.end())
                return 'ENERGY_PROJECT', 'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA', {'value': 'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA', 'evidence': proof}, ['ENVIRONMENTAL_ACT_IS_NOT_CONSTRUCTION_AUTH'], None
            decision = doc.find(r'ambientalment compatible', marker.end(), end)
            if decision and "declaració d'impacte ambiental" in title:
                return 'ENERGY_PROJECT', 'ENVIRONMENTAL_DIA_COMPATIBLE', {'value': 'ENVIRONMENTAL_DIA_COMPATIBLE', 'evidence': doc.evidence(marker.start(), decision.end())}, ['ENVIRONMENTAL_ACT_IS_NOT_CONSTRUCTION_AUTH'], None
            decision = doc.find(r"(?:s'ha de sotmetre|cal sotmetre).{0,180}?avaluació d'impacte ambiental ordinària", marker.end(), end)
            if decision:
                return 'ENERGY_PROJECT', 'ORDINARY_EIA_REQUIRED', {'value':'ORDINARY_EIA_REQUIRED','evidence':doc.evidence(marker.start(),decision.end())}, ['ORDINARY_EIA_REQUIRED_IS_NOT_PERMIT_DENIAL'], None
        return 'REVIEW_REQUIRED', 'ENVIRONMENTAL_DECISION_UNRESOLVED', None, ['OPERATIVE_ENVIRONMENTAL_DECISION_NOT_FOUND'], None
    if re.search(r"s'atorg(?:a|uen).*autorització administrativa.*construcció", title, re.I):
        match = doc.find(r"Resolc:\s*(?:[—–-]\s*)?(?:\d+[.)]?\s*)?Atorgar.{0,600}?autorització administrativa de construcció.{0,700}?(?=Descripció|Les característiques|Aquesta Resolució|DL B|$)")
        if match:
            return 'ENERGY_PROJECT', 'PRIOR_AND_CONSTRUCTION_AUTH', doc.value('PRIOR_AND_CONSTRUCTION_AUTH', match), ['AUTHORIZATION_IS_NOT_WORK_STARTED'], None
        return 'REVIEW_REQUIRED', 'GRANT_NOT_CONFIRMED_IN_OPERATIVE_BODY', None, ['GRANT_EVIDENCE_MISSING'], None
    if re.search(r"s'atorga.*declaració d'utilitat pública", title, re.I):
        match = doc.find(r"Resolc:\s*(?:[—–-]?\s*\d+[.)]?\s*)?(?:Declarar|Atorgar).{0,700}?utilitat pública.{0,450}?(?=Aquesta|Contra|\s[—–-]?\s*2[.)]|$)")
        if match:
            return 'ENERGY_PROJECT', 'PUBLIC_UTILITY_GRANTED', doc.value('PUBLIC_UTILITY_GRANTED', match), ['PUBLIC_UTILITY_IS_NOT_WORK_STARTED'], None
        return 'REVIEW_REQUIRED', 'UTILITY_GRANT_UNRESOLVED', None, ['GRANT_EVIDENCE_MISSING'], None
    if re.search(r'^Anunci.*informació pública', title, re.I):
        # The issuer's present-tense announcement is a solicitation, not a grant.
        marker = doc.find(r"(?:se sotmet|exposa el projecte esmentat) a informació pública")
        if marker:
            event = ('PUBLIC_INFO_LAND_USE' if "Projecte d'actuació específica de bateries" in title
                     else 'PUBLIC_INFO_PUBLIC_UTILITY' if "la sol·licitud de declaració d'utilitat pública" in title
                     else 'PUBLIC_INFO_AUTHORIZATION_REQUEST')
            flags.append('REQUEST_IS_NOT_AUTHORIZATION')
            if "ampliació per hibridació" in title:
                flags.append('EXISTING_PV_AUTHORIZATION_DOES_NOT_AUTHORIZE_NEW_STORAGE')
            return 'ENERGY_PROJECT', event, doc.value(event, marker), flags, None
    if ('ADMINISTRACIÓ LOCAL' in doc.pages[0].text
            and re.search(r'aprovació (?:inicial|definitiva)', title, re.I)):
        final = bool(re.search(r'aprovació definitiva', title, re.I))
        event = 'MUNICIPAL_FINAL_PROJECT_APPROVAL' if final else 'MUNICIPAL_INITIAL_PROJECT_APPROVAL'
        # Local public-works project approvals are not electricity construction permits.
        body_pattern = (r"(?:aprovar|aprovat|aprovà) definitivament|va adoptar l'acord d'aprovació definitiva|s'ha publicat l'anunci d'aprovació definitiva"
                        if final else r"(?:aprovar|aprovat|aprovà) inicialment")
        match = doc.find(body_pattern)
        if match:
            return 'MUNICIPAL_PROJECT', event, doc.value(event, match), ['MUNICIPAL_PROJECT_APPROVAL_NOT_ENERGY_AUTHORIZATION'], None
    return 'REVIEW_REQUIRED', 'UNRECOGNIZED_OPERATIVE_ACT', None, ['DOCUMENT_RETAINED_FOR_REVIEW'], None


def project_name(doc: Document, title: str) -> dict | None:
    # Prefer an explicit labelled name, never an applicant or an inferred filename.
    for page in doc.pages[:4]:
        raw = re.search(r'(?im)^\s*Nom\s+(?:de la\s+)?instal·lació\s*:\s*([^\n]+)', page.raw)
        if raw:
            value = raw[1].strip().rstrip('.')
            match = doc.find(re.escape(normalized(value)), page.start)
            if match:
                return doc.value(value, match)
    title = normalized(title)
    patterns = [
        r'instal·lació híbrida anomenada (.+?)(?=,| sobre terreny)',
        r'(?:planta solar fotovoltaica|instal·lació solar fotovoltaica|parc eòlic|planta d.emmagatzematge)(?: \(PSFV\))?(?: anomen(?:ada|at))? (?!de \d)(.+?)(?=, de | \(| i l[ae]s? (?:seva|infraestructura)|,(?!\d)| sobre terreny)',
        r'bateries stand-alone (?:BESS )?(.+?)(?=,)',
    ]
    for pattern in patterns:
        found = re.search(pattern, title, re.I)
        if found:
            value = found[1].strip().strip('"')
            if len(value) < 2 or len(value) > 150 or value.lower().startswith(('de ', 'amb ', 'en autoconsum')):
                continue
            proof = doc.find(re.escape(value))
            if proof:
                return doc.value(value, proof)
    return None


def technical_ranges(doc: Document, event: str) -> list[tuple[int,int]]:
    """Current project body only; no administrative history or landowner annex."""
    if event.startswith('ENVIRONMENTAL') or event == 'ORDINARY_EIA_REQUIRED':
        match = doc.find(r'(?:[—–-]\s*)?3[.)]?\s+Descripció (?:del Projecte|del projecte|de l.actuació)')
        if not match:
            return []
        end = doc.find(r'(?:[—–-]\s*)?4[.)]?\s+(?:Consultes|Informació pública|Consideracions|Descripció|Avaluació|Anàlisi)', match.end())
        return [(match.start(), end.start() if end else min(len(doc.text), match.start()+7500))]
    if event == 'PRIOR_AND_CONSTRUCTION_AUTH':
        match = doc.find(r'Resolc:')
        if match:
            end = doc.find(r'Aquesta Resolució es dicta|se sotmet a les condicions', match.end())
            return [(match.end(),end.start() if end else min(len(doc.text),match.end()+6500))]
    if event.startswith('PUBLIC_INFO_'):
        match = doc.find(r'Objecte de la sol·licitud\s*:|Característiques principals de')
        if match:
            end = doc.find(r'Es publica per|ANNEX\s*:|Annex\s*\d', match.end())
            return [(match.start(),end.start() if end else min(len(doc.text),match.start()+9000))]
    if event.startswith('MUNICIPAL_'):
        return [(0,len(doc.text))]
    return []


def component_for(text: str, position: int, technologies: list[str]) -> str:
    if len(technologies) == 1:
        return technologies[0]
    prefix = text[max(0, position-700):position]
    markers = list(re.finditer(r"planta solar fotovoltaica|instal·lació de generació|inversors fotovoltaics|mòduls fotovoltaics|planta d'emmagatzematge|instal·lació d'emmagatzematge|sistema d'acumulació|inversors d'emmagatzematge|energia màxima acumulable|capacitat d'emmagatzematge", prefix, re.I))
    if not markers:
        return 'UNALLOCATED'
    term = markers[-1][0].lower()
    return 'BESS' if any(x in term for x in ('emmagatzematge','acumul')) else 'PV'


def quantities(doc: Document, title: str, technologies: list[str], event: str) -> list[dict]:
    ranges = technical_ranges(doc, event)
    # Heading observations are independently copied, never treated as body truth.
    title_text = normalized(title)
    output: list[dict] = []
    seen = set()
    groups: list[tuple[str,str,int|None]] = [('INDEX_TITLE', title_text, None)]
    groups += [('CURRENT_TECHNICAL_BODY', doc.text[a:b], a) for a,b in ranges]
    for scope, text, offset in groups:
        for match in QUANTITY.finditer(text):
            number, unit = match['number'], match['unit']
            value = decimal_number(number)
            converted = value / (1000 if unit.startswith('k') else 1)
            prefix = text[max(0,match.start()-100):match.start()]
            suffix = text[match.end():match.end()+55]
            component = 'BESS' if unit.endswith('h') else component_for(text,match.start(),technologies)
            basis = ('STORAGE_ENERGY' if unit.endswith('h') else 'PEAK_DC' if unit.endswith('p')
                     else 'NOMINAL_AC' if unit.endswith('n') else 'UNSPECIFIED_POWER')
            if basis == 'UNSPECIFIED_POWER':
                labels = [(r"potència d'accés[^:]{0,25}:?\s*$",'GRID_ACCESS'),
                          (r"potència (?:total de generació|final total)[^:]{0,15}:?\s*$",'SOURCE_HYBRID_TOTAL'),
                          (r'potència instal·lada[^:]{0,8}:?\s*$','INSTALLED_POWER'),
                          (r'potència (?:total )?inversors[^:]{0,40}:?\s*$','INVERTER_POWER'),
                          (r'potència de càrrega i descàrrega\s*:\s*$','CHARGE_DISCHARGE_POWER'),
                          (r'(?:regulada a|limitada a)\s*$','REGULATED_POWER')]
                for pattern,label in labels:
                    if re.search(pattern,prefix,re.I): basis=label; break
            if basis == 'SOURCE_HYBRID_TOTAL': component='UNALLOCATED'
            if re.search(r'existent de\s*$', prefix, re.I): basis='EXISTING_CAPACITY_NOT_INCREMENT'
            annual = bool(unit.endswith('h') and (re.match(r'\s*/\s*any',suffix,re.I) or re.search(r'producció anual',prefix,re.I)))
            if annual:
                basis='ANNUAL_GENERATION';component=technologies[0] if len(technologies)==1 else 'UNALLOCATED'
            device = bool(re.search(r'cadascun|cadascuna|de potència cadascuna',suffix,re.I)
                          or re.search(r'potència unitària[^.]{0,50}$',prefix,re.I)
                          or re.search(r'cada contenidor inclou|unitats de bateries|\d+ bateries de',text[max(0,match.start()-220):match.start()],re.I))
            if device and not annual: basis='DEVICE_UNIT_ENERGY' if unit.endswith('h') else 'DEVICE_UNIT_POWER'
            if offset is None:
                proof = doc.find(re.escape(number) + r'\s*' + re.escape(unit), before=doc.pages[0].start+len(doc.pages[0].text), flags=0)
                if not proof: continue
                ev = doc.evidence(*proof.span())
            else:
                ev = doc.evidence(max(offset,offset+match.start()-min(100,match.start())), min(offset+len(text),offset+match.end()+35))
            key = (scope, component, basis, number, unit)
            if key in seen: continue
            seen.add(key)
            output.append({'source_number':number,'source_unit':unit,'value':str(value),
                           'normalized_value':str(converted),'normalized_unit':'MWh/year' if annual else 'MWh' if unit.endswith('h') else 'MW',
                           'basis':basis,'component':component,'scope':scope,'evidence':ev,
                           'aggregation_allowed':False})
    return output


def capacity_conflicts(observations: list[dict]) -> list[dict]:
    conflicts=[]
    for head in (r for r in observations if r['scope']=='INDEX_TITLE' and r['normalized_unit']=='MW'):
        for body in (r for r in observations if r['scope']=='CURRENT_TECHNICAL_BODY' and r['normalized_unit']=='MW'):
            if head['component'] != body['component'] or head['component']=='UNALLOCATED':continue
            if body['basis'] in ('GRID_ACCESS','REGULATED_POWER','DEVICE_UNIT_POWER','SOURCE_HYBRID_TOTAL'):continue
            a,b=Decimal(head['normalized_value']),Decimal(body['normalized_value'])
            same_numeric_different_unit=(head['source_unit'][1:] == body['source_unit'][1:] and head['source_unit']!=body['source_unit']
                                         and Decimal(head['value'])==Decimal(body['value']))
            magnitude=(a and b and (a/b==1000 or b/a==1000))
            storage_different=(head['component']=='BESS' and body['basis'] in ('INSTALLED_POWER','CHARGE_DISCHARGE_POWER') and a!=b)
            if same_numeric_different_unit or magnitude or storage_different:
                item={'code':'SOURCE_CAPACITY_CONFLICT','component':head['component'],
                      'headline':head,'technical_body':body,'resolution':'UNRESOLVED_NO_AUTOMATIC_CORRECTION'}
                if not any(x['component']==item['component'] for x in conflicts):conflicts.append(item)
    return conflicts


def classify_document(candidate: dict, pages: list[dict]) -> dict:
    for key in ('document_id','title','publication_date','edition','source_url','pdf_sha256'):
        if not isinstance(candidate.get(key),str) or not candidate[key]:raise ValueError('Missing original field: '+key)
    doc=Document(pages); title=normalized(candidate['title'])
    category,event,decision,flags,correction=event_classification(doc,title)
    technologies=[]
    if category not in ('OUT_OF_SCOPE','REVIEW_REQUIRED'):
        if re.search(r'fotovolta|panells solars',title,re.I):technologies.append('PV')
        if re.search(r'parc eòlic',title,re.I):technologies.append('WIND')
        if re.search(r"emmagatzematge|acumulació d'energia|bateries stand-alone|\bBESS\b",title,re.I):technologies.append('BESS')
    observations=quantities(doc,title,technologies,event) if technologies and category!='CORRECTION' else []
    conflicts=capacity_conflicts(observations)
    flags += [x['code'] for x in conflicts]
    name=project_name(doc,title) if category!='OUT_OF_SCOPE' else None
    references=[]
    # Only the current heading or the first explicit expediente label. References
    # to other plants or old decisions in subsequent pages are not primary IDs.
    for m in REFERENCE.finditer(title):
        value=re.sub(r'\s+','',m[0]);proof=doc.find(re.escape(value).replace(r'\-',r'-\s*'))
        if proof:references.append(doc.value(value,proof))
    if not references:
        ref=doc.find(r'Exp\.?\s*:\s*(\d{4}/\d{6}/[A-Z])')
        if ref:references.append(doc.value(ref[1],ref,1))
    if category=='OUT_OF_SCOPE': references=[]
    for ref in references:
        if ref['value'].startswith('FUE-') and not re.fullmatch(r'FUE-\d{4}-\d{8}',ref['value']):
            flags.append('NONCANONICAL_PRIMARY_REFERENCE_PRESERVED')
    company=doc.find(r"Persona peticionària\s*:\s*(.+?)(?=,?\s+amb |\.\s+Objecte de la sol·licitud)")
    if not company:company=doc.find(r"promogut per (?:l'empresa )?(.{2,140}?)(?=,?\s+als? termes? municipals|,?\s+i tramitat)")
    proponent=doc.value(company[1],company,1) if company and category!='OUT_OF_SCOPE' else None
    location=doc.find(r'als? termes? municipals? (?:de |del |d\')(.{2,300}?)(?=\s*\(exp\.|,?\s+a la (?:província|comarca)|,?\s+i la seva|\s*\([^)]{2,45}\))')
    location_value=doc.value(location[1].rstrip('.,'),location,1) if location and category!='OUT_OF_SCOPE' else None
    deadlines=[]
    for match in re.finditer(r'El termini per a la posada en marxa.{0,450}?(?:Diari Oficial de la Generalitat de Catalunya|notificació[^.]*\.)',doc.text,re.I):
        deadlines.append({'kind':'COMMISSIONING_DEADLINE_NOT_CONSTRUCTION_DURATION',
                          'evidence':doc.evidence(*match.span()),'start_date':None,'end_date':None})
    components=[]
    for tech in technologies:
        role='EXISTING_PV_CONTEXT' if tech=='PV' and 'ampliació per hibridació' in title else 'PROJECT_COMPONENT'
        if tech=='PV' and re.search(r"ampliació.*existent de",title,re.I):
            role='EXPANSION_WITH_EXISTING_CAPACITY_ONLY'
            flags.append('EXISTING_CAPACITY_IS_NOT_ADDED_CAPACITY')
        if len(technologies)>1 and role=='PROJECT_COMPONENT':role='HYBRID_COMPONENT'
        components.append({'technology':tech,'role':role,'capacity_mw':None,
                           'capacity_status':'CONFLICT' if any(c['component']==tech for c in conflicts) else 'TYPED_OBSERVATIONS_ONLY',
                           'capacities':[x for x in observations if x['component']==tech]})
    if len(technologies)>1:flags.append('COMPONENT_CAPACITIES_NOT_SUMMED')
    if 'infraestructures d\'evacuació dels parcs' in title:flags.append('SHARED_EVACUATION_DOES_NOT_CREATE_ADDITIONAL_PLANTS')
    result={
        'schema_version':VERSION,'document_id':candidate['document_id'],'publication_date':candidate['publication_date'],
        'edition':candidate['edition'],'source_title':candidate['title'],'source_url':candidate['source_url'],
        'source_pdf_url':candidate.get('source_pdf_url'),'source_retrieved_at':candidate.get('retrieved_at'),'pdf_sha256':candidate['pdf_sha256'],'page_count':len(pages),
        'category':category,'event':event,'decision':decision,'project_name':name,'primary_references':references,
        'proponent':proponent,'location_text':location_value,'technologies':technologies,'components':components,
        'capacity_observations':observations,'capacity_conflicts':conflicts,'correction':correction,
        'time_terms':deadlines,'construction_start_date':None,'construction_end_date':None,
        'epc':None,'bop':None,'contractor_status':'NOT_ESTABLISHED_FROM_THIS_ACT',
        'flags':sorted(set(flags)),'document_classified':category!='REVIEW_REQUIRED',
        'field_completeness_certified':False,'live_collector_validated':False,
        'database_writes':0,'production_enabled':False,'automatic_project_merge':False,
    }
    result['evidence_spans_verified']=verify_evidence(result,pages)
    if category!='REVIEW_REQUIRED' and not decision:raise ValueError('Classification lacks operative evidence')
    return result
