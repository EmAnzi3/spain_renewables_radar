"""Ordinary execution wiring; synthetic events do not certify live coverage."""
from dataclasses import asdict
from datetime import date,timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.collectors import DOGCCollector
from app.db import connect
from app.lifecycle import commercial_stage
from app.run_pipeline import COLLECTOR_CLASSES,parse_args
from app.store import save_event
from scripts.validate_source_registry import validate_source_registry,validate_source_days
from scripts.validate_complete_pipeline import SOURCES
from test_dogc_projection import record,CATALOG
from app.dogc_projection import event_from_record

class OrdinaryDOGCTests(unittest.TestCase):
    def test_thirteen_collectors_are_consistent_without_counting_enrichments(self):
        result=validate_source_registry(SOURCES)
        self.assertEqual(result['discovery_collectors'],13)
        self.assertIn('DOGC',result['source_codes'])
        self.assertNotIn('REE_ACCESS',result['source_codes'])
        self.assertIs(COLLECTOR_CLASSES['DOGC'],DOGCCollector)

    def test_explicit_sources_remain_available_for_targeted_runs(self):
        with patch('sys.argv',['radar','--sources','DOGC']):
            self.assertEqual(parse_args().sources,'DOGC')

    def test_pre_existing_source_membership_is_preserved(self):
        old={'BOE','BOCYL','BOA','BOJA','DOCM','DOE','BORM','BOCM','AND_PUBLIC','GVA_PUBLIC','MITECO_SABIA','DOG'}
        self.assertEqual(set(COLLECTOR_CLASSES)-{'DOGC'},old)

    def test_environmental_screening_stays_permitting_not_dia_or_authorized(self):
        self.assertEqual(commercial_stage('ENVIRONMENTAL_SCREENING'),'PERMITTING')
        self.assertEqual(commercial_stage('CONSTRUCTION_AUTH'),'AUTHORIZED')
        self.assertEqual(commercial_stage('PUBLIC_INFO'),'EARLY')

    def test_existing_dossier_accumulates_dogc_event_and_retains_original(self):
        with tempfile.TemporaryDirectory() as td:
            conn=connect(str(Path(td)/'test.sqlite'))
            r,p=record();event,_=event_from_record(r,p,CATALOG)
            original=type(event)(**asdict(event));original.source_code='BOE';original.external_id='BOE-fixture'
            original.url='https://www.boe.es/example';original.event_type='PUBLIC_INFO';original.commercial_stage='EARLY'
            original.publication_date='2026-09-01'
            self.assertEqual(save_event(conn,original),(True,True))
            first=dict(conn.execute("SELECT * FROM events WHERE source_code='BOE'").fetchone())
            self.assertEqual(save_event(conn,event),(True,False))
            self.assertEqual(save_event(conn,event),(False,False))
            self.assertEqual(conn.execute('SELECT count(*) FROM projects').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM events').fetchone()[0],2)
            self.assertEqual(dict(conn.execute("SELECT * FROM events WHERE source_code='BOE'").fetchone()),first)
            conn.close()

    def fixture(self):
        start=date(2026,9,5)
        return [{'source_code':s,'date':str(start+timedelta(days=i)),'status':'OK'} for s in ('BOE','DOGC') for i in range(30)]

    def test_source_coverage_proves_unique_contiguous_days(self):
        result=validate_source_days(self.fixture(),{'BOE','DOGC'})
        self.assertEqual(result['source_day_rows'],60)
        self.assertEqual(result['end'],'2026-10-04')

    def test_repeated_day_cannot_replace_a_missing_day(self):
        data=self.fixture();data[-1]=dict(data[-2])
        with self.assertRaises(ValueError):validate_source_days(data,{'BOE','DOGC'})

    def test_sources_cannot_have_different_thirty_day_windows(self):
        data=self.fixture()
        for row in data:
            if row['source_code']=='DOGC':row['date']=str(date.fromisoformat(row['date'])+timedelta(days=1))
        with self.assertRaises(ValueError):validate_source_days(data,{'BOE','DOGC'})

    def test_failed_and_noncontiguous_days_are_not_coverage_success(self):
        for failure in ('ERROR','gap'):
            data=self.fixture()
            if failure=='ERROR':data[-1]['status']='ERROR'
            else:data[-1]['date']='2026-10-06'
            with self.assertRaises(ValueError):validate_source_days(data,{'BOE','DOGC'})

    def test_registry_cannot_claim_disabled_dogc_is_integrated(self):
        with tempfile.TemporaryDirectory() as td:
            entries=json.loads(Path('config/sources.json').read_text())
            for r in entries:
                if r['code']=='DOGC':r['implemented']=False
            path=Path(td)/'sources.json';path.write_text(json.dumps(entries))
            with self.assertRaises(ValueError):validate_source_registry(SOURCES,path)
