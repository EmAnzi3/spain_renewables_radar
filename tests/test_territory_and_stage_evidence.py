import sqlite3,tempfile,unittest
from pathlib import Path
from app.db import connect
from app.parser import ParsedEvent,parse_event
from app.store import save_event
from app.territory import PROVINCE_CCAA,normalize_row
from app.lifecycle import dia_outcome,commercial_stage
from app.dia_repair import repair_unfavourable_dia
from app.web_portal import stage_evidence

NEG=("En consecuencia, esta Dirección General, a la vista de la propuesta de la Subdirección General de Evaluación Ambiental, "
     "formula declaración de impacto ambiental desfavorable a la realización del proyecto «Parque Eólico Las Viñas de 85,18 MW»")
POS=("formula declaración de impacto ambiental favorable a la realización del proyecto; cita otro proyecto con "
     "declaración de impacto ambiental desfavorable emitida mediante Resolución de 29 de agosto de 2025")
TITLE="Resolución de 18 de octubre de 2024, de la Dirección General de Calidad y Evaluación Ambiental, por la que se formula declaración de impacto ambiental del proyecto «Parque eólico Las Viñas, de 85,18 MW»"

class TerritoryTests(unittest.TestCase):
    def test_official_hierarchy_is_complete(self):
        self.assertEqual(len(PROVINCE_CCAA),52);self.assertEqual(len(set(PROVINCE_CCAA.values())),19)
    def test_spelling_variants_and_derived_region(self):
        r={'province':'Castelló','provinces':['Castelló'],'ccaa':None};self.assertEqual(normalize_row(r),[])
        self.assertEqual((r['province'],r['ccaa']),('Castellón','Comunitat Valenciana'))
        r={'province':'Lleida','provinces':[],'ccaa':'Catalunya'};normalize_row(r);self.assertEqual(r['ccaa'],'Cataluña')
    def test_conflict_keeps_source_region_and_withholds_province(self):
        r={'province':'Illes Balears','provinces':['Illes Balears'],'ccaa':'Cataluña'};flags=normalize_row(r)
        self.assertEqual((r['province'],r['provinces'],r['ccaa']),(None,[],'Cataluña'))
        self.assertEqual(flags[0]['code'],'PROVINCE_OUTSIDE_SOURCE_CCAA')
    def test_multi_province_inside_one_region(self):
        r={'province':None,'provinces':['Soria','Burgos'],'ccaa':None};normalize_row(r)
        self.assertEqual((r['province'],r['ccaa']),(None,'Castilla y León'))

class DIAOutcomeTests(unittest.TestCase):
    def test_operative_clause_decides_not_citations(self):
        self.assertEqual(dia_outcome(NEG),'DIA_UNFAVOURABLE');self.assertEqual(dia_outcome(POS),'DIA')
        self.assertEqual(commercial_stage('DIA_UNFAVOURABLE'),'BLOCKED')
    def test_new_unfavourable_dia_is_blocked(self):
        e=parse_event(source_code='BOE',external_id='BOE-A-2024-22417',publication_date='2024-10-30',title=TITLE,url='https://www.boe.es/x',raw_text=NEG)
        self.assertEqual((e.event_type,e.commercial_stage),('DIA_UNFAVOURABLE','BLOCKED'))
    def test_stored_dia_is_repaired_with_audit_and_original_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            c=connect(str(Path(td)/'db.sqlite'))
            save_event(c,ParsedEvent(source_code='BOE',external_id='X',publication_date='2024-10-30',title=TITLE,url='https://www.boe.es/x',
                raw_text=NEG,technology='WIND',power_mw=85.18,project_name='Las Viñas',promoter=None,expediente=None,province='Palencia',
                ccaa='Castilla y León',event_type='DIA',commercial_stage='PERMITTING',project_key='k'))
            before=c.execute('SELECT title,raw_text,url,publication_date FROM events').fetchone()[:]
            self.assertEqual(repair_unfavourable_dia(c)['reclassified_events'],1)
            self.assertEqual(c.execute('SELECT commercial_stage FROM projects').fetchone()[0],'BLOCKED')
            self.assertEqual(c.execute('SELECT title,raw_text,url,publication_date FROM events').fetchone()[:],before)
            self.assertEqual(c.execute('SELECT previous_project_stage FROM dia_outcome_repairs').fetchone()[0],'PERMITTING')
            self.assertEqual(repair_unfavourable_dia(c)['reclassified_events'],0);c.close()

class StageEvidenceTests(unittest.TestCase):
    def ev(self,t,d):return {'event_type':t,'date':d,'source_code':'BOE','external_id':t+d,'url':'https://www.boe.es/'+t,'title':t}
    def test_highest_stage_act_newest_first(self):
        events=[self.ev('PUBLIC_INFO','2026-05-01'),self.ev('CONSTRUCTION_AUTH','2026-02-01'),self.ev('PRIOR_AUTH','2025-10-01')]
        self.assertEqual(stage_evidence(events,'AUTHORIZED')['event_type'],'CONSTRUCTION_AUTH')
        events=[self.ev('EXPROPRIATION','2026-06-01')]+events
        self.assertEqual(stage_evidence(events,'PRECONSTRUCTION')['event_type'],'EXPROPRIATION')
    def test_blocked_points_to_blocking_act(self):
        events=[self.ev('CONSTRUCTION_AUTH','2026-02-01'),self.ev('DIA_UNFAVOURABLE','2025-01-01')]
        self.assertEqual(stage_evidence(events,'BLOCKED')['event_type'],'DIA_UNFAVOURABLE')
