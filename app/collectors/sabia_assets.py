"""Deterministic source-title decomposition; no inferred capacity allocation.

SABIA environmental files may cover several independently named plants. Keep the
administrative file reference verbatim and use a separate component identity.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict

from app.geo import PROVINCE_TO_CCAA
from app.parser import normalize_text, extract_project_name

QUOTES = '\"«»“”‘’'
NUMBER = r'\d+(?:[.,]\d+)?'
POWER = re.compile(rf'\b(?:DE\s+)?({NUMBER})\s*(MWP|MWAC|MWN|MW)\b', re.I)
ANCHOR = re.compile(
    r'(?P<storage>M[ÓO]DULOS?|SISTEMAS?)\s+DE\s+ALMACENAMIENTO'
    r'(?:\s+DE\s+ENERG[ÍI]A)?(?:\s+POR\s+BATER[ÍI]AS)?'
    r'(?:\s+(?:DE\s+LA\s+)?INSTALACI[ÓO]N\s+H[ÍI]BRIDA)?'
    r'|(?P<wind>M[ÓO]DULO\s+DE\s+GENERACI[ÓO]N\s+E[ÓO]LICA|PARQUES?\s+E[ÓO]LICOS?)'
    r'|(?P<pv>(?:PLANTAS?|PARQUES?|PS)\s+(?:SOLARES?\s+)?FOTOVOLTAIC[AO]S?|PF)'
    r'|(?P<hybrid>H[ÍI]BRIDO)\s+(?=[«“\"])'
    r'|(?P<plants>PLANTAS)\s+(?=[«“\"]ALMACENAMIENTO)', re.I)
END = re.compile(
    r',?\s+(?:PARA\s+(?:SU|LA)\s+HIBRIDACI[ÓO]N|Y\s+(?:PARA\s+)?(?:SU|SUS|LA|LAS)\s+INFRAESTRUCTURAS?'
    r'|AS[ÍI]\s+COMO\s+SUS\s+INFRAESTRUCTURAS?|Y\s+PARA\s+UNA\s+PARTE'
    r'|(?:UBICAD[OA]|SITUAD[OA])S?\b|EN\s+(?:LA|LAS)\s+PROVINCIAS?\b)', re.I)

@dataclass(frozen=True)
class Asset:
    name: str | None
    power_mw: float | None
    unit: str | None = None
    rule: str = 'SOURCE_SINGLE'
    reason: str | None = None
    group_power_mw: float | None = None


def _clean(value: str) -> str:
    return ' '.join(value.split()).strip(' ,;.' + QUOTES)


def _number(value: str) -> float:
    return float(value.replace('.', '').replace(',', '.')) if ',' in value else float(value)


def _names(value: str) -> tuple[list[str], str]:
    """Expand only an explicit shared numeric/Roman suffix, or full names joined by Y."""
    value = _clean(value)
    enum = re.fullmatch(r'(.*?)\s+((?:\d+|[IVX]+)(?:\s*,\s*(?:\d+|[IVX]+))*\s+Y\s+(?:\d+|[IVX]+))(\s+H[ÍI]BRID[OA])?', value, re.I)
    if enum:
        numbers = re.split(r'\s*,\s*|\s+Y\s+', enum[2], flags=re.I)
        return [_clean(enum[1] + ' ' + n + (enum[3] or '')) for n in numbers], 'EXPLICIT_SHARED_SUFFIX'
    parts = [_clean(x) for x in re.split(r'\s+Y\s+', value, flags=re.I)]
    return parts, 'EXPLICIT_NAMED_LIST'


def parse_assets(title: str) -> list[Asset]:
    title = ' '.join((title or '').split())
    # The quoted name belongs to an electrolyser, not to its unnamed PV plant.
    if re.match(r'PLANTA\s+DE\s+ELECTR[ÓO]LISIS', title, re.I) and re.search(r'ALIMENTADA\s+POR\s+PLANTA\s+SOLAR\s+FOTOVOLTAICA\s+DE', title, re.I):
        pv = re.split(r'ALIMENTADA\s+POR', title, maxsplit=1, flags=re.I)[1]
        power = POWER.search(pv)
        return [Asset(None, _number(power[1]) if power else None, power[2] if power else None,
                      reason='UNNAMED_RENEWABLE_COMPONENT_OF_HYDROGEN_PROJECT')]
    match = ANCHOR.search(title)
    if not match:
        name = extract_project_name(title)
        power = POWER.search(title)
        return [Asset(name, _number(power[1]) if power else None, power[2] if power else None)]
    block = title[match.end():].strip()
    cut = END.search(block)
    if cut:
        block = block[:cut.start()]
    block = re.sub(r'^(?:DENOMINAD[OA]S?\s+)', '', block, flags=re.I)
    plural = bool(re.search(r'\b(?:MODULOS|MÓDULOS|SISTEMAS|PLANTAS|PARQUES|FOTOVOLTAICOS)\b', match[0], re.I))
    powers = list(POWER.finditer(block))
    if not plural:
        stop = powers[0].start() if powers else len(block)
        name = _clean(block[:stop])
        quoted = re.match(r'[«“\"]([^»”\"]+)[»”\"]', block)
        if quoted:
            name = _clean(quoted[1])
        if name.endswith(' DE'):
            name = _clean(name[:-3])
        if not name or re.match(r'^(?:DE\s+)?\d|DE\s+\d', name):
            name = None
        return [Asset(name, _number(powers[0][1]) if powers else None, powers[0][2] if powers else None)]
    # Separate each explicit name + power pair. Secondary MWn after / is not a new plant.
    paired = []
    cursor = 0
    for power in powers:
        prefix = block[cursor:power.start()]
        name = _clean(re.sub(r'^\s*[,;]?\s*(?:Y\s+)?', '', prefix, flags=re.I))
        if name.endswith(' DE'):
            name = _clean(name[:-3])
        if name and not re.match(r'^[/\d]', name):
            paired.append(Asset(name, _number(power[1]), power[2], 'NAME_ASSOCIATED_POWER'))
        cursor = power.end()
    if len(paired) > 1:
        return paired
    # Shared capacity is assignable to each plant ONLY when the source says each/both.
    if powers:
        name_text = _clean(block[:powers[0].start()])
        each = bool(re.search(r'\b(?:CADA\s+UNO|CADA\s+UNA|AMBOS|AMBAS)\b', block, re.I))
        name_text = _clean(re.sub(r',?\s*(?:AMBOS|AMBAS)\s*(?:DE)?\s*$', '', name_text, flags=re.I))
        if name_text.endswith(' DE'):
            name_text = _clean(name_text[:-3])
        names, rule = _names(name_text)
        if len(names) > 1:
            mw = _number(powers[0][1])
            return [Asset(n, mw if each else None, powers[0][2] if each else None,
                          'EXPLICIT_EACH_POWER' if each else rule,
                          group_power_mw=None if each else mw) for n in names]
        return [Asset(name_text or None, _number(powers[0][1]), powers[0][2])]
    names, rule = _names(block)
    return [Asset(n or None, None, rule=rule) for n in names]


PROVINCE_ALIASES = {'Araba':'Álava','Vizcaya':'Bizkaia','Guipúzcoa':'Gipuzkoa',
                    'Alicante':'Alicante/Alacant','Castelló':'Castellón',
                    'València':'Valencia','Baleares':'Illes Balears'}


def source_provinces(detail: dict) -> list[str]:
    value = detail.get('province') or ''
    explicit = re.search(r'\bPROVINCIAS\s+DE\s+([^.;]+)', detail.get('title') or '', re.I)
    if explicit:
        value += ' ' + explicit[1]
    normalized = normalize_text(value)
    found = set()
    for province in sorted(PROVINCE_TO_CCAA, key=len, reverse=True):
        key = normalize_text(province)
        if re.search(r'(?<!\w)' + re.escape(key) + r'(?!\w)', normalized):
            found.add(PROVINCE_ALIASES.get(province, province))
    return sorted(found)


def component_key(reference: str, asset: Asset) -> str:
    raw = 'sabia-component|' + normalize_text(reference) + '|' + normalize_text(asset.name or '')
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]


def write_event_metadata(conn, details, candidates, event_factory):
    conn.execute('''CREATE TABLE IF NOT EXISTS event_source_metadata (
        source_code TEXT NOT NULL, external_id TEXT NOT NULL, project_key TEXT NOT NULL,
        environmental_code TEXT, source_current_state TEXT, date_basis TEXT NOT NULL,
        web_publication_date TEXT, source_retrieved_at TEXT, evidence_json TEXT NOT NULL,
        PRIMARY KEY(source_code,external_id))''')
    for code, value in details.items():
        detail, url = value
        assets = parse_assets(detail['title'])
        provinces = source_provinces(detail)
        for event in event_factory(detail, candidates[code]['source_type'], url):
            stored = conn.execute('SELECT project_key FROM events WHERE source_code=? AND external_id=?',
                                  (event.source_code, event.external_id)).fetchone()
            if not stored:
                continue
            key = stored['project_key']
            asset = next((a for a in assets if a.name == event.project_name), assets[0])
            evidence = {'asset':asdict(asset), 'source_title':detail['title'], 'source_url':url,
                        'source_provinces':provinces, 'administrative_reference':detail.get('substantive_code'),
                        'source_group_id':code if len(assets)>1 else None}
            conn.execute('''INSERT OR REPLACE INTO event_source_metadata VALUES (?,?,?,?,?,?,?,?,?)''',
                         (event.source_code,event.external_id,key,code,detail.get('state'),
                          'ENTRY_DATE' if ':ENTRY' in event.external_id else 'CONSULTATION_START',None,
                          detail.get('retrieved_at'),json.dumps(evidence,ensure_ascii=False)))
            if len(provinces)>1:
                communities = {PROVINCE_TO_CCAA[p] for p in provinces}
                conn.execute('''INSERT INTO project_geo_enrichment
                    (project_key,municipalities_json,provinces_json,province,ccaa,status,source_code,source_url,reference_date)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_key) DO UPDATE SET
                    provinces_json=excluded.provinces_json,status=excluded.status,source_code=excluded.source_code,
                    source_url=excluded.source_url,reference_date=excluded.reference_date''',
                    (key,json.dumps([detail['municipality']] if detail.get('municipality') else [],ensure_ascii=False),
                     json.dumps(provinces,ensure_ascii=False),None,next(iter(communities)) if len(communities)==1 else None,
                     'MULTI_PROVINCE','MITECO_SABIA',url,event.publication_date))
    conn.commit()
