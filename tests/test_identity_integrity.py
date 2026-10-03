import sqlite3
import tempfile
import unittest
from pathlib import Path
from app.db import connect
from app.identifiers import extract_identifier, valid_expediente
from app.identity_migration import repair_legacy_identities
from app.parser import parse_event, build_project_key, detect_technology, extract_project_name
from app.store import save_event


def event(name='Demo', code='X1', source='BOE', when='2026-10-01', expediente='EX-123'):
    return parse_event(source_code=source,external_id=code,publication_date=when,
                       title=f'Información pública de la instalación fotovoltaica «{name}», de 50 MW, en la provincia de Madrid. Expediente: {expediente}.',url='https://example.invalid/'+code,raw_text='')

class IdentityIntegrityTests(unittest.TestCase):
    def test_prose_cannot_become_identifier_or_merge_key(self):
        for word in ('incoado','para','INAGA','Persona','del','PRETOR','expropiatorio'):
            self.assertIsNone(extract_identifier('Expediente '+word));self.assertFalse(valid_expediente(word))
        self.assertNotEqual(build_project_key('Plant A','PV','Madrid','1','incoado'),build_project_key('Plant B','PV','Madrid','2','incoado'))

    def test_official_qualified_codes_and_title_references(self):
        self.assertEqual(extract_identifier('Número de Expediente: INAGA 500306/01l/2026/04176.'),'INAGA 500306/01l/2026/04176')
        self.assertEqual(extract_identifier('Referencia: 2703/01644.'),'2703/01644')
        self.assertEqual(extract_identifier('Expediente: PRETOR 2448 AAU/JA/035/2024'),'PRETOR 2448')
        self.assertIsNone(extract_identifier('Se obtuvo la servidumbre aeronáutica, expediente P24-0252.',body=True))
        self.assertIsNone(extract_identifier('Expediente: PFot-1. Expediente: PFot-2.',body=True))

    def test_biological_hybridization_is_not_energy(self):
        self.assertIsNone(detect_technology('Material para inmunohistoquímica, hibridación in situ e inmunofluorescencia'))

    def test_wind_name_not_truncated_by_decimal_comma(self):
        self.assertEqual(extract_project_name('PARQUE EOLICO LOKI DE 19,8 MW E INFRAESTRUCTURA DE EVACUACIÓN'),'LOKI')

    def test_older_source_event_does_not_replace_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=connect(str(Path(tmp)/'test.sqlite'))
            later=event(when='2026-10-02');later.event_type='CONSTRUCTION_AUTH';later.commercial_stage='AUTHORIZED'
            earlier=event(code='X0',when='2026-09-01');earlier.power_mw=40
            save_event(c,later);save_event(c,earlier)
            p=dict(c.execute('SELECT * FROM projects').fetchone())
            self.assertEqual(p['last_seen'],'2026-10-02');self.assertEqual(p['latest_event_type'],'CONSTRUCTION_AUTH')
            self.assertEqual(p['power_mw'],50);self.assertEqual(p['first_seen'],'2026-09-01');c.close()

    def test_missing_reference_can_link_only_on_exact_multi_field_same_day_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=connect(str(Path(tmp)/'test.sqlite'));save_event(c,event())
            save_event(c,event(code='A1',source='AND_PUBLIC',expediente=''))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM projects').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0],2)
            save_event(c,event(code='A2',source='AND_PUBLIC',expediente='EX-OTHER-9'))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM projects').fetchone()[0],2);c.close()

    def test_legacy_repair_splits_false_group_and_preserves_source_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=connect(str(Path(tmp)/'test.sqlite'))
            save_event(c,event('Plant A','A1',expediente='INAGA 500306/01/2026/001'))
            save_event(c,event('Plant B','B1',expediente='INAGA 500306/01/2026/002'))
            keys=[r[0] for r in c.execute('SELECT project_key FROM projects')]
            c.execute('UPDATE events SET project_key=?,expediente=?',(keys[0],'INAGA'))
            c.execute('DELETE FROM projects WHERE project_key=?',(keys[1],));c.execute('UPDATE projects SET expediente=?',('INAGA',));c.commit()
            before=[tuple(r) for r in c.execute('SELECT id,title,url,raw_text,publication_date FROM events ORDER BY id')]
            report=repair_legacy_identities(c,report_dir=Path(tmp)/'reports')
            self.assertEqual(report['projects_before'],1);self.assertEqual(report['projects_after'],2)
            self.assertTrue(Path(report['backup_path']).exists())
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT id,title,url,raw_text,publication_date FROM events ORDER BY id')])
            self.assertEqual(repair_legacy_identities(c)['status'],'NOT_NEEDED')
            old=sqlite3.connect(report['backup_path']);self.assertEqual(old.execute('SELECT COUNT(*) FROM projects').fetchone()[0],1);old.close();c.close()

if __name__=='__main__':unittest.main()
