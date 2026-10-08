"""Rebuild a reviewable portal from the exact prior operational SQLite evidence.

The prior operational acquisition, partial source coverage, timestamps and
event identities remain unchanged. This is NOT a fresh source scan/certification.
A single official INE municipality catalog is fetched separately and retained
as geographical reference evidence for this review.
"""
from __future__ import annotations
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import requests

from app.field_integrity import apply_verified_field_repairs,review_database
from app.field_geography import enrich_municipal_context
from app.enrichment.ine_municipalities import (
    INE_MUNICIPALITIES_URL,parse_ine_municipalities)
from app.reporting import write_quality_issues
from app.web_portal import payload
from app.operational import event_fingerprints

EXPECTED_RUN = '37441856639'
EXPECTED_HEAD = 'f7b68784789e3f87ce525e7efae5c6ef3c311285'

def digest(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def validate_snapshot(state:Path,original:Path):
    metadata=load(state/'state_receipt.json')
    if metadata.get('run_id')!=EXPECTED_RUN or metadata.get('head_sha')!=EXPECTED_HEAD:
        raise ValueError('Wrong acquisition run or original code identity')
    db=state/'spain_renewables.sqlite'
    if digest(db.read_bytes())!=metadata['database_sha256']:
        raise ValueError('Original SQLite digest differs from its frozen receipt')
    old=load(original/'site/data.json')
    browser=load(original/'site/browser_receipt.json')
    receipt=load(original/'site/build_receipt.json')
    if digest((original/'site/index.html').read_bytes())!=receipt['index_sha256']:
        raise ValueError('Original browser HTML differs from receipt')
    if (old['status']['run_id']!=EXPECTED_RUN or old['status']['head_sha']!=EXPECTED_HEAD
        or old['status']['database_promoted'] is not True
        or old['status']['state']!='PARTIAL' or old['status']['full_certification'] is not False
        or browser['real_data_projects']!=len(old['records']) or browser['javascript_errors']
        or browser['mobile_horizontal_overflow'] is not False):
        raise ValueError('Original partial portal provenance or browser checks disagree')
    with closing(sqlite3.connect(f'file:{db.resolve()}?mode=ro',uri=True)) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        if conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]!=len(old['records']):
            raise ValueError('Original portal does not match the saved database count')
        if conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]!=receipt['events']:
            raise ValueError('Original event total mismatch')
    return old,metadata

def acquire_ine(root:Path):
    """Official reference acquired live exactly once; failure leaves fields unresolved."""
    with requests.Session() as session:
        session.headers['User-Agent']='SpainRenewablesRadar/0.7 (evidence-only INE municipality review)'
        response=session.get(INE_MUNICIPALITIES_URL,timeout=(15,55),
                             allow_redirects=False)
        if response.status_code!=200:
            raise ValueError('INE reference did not return HTTP 200: '+str(response.status_code))
        raw=response.content
        rows=parse_ine_municipalities(response.json())
        if len(rows)<7000 or len(raw)>10_000_000:
            raise ValueError('INE municipality catalog incomplete/invalid')
        root.mkdir(parents=True,exist_ok=True)
        (root/'ine_original.json').write_bytes(raw)
        return rows,dict(url=INE_MUNICIPALITIES_URL,received_at=datetime.now(timezone.utc).isoformat(),
            sha256=digest(raw),original_bytes=len(raw),official_municipalities=len(rows),
            purpose='REFERENCE_GEOGRAPHY_ONLY_NOT_PROJECT_PUBLICATION')

