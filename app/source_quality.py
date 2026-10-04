"""Read-only projection of regional source assertions into quality and dashboard.

These helpers report discrepancies. They must never rewrite project/event fields.
"""
from __future__ import annotations
import json


def regional_evidence_by_project(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='regional_public_metadata'").fetchone():
        return {}
    result={}
    rows=conn.execute('''SELECT m.*,e.publication_date AS event_date,e.url AS event_url,e.project_key AS event_project_key
        FROM regional_public_metadata m LEFT JOIN events e USING(source_code,external_id)
        ORDER BY m.web_publication_date,m.external_id''')
    for row in rows:
        if row['web_publication_date']!=row['event_date'] or row['source_url']!=row['event_url'] or row['project_key']!=row['event_project_key']:
            raise ValueError('Regional source provenance differs from its immutable event')
        evidence=json.loads(row['evidence_json'])
        if not isinstance(evidence,dict) or not isinstance(evidence.get('quality_flags'),list):
            raise ValueError('Invalid regional source evidence schema')
        result.setdefault(row['project_key'],[]).append({
            'source_code':row['source_code'],'external_id':row['external_id'],
            'publication_date':row['web_publication_date'],'source_url':row['source_url'],
            'extraction':evidence.get('extraction',{}),
            'quality_flags':evidence['quality_flags'],'legal_documents':evidence.get('legal_documents',[]),
        })
    return result


def regional_quality_issues(conn):
    projects={row['project_key']:dict(row) for row in conn.execute('SELECT * FROM projects')}
    issues=[]
    for key,records in regional_evidence_by_project(conn).items():
        project=projects[key]
        for record in records:
            for flag in record['quality_flags']:
                if flag.get('severity') not in {'ERROR','WARN','INFO'} or not flag.get('code'):
                    raise ValueError('Regional source flag has no valid severity/code')
                issue={field:project.get(field) for field in ('project_key','project_name','technology','power_mw','province','ccaa','commercial_stage')}
                issue.update(severity=flag['severity'],code=flag['code'],source_code=record['source_code'],
                             source_url=record['source_url'],detail=json.dumps({
                                 'external_id':record['external_id'],
                                 'publication_date':record['publication_date'],'source_issue':flag,
                             },ensure_ascii=False,sort_keys=True))
                issues.append(issue)
    return issues
