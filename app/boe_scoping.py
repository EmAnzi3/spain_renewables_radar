"""Conservative BOE title scope for a utility-scale renewables project radar.

A named multi-plant or unidentifiable official notice is a review lead, NEVER
one invented renewable project. Non-energy acts with incidental battery/PV
words are not project permits. Original targeted leads are kept by BOECollector.
"""
from __future__ import annotations
import re
import unicodedata

def canonical(text):
    text=unicodedata.normalize('NFKD',text or '').casefold()
    return ''.join(c for c in text if not unicodedata.combining(c))

# Rules apply to the official announcement TITLE, not to the entire document.
# Do not exclude a real wind/PV/BESS permit because its body mentions a port,
# aid program, university or electricity network.
NON_PROJECT=[
    (r'\b(?:universidad|plan de estudios)\b.*\b(?:master|grado|energias renovables)\b','EDUCATION'),
    (r'\bautoridad portuaria\b.*\b(?:muelle|concesion administrativa)\b.*\b(?:manipulacion portuaria|graneles)\b','PORT_SIDE_PV_NOT_PLANT'),
    (r'\b(?:extracto|correccion de errores del extracto)\b.*\b(?:convocatoria|ayudas|subvenciones)\b','GRANT_CALL_NOT_PLANT'),
    (r'\b(?:produccion de baterias|fabricacion de baterias)\b.*\b(?:vehiculo electrico|pilas de combustible)\b','EV_BATTERY_FACTORY'),
    (r'\b(?:comision nacional de los mercados|cnmc)\b.*\brecurso contencioso-administrativo\b.*\b(?:inversion|baterias)\b','REGULATORY_LITIGATION'),
    (r'\b(?:sentencia|tribunal supremo)\b.*\b(?:regimen|normativa)\b.*\bplantas fotovoltaicas flotantes\b','GENERAL_ENERGY_LAW'),
    (r'\b(?:secretaria de estado de medio ambiente|mancomunidad de los canales)\b.*\b(?:suministro complementario|idam de alicante|elevacion de valdelentisco)\b','AUXILIARY_WATER_PUMP_SOLAR'),
    (r'\b(?:comisaria de aguas|confederacion hidrografica)\b.*\b(?:registro de aguas|aprovechamiento de aguas subterran[eé]as)\b','WATER_WELLS_NOT_BESS'),
    (r'\bdireccion general de desarrollo rural\b.*\bproyecto de mejora de la eficiencia energetica\b','IRRIGATION_UPGRADE_NOT_PLANT'),
    (r'\b(?:instalacion|generacion) fotovoltaica\b.*\b(?:idam|desaladora|desalinizadora)\b.*\bsuministro complementario\b','AUXILIARY_WATER_SUPPLY'),
]
COMPILED_NON_PROJECT=[(re.compile(p,re.I|re.S),code) for p,code in NON_PROJECT]

# Do NOT project an evacuation group as a single power plant, and DO NOT
# propagate an identifier shared by separate individual projects.
MULTI=[
    (r'\binfraestructura(?:s)? de evacuacion conjunta de las (?:dos|tres|cuatro|cinco|varias) plantas fotovoltaicas\b','SHARED_EVACUATION'),
    (r'\b(?:instalacion|proyecto) de las plantas fotovoltaicas\s+vallejon\s+y\s+calera\b','TWO_PV_PLANTS'),
    (r'\bparques fotovoltaicos\s+magec\s+i[\-–]ii[\-–]iii[\-–]iv\b','FOUR_PV_PLANTS'),
    (r'\bparques solares fotovoltaicos\s+azor solar\b.*\bavutarda solar\b','TWO_PV_PLANTS'),
]
COMPILED_MULTI=[(re.compile(p,re.I|re.S),code) for p,code in MULTI]

# A regional water-occupancy permission can be a useful PROJECT LEAD,
# but it is not evidence of renewable-energy permit/lifecycle.
NON_ENERGY_LEADS=[
    (r'\bcomisaria de aguas\b.*\b(?:autorizacion|zona de policia)\b.*\bplanta solar fotovoltaica\b','WATER_ZONE_PROJECT_LEAD'),
]
COMPILED_LEADS=[(re.compile(p,re.I|re.S),code) for p,code in NON_ENERGY_LEADS]

def notice_scope(title):
    value=canonical(title)
    for pattern,reason in COMPILED_NON_PROJECT:
        if pattern.search(value):return 'OUT_OF_SCOPE',reason
    for pattern,reason in COMPILED_MULTI:
        if pattern.search(value):return 'REVIEW_MULTI_ASSET',reason
    for pattern,reason in COMPILED_LEADS:
        if pattern.search(value):return 'REVIEW_NON_ENERGY_PERMIT',reason
    return 'CANDIDATE',None