def build(operational_root:Path,portal_root:Path,output:Path):
    old,metadata=validate_snapshot(operational_root,portal_root)
    output.mkdir(parents=True,exist_ok=True)
    checked=output/'checked';checked.mkdir(exist_ok=True)
    db=checked/'spain_renewables.sqlite'
    shutil.copyfile(operational_root/'spain_renewables.sqlite',db)
    before=digest(db.read_bytes())
    with closing(sqlite3.connect(db)) as conn:
        conn.row_factory=sqlite3.Row
        original_events=event_fingerprints(conn)
        keys={x[0] for x in conn.execute('SELECT project_key FROM projects')}
        all_original_rows={(r['project_key'],r['commercial_stage'],r['latest_event_type'])
                            for r in conn.execute('SELECT * FROM projects')}
        preview=apply_verified_field_repairs(conn,dry_run=True)
        repair=apply_verified_field_repairs(conn)
        if repair['changed_fields']!=preview['changed_fields']:
            raise ValueError('Field repair dry-run disagrees with applied results')
        if apply_verified_field_repairs(conn)['changed_fields']!=0:
            raise ValueError('Field repair is not idempotent')
        town_catalog,ine_receipt=acquire_ine(checked)
        site= enrich_municipal_context(conn,town_catalog)
        if enrich_municipal_context(conn,town_catalog)['documented']!=0:
            raise ValueError('Municipal context is not idempotent')
        if keys!={x[0] for x in conn.execute('SELECT project_key FROM projects')}:
            raise ValueError('Source project identities changed')
        if all_original_rows!={(r['project_key'],r['commercial_stage'],r['latest_event_type'])
                            for r in conn.execute('SELECT * FROM projects')}:
            raise ValueError('Administrative lifecycle or latest event changed')
        if original_events!=event_fingerprints(conn):
            raise ValueError('Immutable source event contents were modified')
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Repaired database integrity failed')
        for name in ('Elawan Olmedo I','Collarada Solar'):
            row=conn.execute('SELECT project_name,power_mw,promoter FROM projects WHERE project_name=?',(name,)).fetchone()
            if row is None or not row['promoter']:
                raise ValueError('Documented project company still missing: '+name)
            if name=='Elawan Olmedo I' and abs(row['power_mw']-49.61)>0.00001:
                raise ValueError('Elawan legal MW rectification not applied')
        reviews=review_database(conn)
        issues,_,_=write_quality_issues(conn,checked/'quality')
        review_quality=dict(Counter(x['severity'] for x in issues))
        revision=payload(db,old['status'])
    indexed={x['project_key']:x for x in revision['records']}
    previous={x['project_key']:x for x in old['records']}
    if set(indexed)!=set(previous):
        raise ValueError('Project missing or fabricated')
    for key,row in indexed.items():
        oldrow=previous[key]
        if row['events']!=oldrow['events'] or row['commercial_stage']!=oldrow['commercial_stage']:
            raise ValueError('Source event history or lifecycle changed for '+key)
    # These sections have independently reviewed original evidence. They do not
    # represent any newly ingested BOPV or alternative-source project events.
    revision['bopv']=old['bopv']
    revision['alternatives']=old['alternatives']
    revision['review_quality']=review_quality
    revision['review_provenance']={'mode':'FIELD_PROJECTION_REPLAY_PLUS_OFFICIAL_INE_REFERENCE',
        'source_run_id':EXPECTED_RUN, 'original_operational_status':'PARTIAL',
        'new_project_event_downloads':0,'source_dates_preserved':True,
        'ine_reference':ine_receipt,'reclassified_as_complete':False}
    serial=json.dumps(revision,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    safe=(serial.replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e')
          .replace('\u2028','\\u2028').replace('\u2029','\\u2029'))
    template=Path('web/portal.html').read_text(encoding='utf-8')
    if template.count('__RADAR_PAYLOAD__')!=1:
        raise ValueError('Invalid self-contained browser template')
    website=output/'site';website.mkdir(exist_ok=True)
    html=template.replace('__RADAR_PAYLOAD__',safe)
    (website/'index.html').write_text(html,encoding='utf-8')
    (website/'data.json').write_text(serial,encoding='utf-8')
    (website/'.nojekyll').write_text('',encoding='utf-8')
    count_events=sum(len(r['events']) for r in revision['records'])
    build_receipt={'projects':len(indexed),'events':count_events,
        'state':'PARTIAL','source_run_id':EXPECTED_RUN,'full_certification':False,
        'original_source_state_digest':before,'generated_at':revision['generated_at'],
        'index_sha256':digest(html.encode('utf-8')),'review_purpose':'FIELD_PROJECTION_ONLY'}
    (website/'build_receipt.json').write_text(json.dumps(build_receipt,indent=2))
    summary={'project_count':len(indexed),'event_count':count_events,
        'source_run_id':EXPECTED_RUN,'original_head_sha':EXPECTED_HEAD,
        'original_sqlite_sha256':before,'reviewed_sqlite_sha256':digest(db.read_bytes()),
        'changes':repair,'geography':site,'ine_reference':ine_receipt,'quality':review_quality,
        'original_quality':old['status'].get('quality'),'original_source_coverage':old['status']['state'],
        'original_source_dates_unchanged':True,'event_fingerprints_unchanged':True,
        'no_new_project_event_downloads':True,'not_a_fresh_full_certification':True}
    (checked/'field_review.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print('FIELD_REVIEW_VERIFIED',json.dumps({k:v for k,v in summary.items() if k!='changes'},ensure_ascii=False),flush=True)
    return summary

def main():
    build(Path('replay-input/state'),Path('replay-input/portal'),Path('field-reviewed'))

if __name__=='__main__': main()
