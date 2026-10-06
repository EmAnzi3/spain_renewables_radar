import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import requests
from app.gva_preflight import run_preflight
from app.gva_catalogue import row_signature, parse_receipts


class PreflightTests(unittest.TestCase):
    def fake(self):
        c=Mock()
        c.inventory=[{'external_id':'one'}]
        c.audit={'complete':True,'declared_records':1,'distinct_ids':1,'pages':1,'catalogue_mode':'LIVE_FULL_CATALOGUE'}
        return c

    def test_success_does_not_claim_events_or_full_backfill(self):
        c=self.fake()
        with tempfile.TemporaryDirectory() as tmp, patch('app.gva_preflight.GVAPublicCollector', return_value=c):
            result=run_preflight(tmp)
            self.assertTrue(result['catalogue_ready'])
            self.assertFalse(result['thirteen_source_backfill_certified'])
            self.assertEqual(result['project_events_created'],0)
            self.assertEqual(json.loads((Path(tmp)/'preflight.json').read_text()),result)
        c.session.close.assert_called_once()

    def test_network_failure_persists_failure_and_propagates(self):
        c=self.fake();c._load.side_effect=requests.ConnectTimeout('source unreachable')
        with tempfile.TemporaryDirectory() as tmp, patch('app.gva_preflight.GVAPublicCollector',return_value=c):
            with self.assertRaises(requests.ConnectTimeout):run_preflight(tmp)
            report=json.loads((Path(tmp)/'preflight.json').read_text())
            self.assertFalse(report['catalogue_ready'])
            self.assertEqual(report['error_type'],'ConnectTimeout')
        c.session.close.assert_called_once()

    def test_partial_catalogue_cannot_be_ready(self):
        for field,value in [('complete',False),('declared_records',2),('distinct_ids',0)]:
            c=self.fake();c.audit[field]=value
            with tempfile.TemporaryDirectory() as tmp, patch('app.gva_preflight.GVAPublicCollector',return_value=c):
                with self.assertRaises(ValueError):run_preflight(tmp)
                self.assertFalse(json.loads((Path(tmp)/'preflight.json').read_text())['catalogue_ready'])

    def test_empty_catalogue_is_not_a_false_zero_opportunity_success(self):
        c=self.fake();c.inventory=[];c.audit.update(declared_records=0,distinct_ids=0)
        with tempfile.TemporaryDirectory() as tmp, patch('app.gva_preflight.GVAPublicCollector',return_value=c):
            with self.assertRaises(ValueError):run_preflight(tmp)

    def test_navigation_query_can_change_but_source_host_path_cannot(self):
        base={'external_id':'1','title':'T','url':'https://mediambient.gva.es/energy?x_assetEntryId=1&x_cur=2'}
        other=dict(base,url=base['url'].replace('cur=2','cur=3'))
        self.assertEqual(row_signature([base]),row_signature([other]))
        for link in ['https://cindi.gva.es/energy?x_assetEntryId=1','https://mediambient.gva.es/elsewhere?x_assetEntryId=1']:
            self.assertNotEqual(row_signature([base]),row_signature([dict(base,url=link)]))

    def test_snapshot_receipt_needs_timezone_and_official_url(self):
        receipt={'url':'https://mediambient.gva.es/energy','retrieved_at':'2026-10-06T06:00:00'}
        with self.assertRaises(ValueError):parse_receipts([receipt],Path('.'))
        receipt.update(url='https://evil.invalid/energy',retrieved_at='2026-10-06T06:00:00+00:00')
        with self.assertRaises(ValueError):parse_receipts([receipt],Path('.'))

    def test_snapshot_receipts_are_bounded_before_reading_files(self):
        for receipts in (None, [], [{}]*251):
            with self.assertRaises(ValueError):parse_receipts(receipts,Path('.'))
