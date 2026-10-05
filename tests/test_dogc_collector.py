import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from app.collectors.dogc import DOGCCollector
from app.db import connect
from app.store import save_event
from test_dogc_projection import record,CATALOG

DAY=date(2026,9,8)

class CollectorTests(unittest.TestCase):
    def collector(self,root,published=False):
        c=DOGCCollector(output=str(root/'output'),catalog=CATALOG)
        c._month=Mock(return_value={DAY:'9747' if published else None})
        return c

    def test_official_zero_is_success_not_inferred_weekend(self):
        with tempfile.TemporaryDirectory() as td:
            c=self.collector(Path(td));c.index.post=Mock(return_value={'numResultSearch':0})
            self.assertEqual(c.collect_day(DAY),[])
            self.assertTrue(c.audit['complete']);self.assertEqual(c.audit['days'][str(DAY)]['status'],'OK');c.close()

    def test_missing_result_count_not_an_empty_success(self):
        with tempfile.TemporaryDirectory() as td:
            c=self.collector(Path(td));c.index.post=Mock(return_value={})
            with self.assertRaises(ValueError):c.collect_day(DAY)
            self.assertFalse(c.audit['complete']);self.assertEqual(c.audit['days'][str(DAY)]['status'],'ERROR');c.close()

    def test_successful_day_replay_does_not_refetch(self):
        with tempfile.TemporaryDirectory() as td:
            c=self.collector(Path(td));c.index.post=Mock(return_value={'numResultSearch':0})
            c.collect_day(DAY);c.collect_day(DAY);self.assertEqual(c.index.post.call_count,1);c.close()

    def test_failed_day_not_silently_retried_as_zero(self):
        with tempfile.TemporaryDirectory() as td:
            c=self.collector(Path(td));c.index.post=Mock(side_effect=RuntimeError('source down'))
            for _ in range(2):
                with self.assertRaises(RuntimeError):c.collect_day(DAY)
            self.assertEqual(c.index.post.call_count,1);c.close()

    def run_candidate(self,root,category='ENERGY_PROJECT',complete=True):
        c=self.collector(root,True);r,p=record();r['category']=category
        candidate={'document_id':'1','title':'Planta BESS Demo','publication_date':str(DAY),'edition':'9747','base_edition':'9747','source_url':r['source_url']}
        search={'numResultSearch':1,'resultSearch':[{'idDocument':'1','title':candidate['title'],'date':'08/09/2026','tipusDiari':'DOGC','linkTitle':'?documentId=1'}]}
        c.index.post=Mock(side_effect=[{},search]);c.bodies.get_pdf=Mock(return_value=(b'%PDF',{'sha256':r['pdf_sha256'],'retrieved_at':r['source_retrieved_at']}))
        patches=[patch('app.collectors.dogc.parse_summary',return_value={('1',str(DAY)):candidate}),
                 patch('app.collectors.dogc.summary_scopes',return_value=[('9747',{})]),
                 patch('app.collectors.dogc.extract_pages',return_value={'pages':p,'publication_evidence_complete':complete,'empty_text_pages':[]}),
                 patch('app.collectors.dogc.classify_document',return_value=r)]
        for value in patches:value.start();self.addCleanup(value.stop)
        return c

    def test_energy_event_retains_source_and_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.run_candidate(root);events=c.collect_day(DAY)
            self.assertEqual(len(events),1);self.assertEqual(c.audit['totals']['energy_events'],1)
            conn=connect(str(root/'test.sqlite'));save_event(conn,events[0]);c.persist_metadata(conn)
            meta=conn.execute("SELECT * FROM regional_public_metadata WHERE source_code='DOGC'").fetchone()
            self.assertEqual(meta['external_id'],'1');self.assertEqual(meta['source_url'],events[0].url)
            self.assertEqual(conn.execute('SELECT count(*) FROM dogc_document_observations').fetchone()[0],1)
            self.assertEqual(save_event(conn,events[0]),(False,False));conn.close();c.close()

    def test_local_lead_is_preserved_but_not_a_granted_energy_project(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.run_candidate(root,'MUNICIPAL_PROJECT')
            self.assertEqual(c.collect_day(DAY),[]);self.assertEqual(c.audit['totals']['municipal_leads'],1)
            conn=connect(str(root/'test.sqlite'));c.persist_metadata(conn)
            self.assertEqual(conn.execute('SELECT count(*) FROM projects').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT count(*) FROM dogc_document_observations').fetchone()[0],1)
            self.assertEqual(len(json.loads((c.generation/'municipal_leads.json').read_text())),1);conn.close();c.close()

    def test_header_must_be_verified_before_event_creation(self):
        with tempfile.TemporaryDirectory() as td:
            c=self.run_candidate(Path(td),complete=False)
            with self.assertRaises(ValueError):c.collect_day(DAY)
            self.assertFalse(c.audit['complete']);self.assertEqual(c.projected,{});c.close()

    def test_unrecognized_semantics_fail_the_source_day(self):
        with tempfile.TemporaryDirectory() as td:
            c=self.run_candidate(Path(td),'REVIEW_REQUIRED')
            with self.assertRaises(ValueError):c.collect_day(DAY)
            self.assertEqual(c.audit['totals']['review_required'],1);self.assertEqual(c.projected,{});c.close()

    def test_metadata_cannot_be_attached_to_an_unpersisted_event(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.run_candidate(root);c.collect_day(DAY);conn=connect(str(root/'test.sqlite'))
            with self.assertRaises(ValueError):c.persist_metadata(conn)
            conn.close();c.close()
