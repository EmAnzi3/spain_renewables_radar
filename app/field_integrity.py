"""Evidence-only repairs for project fields, never original legal events.

A project can appear in many notices. This module does not infer developer,
contractor, MW or municipalities from an unrelated company, line or component.
Unknown/conflicting values stay unresolved and are reported.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata

LEGAL = r'(?:S\s*\.?\s*L\s*\.?\s*U\.?|S\s*\.?\s*L\.?|S\s*\.?\s*A\s*\.?\s*U\.?|S\s*\.?\s*A\.?)'
COMPANY = rf'(?P<company>[A-ZÁÉÍÓÚÜÑÀÈÒÇ][\wÀ-ÿ&\x27’\- ]{{1,105}}?,?\s+{LEGAL})'
PREFIXES = (
    (r'\b(?:(?:se\s+)?otorg[aoó]|otorgar)\s+a\s+(?:(?:la|el)\s+)?(?:(?:sociedad|mercantil|entidad)\s+)?', 'GRANTEE'),
    (r'\b(?:peticionari[ao]|solicitante|promotor[ao]|titular)\s*:\s*(?:(?:la|el)\s+)?', 'EXPLICIT_ROLE'),
    (r'\b(?:cuya|cuyo)\s+promotor[ao]\s+es\s+(?:(?:la|el)\s+)?(?:(?:sociedad|mercantil)\s+)?', 'EXPLICIT_ROLE'),
    (r'\b(?:promovid[ao]|formulad[ao]|solicitad[ao])\s+por\s+(?:(?:la|el)\s+)?(?:(?:sociedad|mercantil|entidad)\s+)?[«“\x22]?', 'APPLICANT'),
    (r'\bempresa\s+beneficiaria\s*:\s*', 'BENEFICIARY'),
)
PATTERNS = [(re.compile(p + COMPANY + r'(?=$|[^\w])', re.I), role) for p, role in PREFIXES]
NOISE = re.compile(r'\b(?:expediente|resoluci[oó]n|dispone\s+de|capacidad\s+legal|informe|tramitaci[oó]n)\b', re.I)
RECTIFICATION = re.compile(
    r'potencia\s+instalada[^.;\n]{0,200}?\bes\s+de\s*([\d.,]+)\s*MW\s*,?\s*debiendo\s+ser\s+de\s*([\d.,]+)\s*MW\b', re.I)

def norm(value):
    value = unicodedata.normalize('NFKD', value or '')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c)).casefold())).strip()

def company_key(value):
    return norm(value).replace(' s l u', ' slu').replace(' s l', ' sl').replace(' s a u', ' sau').replace(' s a', ' sa')

def clean_company(value):
    value = re.sub(r'\s+', ' ', value or '').strip(' \t\n.,;:\"«»“”')
    if not 5 <= len(value) <= 122 or NOISE.search(value):
        return None
    if re.match(r'(?i)^(?:empresa|sociedad|entidad|la\s+empresa)\s+', value):
        return None
    if not re.search(r'\b(?:s\s*\.?\s*l\s*\.?\s*u\.?|s\s*\.?\s*l\.?|s\s*\.?\s*a\s*\.?\s*u\.?|s\s*\.?\s*a\.?)$', value, re.I):
        return None
    return value if len(norm(value).split()) <= 16 else None

def promoter_status(value):
    if not value:
        return 'MISSING'
    return 'LEGAL_NAME_FORMAT' if clean_company(value) else 'REVIEW_REQUIRED'

@dataclass(frozen=True)
class Evidence:
    source_code: str
    external_id: str
    publication_date: str
    url: str
    raw_sha256: str
    start: int
    end: int
    original: str
    value: str
    role: str

def company_mentions(text, project_name=None, **source):
    if not text:
        return []
    project = norm(project_name)
    sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    found = []
    for pattern, role in PATTERNS:
        for m in pattern.finditer(text):
            value = clean_company(m.group('company'))
            if not value:
                continue
            linked = bool(project and project in norm(text[m.end():m.end()+260]))
            found.append(Evidence(source.get('source_code') or '', source.get('external_id') or '',
                source.get('publication_date') or '', source.get('url') or '', sha,
                m.start('company'), m.end('company'), m.group('company'), value,
                role + ('_PROJECT_LINKED' if linked else '')))
    return found

def parse_mw(raw):
    if not re.fullmatch(r'\d{1,5}(?:[.,]\d{1,6})?', raw):
        return None
    if re.fullmatch(r'\d+[.]\d{3}', raw) and not raw.startswith('0.'):
        return None  # decimal point vs thousands separator is ambiguous
    try:
        value = Decimal(raw.replace(',', '.'))
        return float(value) if Decimal('0') < value <= Decimal('5000') else None
    except InvalidOperation:
        return None

def explicit_capacity_corrections(text, **source):
    sha = hashlib.sha256((text or '').encode('utf-8')).hexdigest()
    found = []
    for m in RECTIFICATION.finditer(text or ''):
        old, new = parse_mw(m.group(1)), parse_mw(m.group(2))
        if old is None or new is None or old == new:
            continue
        found.append((old, Evidence(source.get('source_code') or '', source.get('external_id') or '',
            source.get('publication_date') or '', source.get('url') or '', sha,
            m.start(2), m.end(2), m.group(2), str(new), 'EXPLICIT_INSTALLED_MW_RECTIFICATION')))
    return found

def audit_project(project, events):
    candidates, corrections = [], []
    for event in events:
        fields = {k: event.get(k) or '' for k in ('source_code','external_id','publication_date','url')}
        raw = event.get('raw_text') or ''
        candidates += company_mentions(raw, project_name=project.get('project_name'), **fields)
        heading = norm(event.get('title') or '')
        if any(marker in heading for marker in ('corrig', 'rectific', 'correc')):
            corrections += explicit_capacity_corrections(raw, **fields)
    groups = defaultdict(list)
    for e in candidates:
        groups[company_key(e.value)].append(e)
    linked = {k:group for k,group in groups.items() if any(x.role.endswith('_PROJECT_LINKED') for x in group)}
    eligible = linked or groups
    selected = next(iter(eligible.values())) if len(eligible) == 1 and project.get('project_name') else []
    company = max(selected, key=lambda e:(len(e.value), e.publication_date)).value if selected else None
    fixed_values = {e.value for _,e in corrections}
    fixed = float(next(iter(fixed_values))) if len(fixed_values) == 1 else None
    return dict(project_key=project['project_key'], promoter_status=promoter_status(project.get('promoter')),
        company_proposal=company, company_evidence=[asdict(x) for x in selected],
        company_candidates=sorted({x.value for x in candidates}), company_conflict=len(eligible)>1,
        installed_power_proposal=fixed, power_corrections=[{'prior_mw':old, **asdict(e)} for old,e in corrections],
        power_conflict=len(fixed_values)>1)

def review_database(conn):
    result=[]
    for row in conn.execute('SELECT * FROM projects ORDER BY project_key').fetchall():
        p=dict(row)
        events=[dict(e) for e in conn.execute('SELECT * FROM events WHERE project_key=? ORDER BY publication_date,id',(p['project_key'],))]
        result.append(audit_project(p,events))
    return result

def safe_proposals(project, events, review):
    result=[]
    name=project.get('project_name')
    company=review['company_proposal']
    if company and not review['company_conflict'] and name:
        evidence=review['company_evidence']
        linked=[e for e in evidence if e['role'].endswith('_PROJECT_LINKED')]
        original=project.get('promoter')
        if ((not original and (linked or len(review['company_candidates'])==1)) or
            (original and promoter_status(original)=='REVIEW_REQUIRED' and
             (norm(original).startswith(norm(company)) or linked))):
            best=max(linked or evidence,key=lambda e:(len(e['value']),e['publication_date']))
            result.append(('promoter',original,company,best))
    fixed=review['installed_power_proposal']
    if (fixed is not None and project.get('power_mw') is not None
        and abs(float(project['power_mw'])-fixed)>1e-8 and not review['power_conflict']
        and name and len({e['external_id'] for e in review['power_corrections']})==1):
        e=review['power_corrections'][0]
        original=next((x for x in events if x['source_code']==e['source_code']
                       and x['external_id']==e['external_id']),None)
        if original and norm(name) in norm(original.get('raw_text') or '') and abs(float(project['power_mw'])-e['prior_mw'])<1e-8:
            result.append(('power_mw',project['power_mw'],fixed,e))
    return result

def apply_verified_field_repairs(conn, dry_run=False):
    """Project projection only. Do not rewrite source events, IDs, dates or stages."""
    changes=[]
    for row in conn.execute('SELECT * FROM projects ORDER BY project_key'):
        p=dict(row)
        events=[dict(e) for e in conn.execute('SELECT * FROM events WHERE project_key=? ORDER BY publication_date,id',(p['project_key'],))]
        review=audit_project(p,events)
        for field,old,new,evidence in safe_proposals(p,events,review):
            changes.append(dict(project_key=p['project_key'],field_name=field,
                old_value=old,new_value=new,evidence=evidence))
    if changes and not dry_run:
        conn.execute('SAVEPOINT field_evidence_repair')
        try:
            conn.execute('''CREATE TABLE IF NOT EXISTS project_field_repair_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_key TEXT NOT NULL,
                field_name TEXT NOT NULL, previous_value_json TEXT, new_value_json TEXT NOT NULL,
                source_code TEXT NOT NULL, external_id TEXT NOT NULL, source_url TEXT NOT NULL,
                original_raw_sha256 TEXT NOT NULL, original_span_start INTEGER NOT NULL,
                original_span_end INTEGER NOT NULL, role TEXT NOT NULL, applied_at TEXT NOT NULL)''')
            for item in changes:
                field=item['field_name']
                if field not in ('promoter','power_mw'):
                    raise ValueError('Unexpected field to update')
                present=conn.execute('SELECT '+field+' FROM projects WHERE project_key=?',
                                     (item['project_key'],)).fetchone()
                if present is None or present[0]!=item['old_value']:
                    raise ValueError('Concurrent projection change')
                ev=item['evidence']
                source=conn.execute('SELECT raw_text FROM events WHERE project_key=? AND source_code=? AND external_id=?',
                                    (item['project_key'],ev['source_code'],ev['external_id'])).fetchone()
                if (not source or hashlib.sha256((source[0] or '').encode()).hexdigest()!=ev['raw_sha256']
                    or source[0][ev['start']:ev['end']]!=ev['original']):
                    raise ValueError('Original evidence fingerprint/span mismatch')
                conn.execute('UPDATE projects SET '+field+'=? WHERE project_key=?',(item['new_value'],item['project_key']))
                conn.execute('''INSERT INTO project_field_repair_audit
                    (project_key,field_name,previous_value_json,new_value_json,source_code,external_id,
                     source_url,original_raw_sha256,original_span_start,original_span_end,role,applied_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (item['project_key'],field,json.dumps(item['old_value']),json.dumps(item['new_value']),
                     ev['source_code'],ev['external_id'],ev['url'],ev['raw_sha256'],ev['start'],ev['end'],
                     ev['role'],datetime.now(timezone.utc).isoformat()))
            conn.execute('RELEASE SAVEPOINT field_evidence_repair')
            conn.commit()
        except Exception:
            conn.execute('ROLLBACK TO SAVEPOINT field_evidence_repair')
            conn.execute('RELEASE SAVEPOINT field_evidence_repair')
            raise
    return {'status':'DRY_RUN' if dry_run else 'APPLIED', 'changed_fields':len(changes),
        'promoters':sum(x['field_name']=='promoter' for x in changes),
        'power_mw':sum(x['field_name']=='power_mw' for x in changes),
        'changes':changes}
