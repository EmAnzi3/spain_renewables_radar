"""Certify the declared SABIA extraction scope, not the entire Spanish project market."""
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path


def main():
    coverage = json.loads(Path('reports/sabia/coverage.json').read_text(encoding='utf-8'))
    con = sqlite3.connect('data/sabia_backfill.sqlite')
    con.row_factory = sqlite3.Row
    projects = con.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
    events = con.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    with open('reports/quality_issues_latest.csv', encoding='utf-8-sig') as stream:
        issues = list(csv.DictReader(stream))
    with open('reports/coverage_latest.csv', encoding='utf-8-sig') as stream:
        source_days = list(csv.DictReader(stream))
    metrics = {
        'inventory_candidates': coverage['candidates'],
        'details_ok': coverage['details_ok'],
        'detail_errors': len(coverage['detail_errors']),
        'projects': projects,
        'events': events,
        'administrative_files': con.execute("SELECT COUNT(DISTINCT environmental_code) FROM event_source_metadata").fetchone()[0],
        'multi_province_projects': con.execute("SELECT COUNT(*) FROM project_geo_enrichment WHERE status='MULTI_PROVINCE'").fetchone()[0],
        'event_metadata_rows': con.execute('SELECT COUNT(*) FROM event_source_metadata').fetchone()[0],
        'detail_cache_reused': coverage.get('detail_cache_reused',0),
        'detail_retrieval_oldest': coverage.get('detail_retrieval_oldest'),
        'detail_retrieval_newest': coverage.get('detail_retrieval_newest'),
        'by_technology': dict(con.execute('SELECT technology, COUNT(*) FROM projects GROUP BY technology').fetchall()),
        'quality': dict(Counter(i['severity'] for i in issues)),
        'source_day_errors': sum(x['status'] in ('ERROR', 'WARN') for x in source_days),
        'date_semantics': 'ENTRY_DATE and CONSULTATION_START, not web publication dates',
        'milestone_scope': 'ENTRY and CONSULT only; resolution and authorization not yet materialized',
    }
    print('SABIA_CERTIFICATION', json.dumps(metrics, ensure_ascii=False), flush=True)
    for row in con.execute('''SELECT e.publication_date,e.external_id,p.project_name,e.title,e.technology,e.power_mw,
                              e.expediente,e.province,e.ccaa,e.event_type
                              FROM events e JOIN projects p ON p.project_key=e.project_key
                              ORDER BY e.publication_date,e.external_id'''):
        print('SABIA_EVENT', json.dumps(dict(row), ensure_ascii=False), flush=True)
    for issue in issues:
        if issue['severity'] in ('ERROR','WARN'):
            print('SABIA_QUALITY', json.dumps(issue, ensure_ascii=False), flush=True)
    Path('reports/sabia/certification.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    if metrics['event_metadata_rows'] != events:
        raise SystemExit('Missing per-event source metadata')
    if con.execute('SELECT COUNT(*) FROM event_source_metadata WHERE web_publication_date IS NOT NULL').fetchone()[0]:
        raise SystemExit('SABIA web publication dates must not be invented')
    if con.execute('PRAGMA foreign_key_check').fetchall():
        raise SystemExit('Invalid project references')
    con.close()
    if not coverage['complete'] or coverage['details_ok'] != coverage['candidates'] or coverage['detail_errors']:
        raise SystemExit('Incomplete SABIA source snapshot')
    if projects == 0 or events == 0:
        raise SystemExit('Empty SABIA 30-day output is not certified')
    if metrics['source_day_errors'] or metrics['quality'].get('ERROR', 0):
        raise SystemExit('SABIA coverage or quality gate failed')

if __name__ == '__main__':
    main()
