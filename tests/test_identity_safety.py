import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.collectors.boa import BOACollector
from app.db import connect
from app.identity_migration import repair_legacy_identities
from app.parser import extract_project_name
from app.store import save_event
from test_identity_integrity import event

class IdentitySafetyTests(unittest.TestCase):
    def test_ambiguous_cross_source_match_is_not_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/'test.sqlite'))
            save_event(conn,event(code='a',expediente='REF-111'))
            save_event(conn,event(code='b',expediente='REF-222'))
            save_event(conn,event(code='c',source='AND_PUBLIC',expediente=''))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0],3);conn.close()

    def test_same_name_with_incompatible_evidence_is_not_merged(self):
        for field,value in [('power_mw',60),('publication_date','2026-09-30'),('promoter','Other Owner S.L.')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                conn=connect(str(Path(tmp)/'test.sqlite'))
                base=event();base.promoter='Original Owner S.L.';save_event(conn,base)
                other=event(code='other',source='AND_PUBLIC',expediente='');setattr(other,field,value);save_event(conn,other)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0],2);conn.close()

    def test_recycling_notice_is_excluded_by_collector(self):
        from datetime import date
        row={'DOCN':'X1','Titulo':'Información pública de una planta de reciclaje de paneles fotovoltaicos.',
             'Texto':'Planta La Estación, de 50 MW.', 'UrlPdf':'https://www.boa.aragon.es/test.pdf'}
        self.assertEqual(BOACollector.events_from_row(date(2026,10,1),row),[])

    def test_source_quarantine_preserves_original_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/'test.sqlite'))
            source=event('Rosi Energy','out',source='BOA')
            source.title='Planta de reciclaje de paneles fotovoltaicos Rosi Energy'
            source.raw_text='Exact original official source text';save_event(conn,source)
            original=dict(conn.execute('SELECT * FROM events').fetchone())
            result=repair_legacy_identities(conn,report_dir=Path(tmp)/'reports')
            self.assertEqual(result['quarantined_source_events'],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)
            payload=conn.execute('SELECT payload_json FROM quarantined_source_events').fetchone()[0]
            self.assertEqual(json.loads(payload),original);conn.close()

    def test_migration_rolls_back_when_source_invariant_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/'test.sqlite'));save_event(conn,event())
            conn.execute("UPDATE events SET expediente='incoado'");conn.commit()
            before=[tuple(row) for row in conn.execute('SELECT * FROM events')]
            with patch('app.identity_migration._source_fingerprint',side_effect=['before','after']):
                with self.assertRaisesRegex(RuntimeError,'Source payload changed'):
                    repair_legacy_identities(conn,report_dir=Path(tmp)/'reports')
            self.assertEqual(before,[tuple(row) for row in conn.execute('SELECT * FROM events')])
            self.assertEqual(len(list((Path(tmp)/'migrations').glob('*.sqlite'))),1);conn.close()

    def test_explicit_viso_name_beats_description_of_inverters(self):
        text='La planta fotovoltaica dispondrá de 25 inversores. Tecnología solar fotovoltaica denominada «PSFV Viso Energy».'
        self.assertEqual(extract_project_name(text),'PSFV Viso Energy')

if __name__=='__main__':unittest.main()
