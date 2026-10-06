import hashlib,json,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from app.bocyl_storage import battery_projection,project_event,repair_database,source_fingerprint,LEGACY_HASH,LEGACY_KEY
from app.parser import parse_event
from app.db import connect
from app.store import save_event
FIXTURE=json.loads((Path(__file__).parent/'fixtures/bocyl_cisterniga_review.json').read_text())
def original_event():
    return parse_event(**{k:FIXTURE[k] for k in ('source_code','external_id','publication_date','title','url','raw_text')})
class ProjectionTests(unittest.TestCase):
    def test_reviewed_original_is_frozen(self):
        self.assertEqual(hashlib.sha256(FIXTURE['raw_text'].encode()).hexdigest(),LEGACY_HASH)
    def test_new_battery_not_existing_pv_or_network_point(self):
        event=original_event();got=project_event(event)
        self.assertEqual((got.project_name,got.technology,got.power_mw),('BESS Cistérniga','BESS',2.1))
        self.assertEqual(got.promoter,'Soluciones de Ingeniería Industrial II, S.L.')
        for field in ('source_code','external_id','publication_date','raw_text','title','url','event_type','commercial_stage','project_key'):
            self.assertEqual(getattr(event,field),getattr(got,field))
    def test_no_applicant_does_not_fall_back_to_distributor(self):
        raw='\n'.join(l for l in FIXTURE['raw_text'].splitlines() if not l.startswith('Peticionario'))
        self.assertIsNone(battery_projection(FIXTURE['title'],raw)['promoter'])
    def test_missing_installed_scope_does_not_use_nominal_energy_or_apparent_power(self):
        raw='\n'.join(l for l in FIXTURE['raw_text'].splitlines() if not l.startswith('Potencia instalada'))
        self.assertIsNone(battery_projection(FIXTURE['title'],raw)['power_mw'])
    def test_multiple_applicants_or_installed_scopes_remain_unknown(self):
        raw=FIXTURE['raw_text']+'\nPeticionario Other Company, S.L., con domicilio en Madrid.\nPotencia instalada 9 MW'
        got=battery_projection(FIXTURE['title'],raw);self.assertIsNone(got['promoter']);self.assertIsNone(got['power_mw'])
    def test_rule_is_not_a_lookup_by_name_id_or_company(self):
        event=original_event();changed=replace(event,external_id='DIFFERENT',title=event.title.replace('BESS Cistérniga','Otra batería'),raw_text=event.raw_text.replace('Soluciones de Ingeniería Industrial II','Otra Sociedad').replace('2.100 kW','4.200 kW'))
        got=project_event(changed);self.assertEqual(got.project_name,'Otra batería');self.assertEqual(got.power_mw,4.2);self.assertIn('Otra Sociedad',got.promoter)
    def test_other_sources_or_unscoped_titles_are_unchanged(self):
        event=original_event()
        self.assertEqual(project_event(replace(event,source_code='DOCM')),replace(event,source_code='DOCM'))
        self.assertEqual(project_event(replace(event,title='Existing photovoltaic plant')),replace(event,title='Existing photovoltaic plant'))
class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.c=connect(str(self.root/'db.sqlite'));save_event(self.c,original_event())
    def tearDown(self):self.c.close();self.temp.cleanup()
    def test_only_reviewed_projection_changes_with_backup_and_idempotence(self):
        before=source_fingerprint(self.c);result=repair_database(self.c,self.root/'audit')
        self.assertEqual(result['changed_projects'],1);self.assertTrue(Path(result['backup_path']).exists())
        row=self.c.execute('SELECT * FROM projects WHERE project_key=?',(LEGACY_KEY,)).fetchone()
        self.assertEqual((row['project_name'],row['technology'],row['promoter']),('BESS Cistérniga','BESS','Soluciones de Ingeniería Industrial II, S.L.'))
        self.assertEqual(source_fingerprint(self.c),before)
        self.assertEqual(repair_database(self.c,self.root/'audit')['changed_projects'],0)
    def test_changed_original_is_rejected(self):
        self.c.execute("UPDATE events SET raw_text=raw_text||' altered'");self.c.commit()
        with self.assertRaises(ValueError):repair_database(self.c,self.root/'audit')
    def test_shared_project_not_rewritten(self):
        save_event(self.c,replace(original_event(),external_id='SECOND',publication_date='2026-10-04'))
        with self.assertRaises(ValueError):repair_database(self.c,self.root/'audit')
    def test_fresh_correct_projection_needs_no_legacy_repair(self):
        self.c.execute('DELETE FROM events');self.c.execute('DELETE FROM projects');self.c.commit()
        save_event(self.c,project_event(original_event()))
        self.assertEqual(repair_database(self.c,self.root/'audit')['changed_projects'],0)
    def test_invariant_failure_rolls_back_projection(self):
        before=dict(self.c.execute('SELECT * FROM projects').fetchone())
        with patch('app.bocyl_storage.source_fingerprint',side_effect=['before','changed']):
            with self.assertRaises(ValueError):repair_database(self.c,self.root/'audit')
        self.assertEqual(dict(self.c.execute('SELECT * FROM projects').fetchone()),before)
