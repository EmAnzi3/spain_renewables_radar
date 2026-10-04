import hashlib,json,tempfile,unittest
from pathlib import Path
from app.db import connect
from app.store import save_event
from app.collectors.dog import DOGCollector,events_from_notice,parse_notice
from scripts.dog_integration_gate import validate_dog_integration
from test_dog import FIXTURES,fixture_html

class DOGGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.conn=connect(str(self.root/'db.sqlite'))
        self.collector=DOGCollector(output_dir=self.root)
        raw=fixture_html(FIXTURES[0]);notice=parse_notice(raw,FIXTURES[0]);digest=hashlib.sha256(raw).hexdigest()
        (self.root/'raw'/(digest+'.bin')).write_bytes(raw)
        self.collector.notices[notice['external_id']]=notice
        self.collector.audit['acquisitions']=[dict(complete=True,sha256=digest,bytes=len(raw))]
        self.collector.audit['days']={'2026-09-07':dict(status='OK',editions=1,index_notices=1,candidates=1,events=1)}
        for event,row in zip(events_from_notice(notice),notice['records']):
            save_event(self.conn,event);self.collector.metadata[event.external_id]=(notice,row)
        self.collector.persist_metadata(self.conn);self.collector._save()
        self.coverage=[dict(source_code='DOG',date='2026-09-07',status='OK')]
    def tearDown(self):
        self.conn.close();self.tmp.cleanup()
    def verify(self):
        return validate_dog_integration(self.conn,self.coverage,root=self.root,expected_days=1)
    def test_source_rebuild_agrees_with_integrated_database(self):
        result=self.verify();self.assertEqual(result['dog_projects'],1)
        self.assertTrue(result['dog_original_provenance_verified'])
    def test_missing_source_day_fails(self):
        self.coverage=[]
        with self.assertRaises(ValueError):self.verify()
    def test_changed_event_power_fails(self):
        self.conn.execute('UPDATE events SET power_mw=750');self.conn.commit()
        with self.assertRaises(ValueError):self.verify()
    def test_wrong_metadata_publication_fails(self):
        self.conn.execute("UPDATE regional_public_metadata SET web_publication_date='2026-08-06'");self.conn.commit()
        with self.assertRaises(ValueError):self.verify()
    def test_corrupted_original_bytes_fail(self):
        for path in (self.root/'raw').glob('*.bin'):path.write_bytes(b'changed source')
        with self.assertRaises(ValueError):self.verify()

if __name__=='__main__':unittest.main()
