"""Audit DOG source publications against the integrated project/event database."""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from datetime import date,timedelta
from pathlib import Path
from app.collectors.dog import ASSET_RE,events_from_notice,parse_notice


def validate_dog_integration(conn,coverage,root='reports/dog',expected_days=30):
    root=Path(root)
    source_days=[row for row in coverage if row['source_code']=='DOG']
    dates=[row['date'] for row in source_days]
    if len(dates)!=expected_days or len(set(dates))!=expected_days or any(row['status']!='OK' for row in source_days):
        raise ValueError('DOG source/day coverage incomplete')
    start=date.fromisoformat(min(dates))
    if set(dates)!={(start+timedelta(days=i)).isoformat() for i in range(expected_days)}:
        raise ValueError('DOG coverage has calendar gaps')
    audit=json.loads((root/'coverage.json').read_text())
    if audit.get('source_code')!='DOG' or set(audit.get('days',{}))!=set(dates):
        raise ValueError('DOG acquisition dates disagree with pipeline coverage')
    if any(row.get('status')!='OK' for row in audit['days'].values()):
        raise ValueError('DOG has failed source days')
    for acquisition in audit['acquisitions']:
        digest=acquisition.get('sha256')
        if not digest:
            if acquisition.get('complete'):raise ValueError('DOG successful response without source hash')
            continue
        raw=(root/'raw'/(digest+'.bin')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest or len(raw)!=acquisition['bytes']:
            raise ValueError('DOG original acquisition corrupted')
    unresolved=[r for r in audit['review'] if ASSET_RE.search(r['title'])]
    if unresolved:raise ValueError('DOG named projects left unresolved: '+json.dumps(unresolved,ensure_ascii=False))
    observed={row['external_id']:dict(row) for row in conn.execute("SELECT * FROM events WHERE source_code='DOG'")}
    metadata={row['external_id']:dict(row) for row in conn.execute("SELECT * FROM regional_public_metadata WHERE source_code='DOG'")}
    expected={};project_rows=[]
    for notice in audit['notices']:
        raw=(root/'raw'/(notice['original_html_sha256']+'.bin')).read_bytes()
        rebuilt=parse_notice(raw,notice)
        if rebuilt['records']!=notice['records'] or rebuilt['raw_text']!=notice['raw_text']:
            raise ValueError('DOG derived fields do not reproduce from the original legal text')
        for event,record in zip(events_from_notice(rebuilt),rebuilt['records']):
            if event.external_id in expected:raise ValueError('Repeated DOG component identity')
            expected[event.external_id]=event
            stored=observed.get(event.external_id);meta=metadata.get(event.external_id)
            if stored is None or meta is None:raise ValueError('DOG source event or provenance missing from database')
            for field in ('source_code','external_id','publication_date','title','url','raw_text','technology','power_mw','promoter','expediente','province','ccaa','event_type','commercial_stage'):
                if stored[field]!=getattr(event,field):raise ValueError('DOG event field changed without source evidence: '+field)
            if (meta['source_url']!=stored['url'] or meta['web_publication_date']!=stored['publication_date'] or meta['project_key']!=stored['project_key']):
                raise ValueError('DOG metadata assigned to a different event')
            evidence=json.loads(meta['evidence_json'])
            if evidence['extraction']!=record:raise ValueError('DOG metadata differs from scoped source extraction')
            if record['work_start'] is not None or record['work_end'] is not None:
                raise ValueError('DOG execution duration was turned into an invented work date')
            project_rows.append({**{k:record[k] for k in ('project_name','expediente','technology','power_mw','province','event_type','execution_duration_months','power_scope')},'publication_date':notice['publication_date'],'source_url':notice['url']})
    if set(observed)!=set(expected) or set(metadata)!=set(expected):
        raise ValueError('DOG database and source inventory have different event identities')
    if sum(row['events'] for row in audit['days'].values())!=len(expected):
        raise ValueError('DOG source/day event accounting mismatch')
    if sum(row['candidates'] for row in audit['days'].values())!=len(audit['notices']):
        raise ValueError('DOG candidate accounting mismatch')
    links=json.loads((root/'galicia_links.json').read_text())
    keys={row['project_key'] for row in observed.values()}
    return dict(dog_source_days=len(dates),dog_publication_editions=sum(r['editions'] for r in audit['days'].values()),
        dog_index_notices=sum(r['index_notices'] for r in audit['days'].values()),dog_source_publications=len(audit['notices']),
        dog_events=len(expected),dog_projects=len(keys),dog_by_event=dict(Counter(e.event_type for e in expected.values())),
        dog_original_provenance_verified=True,dog_source_reviews=len(audit['review']),
        dog_archive_link_status=links['status'],dog_archive_links=len(links['matches']),dog_project_details=project_rows)
