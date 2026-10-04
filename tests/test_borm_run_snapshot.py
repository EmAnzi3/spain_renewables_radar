import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock,patch

from app.collectors.borm import BORMCollector,INDEX_JSON
from app.run_snapshot import snapshot_paths
import test_borm_transport


class BORMSameRunSnapshotTests(unittest.TestCase):
    def test_smoke_and_backfill_use_one_original_acquisition(self):
        fixture=test_borm_transport.BORMTransportTests();fixture.setUp()
        raw=json.dumps([fixture.row]).encode('utf-8-sig')
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'BORM_RUN_SNAPSHOT_DIR':tmp+'/snapshot','BORM_RUN_SNAPSHOT_SCOPE':'run-1:attempt-1'}),patch('app.collectors.borm.Path',side_effect=lambda p:Path(tmp)/p):
            smoke=BORMCollector();smoke.session.get=Mock(return_value=fixture.response(raw))
            smoke_events=smoke.collect_day(date(2026,10,2))
            original=smoke.audit.copy()
            backfill=BORMCollector();backfill.session.get=Mock(side_effect=AssertionError('unexpected second network call'))
            events=backfill.collect_day(date(2026,10,2))
            self.assertEqual(events,smoke_events)
            backfill.session.get.assert_not_called()
            self.assertEqual(backfill.audit['acquisition_mode'],'RUN_SNAPSHOT_REUSE')
            self.assertEqual(backfill.audit['retrieved_at'],original['retrieved_at'])
            self.assertEqual(backfill.audit['sha256'],original['sha256'])
            self.assertEqual(backfill.audit['attempts'],original['attempts'])
            self.assertEqual((Path(tmp)/'reports/borm/index_raw.json').read_bytes(),raw)

    def test_new_attempt_must_fetch_live_again(self):
        fixture=test_borm_transport.BORMTransportTests();fixture.setUp()
        raw=json.dumps([fixture.row]).encode()
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'BORM_RUN_SNAPSHOT_DIR':tmp+'/snapshot','BORM_RUN_SNAPSHOT_SCOPE':'run-1:attempt-1'}),patch('app.collectors.borm.Path',side_effect=lambda p:Path(tmp)/p):
            first=BORMCollector();first.session.get=Mock(return_value=fixture.response(raw));first._rows()
            os.environ['BORM_RUN_SNAPSHOT_SCOPE']='run-1:attempt-2'
            second=BORMCollector();second.session.get=Mock(return_value=fixture.response(raw));second._rows()
            second.session.get.assert_called_once()
            self.assertEqual(second.audit['acquisition_mode'],'LIVE')

    def test_bad_snapshot_does_not_hide_live_failure(self):
        fixture=test_borm_transport.BORMTransportTests();fixture.setUp()
        raw=json.dumps([fixture.row]).encode()
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'BORM_RUN_SNAPSHOT_DIR':tmp+'/snapshot','BORM_RUN_SNAPSHOT_SCOPE':'run-1:attempt-1'}),patch('app.collectors.borm.Path',side_effect=lambda p:Path(tmp)/p),patch('app.collectors.borm.time.sleep'):
            first=BORMCollector();first.session.get=Mock(return_value=fixture.response(raw));first._rows()
            raw_path,_=snapshot_paths(tmp+'/snapshot','run-1:attempt-1',INDEX_JSON)
            raw_path.write_bytes(b'<html>corrupt</html>')
            second=BORMCollector();second.session.get=Mock(return_value=fixture.response(b'Forbidden',403))
            with self.assertRaisesRegex(RuntimeError,'403'):second._rows()
            second.session.get.assert_called_once()
            self.assertFalse(second.audit['complete'])


if __name__=='__main__':unittest.main()
