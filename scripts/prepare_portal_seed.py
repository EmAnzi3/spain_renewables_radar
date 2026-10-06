"""Materialize a verified historical artifact; never call it a live refresh."""
from __future__ import annotations
import argparse,csv,hashlib,json,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from app.db import connect
from app.docm_storage import repair_and_record,validate_docm_storage
from app.enrichment.ine_municipalities import parse_ine_municipalities,enrich_missing_project_geography
from app.operational import save_state,validate_database,event_fingerprints,atomic_json

def prepare(seed:Path,database:Path,status_path:Path):
    metrics=json.loads((seed/'reports/validation_metrics.json').read_text(encoding='utf-8'))
    original=seed/'data/spain_renewables.sqlite'
    if not original.exists():raise ValueError('No baseline database')
    if database.exists():raise ValueError('Seed never overwrites an existing operational database')
    database.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(f'file:{original.resolve()}?mode=ro',uri=True)) as old,closing(sqlite3.connect(database)) as dest:old.backup(dest)
    conn=connect(str(database));before=event_fingerprints(conn)
    if conn.execute('SELECT count(*) FROM projects').fetchone()[0]!=metrics['projects'] or conn.execute('SELECT count(*) FROM events').fetchone()[0]!=metrics['events']:
        raise ValueError('Baseline metric counts differ from its database')
    repair=repair_and_record(conn,str(status_path.parent/'docm_repair'))
    catalogs=list((seed/'reports/dogc').rglob('ine_municipalities.json'))
    if not catalogs:raise ValueError('No original INE catalogue in baseline')
    raw=sorted(catalogs)[-1].read_bytes()
    previous_geo={r[0]:r[1] for r in conn.execute('SELECT project_key,status FROM project_geo_enrichment')}
    geo=enrich_missing_project_geography(conn,parse_ine_municipalities(json.loads(raw)))
    for row in conn.execute('SELECT project_key FROM project_geo_enrichment').fetchall():
        if previous_geo.get(row[0]) in (None,'UNRESOLVED'):
            conn.execute('UPDATE project_geo_enrichment SET reference_date=NULL WHERE project_key=?',(row[0],))
    conn.commit();validate_docm_storage(conn);validate_database(conn,before)
    with (seed/'reports/coverage_latest.csv').open(encoding='utf-8-sig') as f:coverage=list(csv.DictReader(f))
    from app.run_pipeline import COLLECTOR_CLASSES
    states={}
    for code in COLLECTOR_CLASSES:
        own=[r for r in coverage if r['source_code']==code]
        if len(own)!=30 or any(r['status']!='OK' for r in own):raise ValueError('Baseline is not a complete 30-day source record')
        dates=sorted(r['date'] for r in own)
        if len(set(dates))!=30:raise ValueError('Duplicated baseline source day')
        states[code]={'source_code':code,'status':'HISTORICAL','successful_days':0,'failed_days':[],
                     'last_complete_window_start':dates[0],'last_complete_window_end':dates[-1],
                     'last_complete_run_id':'37406054339','last_complete_observed_at':None}
    status={'run_key':'historical-seed-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
            'state':'SNAPSHOT','full_certification':False,'complete_sources':0,'sources':states,
            'message':'Dati dell’ultimo backfill completato, 6 settembre–5 ottobre 2026. Correzione Almagro applicata e verificata dagli originali. GVA non è stata riacquisita: questo è uno snapshot consultabile, non una nuova scansione live.',
            'provenance_note':'Base: run 37406054339. Correzione DOCM Almagro verificata. La generazione della pagina non aggiorna le date delle fonti.',
            'seed_run_id':'37406054339','seed_was_not_redated':True,'repair':repair,
            'ine_reference_date_not_inferred':True,'ine_historical_response_sha256':hashlib.sha256(raw).hexdigest(),'geography_replay':geo}
    save_state(conn,status);conn.close();atomic_json(status_path,status);return status

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',required=True)
    p.add_argument('--db',default='data/spain_renewables.sqlite');p.add_argument('--status',default='reports/operational/latest.json')
    a=p.parse_args();s=prepare(Path(a.seed),Path(a.db),Path(a.status));print('HISTORICAL_SEED',json.dumps(s,ensure_ascii=False))
if __name__=='__main__':main()
