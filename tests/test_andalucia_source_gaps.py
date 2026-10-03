import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.collectors.andalucia_public import partition_archive, validate_archive, write_source_gaps
from test_andalucia_public import RONDA

class AndaluciaSourceGapTests(unittest.TestCase):
    def test_source_tombstones_and_undated_records_are_preserved(self):
        title_missing={'id':'197389','update_date':'2026-03-04T12:15:11.000Z'}
        undated=dict(RONDA,id='10831',publication_date=None)
        non_target={'id':'595925','title':'Convocatoria de empleo público'}
        records=[RONDA,title_missing,undated,non_target]
        original=copy.deepcopy(records)
        parts=partition_archive(validate_archive(records,4))
        self.assertEqual({k:len(v) for k,v in parts.items()},
                         {'dated':1,'undated':1,'missing_title':1,'non_target':1})
        self.assertEqual(parts['undated'][0]['publication_date'],None)
        self.assertEqual(records,original)
        with tempfile.TemporaryDirectory() as tmp:
            gaps=write_source_gaps(parts,Path(tmp))
            self.assertEqual(len(gaps),2)
            saved=json.loads((Path(tmp)/'source_gaps.json').read_text())
            self.assertEqual(saved[0]['raw_record'],title_missing)
            self.assertEqual(saved[1]['raw_record'],undated)
            self.assertIn('10831',(Path(tmp)/'source_gaps.html').read_text())

    def test_wrong_title_type_remains_a_structural_error(self):
        with self.assertRaisesRegex(ValueError,'title type'):
            validate_archive([{'id':'1','title':['unexpected schema']}],1)

    def test_bad_source_identity_is_not_ignored(self):
        with self.assertRaisesRegex(ValueError,'malformed identity'):
            validate_archive([{'title':'Missing identity'}],1)

    def test_gap_html_escapes_source_text(self):
        record=dict(RONDA,publication_date=None,title='Fotovoltaica <script>alert(1)</script>')
        parts=partition_archive([record])
        with tempfile.TemporaryDirectory() as tmp:
            write_source_gaps(parts,Path(tmp))
            value=(Path(tmp)/'source_gaps.html').read_text()
            self.assertNotIn('<script>',value)
            self.assertIn('&lt;script&gt;',value)

if __name__=='__main__':
    unittest.main()
