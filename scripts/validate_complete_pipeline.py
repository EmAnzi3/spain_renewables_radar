"""Evidence-based certification of the twelve implemented source adapters."""
from __future__ import annotations
import csv,json,os,sys,hashlib
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import connect
from app.identifiers import valid_expediente
from app.parser import ParsedEvent
from app.reporting import geography_accounting,build_commercial_rows
from app.store import save_event
from scripts.gva_integration_gate import validate_gva_integration
from scripts.dog_integration_gate import validate_dog_integration

SOURCES={'BOE','BOCYL','BOA','BOJA','DOCM','DOE','BORM','BOCM','AND_PUBLIC','GVA_PUBLIC','MITECO_SABIA','DOG'}


def rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


def metrics(conn,coverage,quality,sabia,and_public,borm):
    if not borm.get("complete") or borm.get("rows",0)!=borm.get("distinct_ids"):
        raise ValueError("BORM annual index acquisition incomplete")
    raw_index=Path("reports/borm/index_raw.json").read_bytes()
    if hashlib.sha256(raw_index).hexdigest()!=borm.get("sha256"):
        raise ValueError("BORM original source hash mismatch")
    invalid=[]
    for p in conn.execute('SELECT * FROM projects WHERE expediente IS NOT NULL'):
        if valid_expediente(p['expediente']):continue
        evidence=[json.loads(r[0]) for r in conn.execute("SELECT evidence_json FROM event_source_metadata WHERE project_key=? AND source_code='MITECO_SABIA'",(p['project_key'],))]
        if not any(r.get('administrative_reference')==p['expediente'] for r in evidence):
            invalid.append({'project_key':p['project_key'],'expediente':p['expediente']})
    counts={s:sum(r['source_code']==s for r in coverage) for s in SOURCES}
    missing_days={s:n for s,n in counts.items() if n!=30}
    before_projects=conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
    before_events=conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    keys={r[0] for r in conn.execute('SELECT project_key FROM projects')}
    event_rows=conn.execute('SELECT e.*,p.project_name FROM events e JOIN projects p USING(project_key)').fetchall()
    for row in event_rows:
        event=ParsedEvent(**{key:row[key] for key in ParsedEvent.__dataclass_fields__})
        if save_event(conn,event)!=(False,False):raise ValueError('Existing source event was inserted twice')
    after_keys={r[0] for r in conn.execute('SELECT project_key FROM projects')}
    if keys!=after_keys or before_events!=conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]:
        raise ValueError('Non-idempotent replay')
    issues=Counter(r['severity'] for r in quality)
    event_meta=conn.execute('SELECT COUNT(*) FROM event_source_metadata').fetchone()[0]
    sabia_events=conn.execute("SELECT COUNT(*) FROM events WHERE source_code='MITECO_SABIA'").fetchone()[0]
    if event_meta!=sabia_events:raise ValueError('SABIA event provenance incomplete')
    if conn.execute('SELECT COUNT(*) FROM event_source_metadata WHERE web_publication_date IS NOT NULL').fetchone()[0]:
        raise ValueError('Invented SABIA publication date')
    if not sabia.get('complete') or sabia['details_ok']!=sabia['candidates'] or sabia['detail_errors']:
        raise ValueError('SABIA inventory/detail acquisition incomplete')
    if not and_public.get('complete') or sum(and_public['partitions'].values())!=and_public['archive_records']:
        raise ValueError('Andalucia archive accounting incomplete')
    if conn.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Foreign key integrity error')
    source_errors=[r for r in coverage if r['status']!='OK']
    result={
        'head_sha':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID'),
        'window_start':min(r['date'] for r in coverage if r['source_code'] in SOURCES),
        'window_end':max(r['date'] for r in coverage if r['source_code'] in SOURCES),
        'projects':before_projects,'events':before_events,
        'by_source':dict(conn.execute('SELECT source_code,COUNT(*) FROM events GROUP BY source_code')),
        'source_days_per_collector':counts,'source_day_errors':len(source_errors),
        'borm_index_rows':borm['rows'],'borm_index_retrieved_at':borm['retrieved_at'],
        'borm_fetch_attempts':len(borm['attempts']),'borm_recovered_after_retry':borm['recovered_after_retry'],
        'quality':{s:issues.get(s,0) for s in ('ERROR','WARN','INFO')},
        'invalid_project_identifiers':invalid,'missing_source_days':missing_days,
        'missing':dict(conn.execute('SELECT SUM(project_name IS NULL) no_name,SUM(power_mw IS NULL) no_mw,SUM(province IS NULL) no_province,SUM(expediente IS NULL) no_expediente FROM projects').fetchone()),
        'idempotent_replay':True,'event_provenance_complete':True,
        'sabia_inventory':sabia['candidates'],'sabia_details':sabia['details_ok'],
        'sabia_administrative_files_in_window':conn.execute('SELECT COUNT(DISTINCT environmental_code) FROM event_source_metadata').fetchone()[0],
        'sabia_unique_project_cards':conn.execute("SELECT COUNT(DISTINCT project_key) FROM events WHERE source_code='MITECO_SABIA'").fetchone()[0],
        'sabia_cards_not_in_other_collectors':conn.execute("SELECT COUNT(*) FROM projects p WHERE EXISTS(SELECT 1 FROM events e WHERE e.project_key=p.project_key AND e.source_code='MITECO_SABIA') AND NOT EXISTS(SELECT 1 FROM events e WHERE e.project_key=p.project_key AND e.source_code<>'MITECO_SABIA')").fetchone()[0],
        'sabia_milestone_scope':'ENTRY and CONSULT only; web publication dates unknown; authorization/resolution updates remain covered by gazettes, not derived from the SABIA current-state label',
        'andalucia_archive_records':and_public['archive_records'],
        'andalucia_source_metadata_gaps':and_public['source_gaps'],
        'andalucia_source_metadata_complete':and_public['dated_coverage_complete'],
        'geography':geography_accounting(build_commercial_rows(conn)),
        'ree_nodes_latest':conn.execute('SELECT COUNT(*) FROM ree_node_capacity WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM ree_node_capacity)').fetchone()[0],
        'miteco_installations_latest':conn.execute('SELECT COUNT(*) FROM miteco_production_registry WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM miteco_production_registry)').fetchone()[0],
        'miteco_exact_matches':len(rows('reports/miteco_exact_matches_latest.csv')),
    }
    result.update(validate_gva_integration(conn,coverage,quality))
    result.update(validate_dog_integration(conn,coverage))
    if invalid or missing_days or source_errors or issues['ERROR']:
        raise ValueError('Identity, source-day, or structural quality failure: '+json.dumps(result,ensure_ascii=False))
    return result


def main():
    conn=connect('data/spain_renewables.sqlite')
    result=metrics(conn,rows('reports/coverage_latest.csv'),rows('reports/quality_issues_latest.csv'),
                   json.loads(Path('reports/sabia/coverage.json').read_text()),
                   json.loads(Path('reports/andalucia_public/coverage.json').read_text()),
                   json.loads(Path('reports/borm/index_acquisition.json').read_text()))
    Path('reports/validation_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('CERTIFICATION',json.dumps(result,ensure_ascii=False),flush=True)
    conn.close()

if __name__=='__main__':main()
