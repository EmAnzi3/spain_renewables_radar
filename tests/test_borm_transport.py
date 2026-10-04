import copy,json,tempfile,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch,Mock
import requests

from app.collectors.borm import BORMCollector,INDEX_JSON
import test_borm


class BORMTransportTests(unittest.TestCase):
    def setUp(self):
        self.row=test_borm.BORMCollectorTests()._row('2026-10-02 00:00:00',
          'Anuncio de información pública de instalación fotovoltaica «FV Demo» de 5 MW.')

    def response(self,content,status=200):
        r=requests.Response();r._content=content;r.status_code=status;r.url=INDEX_JSON
        r.headers['content-type']='application/json' if content.startswith(b'[') else 'text/html'
        return r

    def test_html_200_then_json_is_retried_and_audited_once(self):
        collector=BORMCollector();good=json.dumps([self.row]).encode()
        with tempfile.TemporaryDirectory() as tmp,patch('app.collectors.borm.Path',side_effect=lambda p:Path(tmp)/p),patch('app.collectors.borm.time.sleep') as sleep:
            collector.session.get=Mock(side_effect=[self.response(b'<html>Service temporarily unavailable</html>'),self.response(good)])
            events=collector.collect_day(date(2026,10,2))
            self.assertEqual(len(events),1);self.assertEqual(collector.session.get.call_count,2)
            self.assertTrue(collector.audit['complete']);self.assertTrue(collector.audit['recovered_after_retry'])
            self.assertIn('JSONDecodeError',collector.audit['attempts'][0]['error'])
            self.assertEqual(collector._rows(),[self.row]);self.assertEqual(collector.session.get.call_count,2)
            self.assertTrue((Path(tmp)/'reports/borm/index_raw.json').exists());sleep.assert_called_once()

    def test_permanent_bad_response_never_becomes_empty_success_or_thirty_download_cycles(self):
        collector=BORMCollector()
        with tempfile.TemporaryDirectory() as tmp,patch('app.collectors.borm.Path',side_effect=lambda p:Path(tmp)/p),patch('app.collectors.borm.time.sleep'):
            collector.session.get=Mock(return_value=self.response(b'<html>Maintenance</html>'))
            for day in (date(2026,10,1),date(2026,10,2),date(2026,10,3)):
                with self.assertRaisesRegex(RuntimeError,'unavailable'):collector.collect_day(day)
            self.assertEqual(collector.session.get.call_count,4);self.assertFalse(collector.audit['complete'])

    def test_bom_bytes_are_valid_json_not_html_failure(self):
        collector=BORMCollector()
        with tempfile.TemporaryDirectory() as tmp,patch('app.collectors.borm.Path',side_effect=lambda p:Path(tmp)/p):
            collector.session.get=Mock(return_value=self.response(json.dumps([self.row]).encode('utf-8-sig')))
            self.assertEqual(len(collector._rows()),1);self.assertTrue(collector.audit['complete'])

    def test_invalid_or_duplicate_index_row_is_structural_error(self):
        for payload in ({},[],[['short']], [self.row,self.row], [dict()]):
            with self.subTest(payload=payload),self.assertRaises(ValueError):BORMCollector.validate_index(payload)
        bad=copy.deepcopy(self.row);bad[4]='invalid'
        with self.assertRaisesRegex(ValueError,'publication date'):BORMCollector.validate_index([bad])

    def test_403_is_not_retried_or_bypassed(self):
        collector=BORMCollector()
        with tempfile.TemporaryDirectory() as tmp,patch('app.collectors.borm.Path',side_effect=lambda p:Path(tmp)/p),patch('app.collectors.borm.time.sleep') as sleep:
            collector.session.get=Mock(return_value=self.response(b'Forbidden',403))
            with self.assertRaisesRegex(RuntimeError,'403'):collector._rows()
            self.assertEqual(collector.session.get.call_count,1);sleep.assert_not_called()

    def test_timeout_and_500_recover_without_manufacturing_records(self):
        collector=BORMCollector()
        with tempfile.TemporaryDirectory() as tmp,patch('app.collectors.borm.Path',side_effect=lambda p:Path(tmp)/p),patch('app.collectors.borm.time.sleep'):
            collector.session.get=Mock(side_effect=[requests.Timeout('connection lost'),self.response(b'Try later',500),self.response(json.dumps([self.row]).encode())])
            self.assertEqual(collector._rows(),[self.row]);self.assertEqual(len(collector.audit['attempts']),3)

if __name__=='__main__':unittest.main()
