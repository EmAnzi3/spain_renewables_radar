"""Reconcile GVA acquisition, immutable events and visible field-quality flags."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path


def validate_gva_integration(conn,coverage,quality,root=Path('reports/gva_public')):
    root=Path(root)
    audit=json.loads((root/'coverage.json').read_text())
    records=json.loads((root/'records.json').read_text())
    inventory=json.loads((root/'inventory.json').read_text())
    if not audit.get('complete') or audit['detail_errors']:
        raise ValueError('GVA inventory/detail acquisition incomplete')
    if not len(inventory)==len({r['external_id'] for r in inventory})==audit['declared_records']==audit['archive_records']:
        raise ValueError('GVA inventory count or source identities differ')
    dates={r['date'] for r in coverage if r['source_code']=='GVA_PUBLIC'}
    if len(dates)!=30 or dates!=set(audit['processed_days']):
        raise ValueError('GVA requested day accounting incomplete')
    if any(r['status']!='OK' for r in audit['processed_days'].values()):
        raise ValueError('GVA source day contains acquisition failure')
    expected={r['external_id'] for r in inventory if r['publication_date'] in dates}
    if expected!={r['external_id'] for r in records} or len(expected)!=len(records):
        raise ValueError('Not every dated GVA source publication has an extraction outcome')
    for acquisition in audit['acquisitions']:
        path=(root/acquisition['file']).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('Invalid original source path')
        raw=path.read_bytes()
        if len(raw)!=acquisition['bytes'] or hashlib.sha256(raw).hexdigest()!=acquisition['sha256']:
            raise ValueError('GVA original source bytes changed')
    events={r['external_id']:dict(r) for r in conn.execute("SELECT * FROM events WHERE source_code='GVA_PUBLIC'")}
    targets={r['external_id']:r for r in records if r['extraction']['disposition']=='TARGET'}
    if set(events)!=set(targets):raise ValueError('GVA target publications differ from stored events')
    metadata={r['external_id']:dict(r) for r in conn.execute("SELECT * FROM regional_public_metadata WHERE source_code='GVA_PUBLIC'")}
    if set(metadata)!=set(events):raise ValueError('GVA event provenance incomplete')
    for identity,event in events.items():
        source=json.loads(event['raw_text']);record=targets[identity];meta=metadata[identity]
        for key in ('external_id','title','publication_date','url'):
            if source[key]!=record[key] or source[key]!=event[key]:
                raise ValueError('GVA original publication evidence differs from stored event')
        for key in ('technology','power_mw','province','expediente','event_type','commercial_stage'):
            if record['extraction'][key]!=event[key]:raise ValueError('GVA source field changed during storage')
        if meta['project_key']!=event['project_key'] or meta['web_publication_date']!=event['publication_date'] or meta['source_url']!=event['url']:
            raise ValueError('GVA source metadata points to another event')
    flags=Counter(f['code'] for r in targets.values() for f in r['quality_flags'])
    if flags['SOURCE_LIFECYCLE_UNMAPPED']:raise ValueError('Unmapped GVA administrative decision remains')
    for code,count in flags.items():
        visible=sum(q['source_code']=='GVA_PUBLIC' and q['code']==code for q in quality)
        if visible!=count:raise ValueError('GVA source discrepancies are missing from the common quality report')
    return {
        'gva_archive_records':len(inventory),'gva_archive_pages':audit['pages'],
        'gva_source_publications':len(records),'gva_events':len(events),
        'gva_by_event':dict(Counter(e['event_type'] for e in events.values())),
        'gva_by_stage':dict(Counter(e['commercial_stage'] for e in events.values())),
        'gva_source_quality_flags':dict(flags),
        'gva_excluded_dispositions':dict(Counter(r['extraction']['disposition'] for r in records if r['extraction']['disposition']!='TARGET')),
        'gva_original_provenance_verified':True,
        'gva_pdf_field_scope':audit['pdf_field_extraction_scope'],
    }
