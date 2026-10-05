"""A known multi-province project is not an unresolved geography to repair."""
import json
from pathlib import Path
import tempfile
import unittest

from app.db import connect
from app.enrichment.ine_municipalities import enrich_missing_project_geography
from app.dogc_projection import event_from_record
from app.collectors.dogc import DOGCCollector
from app.store import save_event
from scripts.validate_source_registry import validate_dogc_geography
from test_dogc_projection import record,CATALOG

class GeographyPreservationTests(unittest.TestCase):
    def seeded(self,root,source='DOGC'):
        conn=connect(str(root/'test.sqlite'))
        r,pages=record();event,evidence=event_from_record(r,pages,CATALOG)
        event.province=None
        save_event(conn,event)
        collector=DOGCCollector(output=str(root/'dogc'),catalog=CATALOG)
        geo={'status':'MULTI_PROVINCE','provinces':['Barcelona','Lleida'],
             'municipalities':[{'name':'Municipality A','province':'Barcelona','code':'00001'},
                               {'name':'Municipality B','province':'Lleida','code':'00002'}],
             'source_quote':'Synthetic two-province fixture','unresolved_text':None,'ambiguous_codes':[]}
        evidence['extraction']['geography']=geo
        collector.metadata={event.external_id:evidence}
        collector.records={event.external_id:{'classification':r}}
        # Persistence, not HTML rendering or live acquisition, is under test.
        collector._save=lambda:None
        collector.persist_metadata(conn);collector.close()
        conn.execute('UPDATE project_geo_enrichment SET source_code=?',(source,));conn.commit()
        return conn,event

    def test_fallback_enrichment_preserves_any_existing_source_multi_province_evidence(self):
        for source in ('DOGC','MITECO_SABIA','INE_MUNICIPALITIES','OTHER_OFFICIAL'):
            with tempfile.TemporaryDirectory() as td:
                conn,event=self.seeded(Path(td),source)
                before=dict(conn.execute('SELECT * FROM project_geo_enrichment').fetchone())
                event_before=dict(conn.execute('SELECT * FROM events').fetchone())
                result=enrich_missing_project_geography(conn,CATALOG)
                self.assertEqual(result['details'],[])
                self.assertEqual(dict(conn.execute('SELECT * FROM project_geo_enrichment').fetchone()),before)
                self.assertEqual(dict(conn.execute('SELECT * FROM events').fetchone()),event_before)
                self.assertIsNone(conn.execute('SELECT province FROM projects').fetchone()[0])
                conn.close()

    def test_ordinary_gate_checks_source_geography_and_no_mw_allocation(self):
        with tempfile.TemporaryDirectory() as td:
            conn,_=self.seeded(Path(td));enrich_missing_project_geography(conn,CATALOG)
            result=validate_dogc_geography(conn)
            self.assertEqual(result['multi_province_projects_verified'],1)
            self.assertTrue(result['no_duplicate_provincial_mw_allocation']);conn.close()

    def test_gate_rejects_prior_silent_overwrite_to_unresolved(self):
        with tempfile.TemporaryDirectory() as td:
            conn,_=self.seeded(Path(td))
            conn.execute("UPDATE project_geo_enrichment SET status='UNRESOLVED',provinces_json='[]'");conn.commit()
            with self.assertRaises(ValueError):validate_dogc_geography(conn)
            conn.close()

    def test_gate_rejects_loss_of_one_documented_province(self):
        with tempfile.TemporaryDirectory() as td:
            conn,_=self.seeded(Path(td))
            conn.execute("UPDATE project_geo_enrichment SET provinces_json=?",(json.dumps(['Barcelona']),));conn.commit()
            with self.assertRaises(ValueError):validate_dogc_geography(conn)
            conn.close()
