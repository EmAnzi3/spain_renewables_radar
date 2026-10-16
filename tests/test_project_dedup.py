import tempfile,unittest
from dataclasses import replace
from pathlib import Path
from app.db import connect
from app.parser import ParsedEvent,build_project_key
from app.store import save_event
from app.project_dedup import merge_duplicate_projects,promoters_compatible,files_compatible

def ev(ident,date,*,name='Sextante Solar',mw=105.36,prov='Toledo',exp=None,prom=None,stage=('PUBLIC_INFO','EARLY'),tech='PV'):
    return ParsedEvent(source_code='BOE',external_id=ident,publication_date=date,title='t '+ident,url='https://www.boe.es/'+ident,raw_text='x',
        technology=tech,power_mw=mw,project_name=name,promoter=prom,expediente=exp,province=prov,ccaa=None,event_type=stage[0],
        commercial_stage=stage[1],project_key=build_project_key(name,tech,prov,ident,exp))

class DedupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.c=connect(str(Path(self.tmp.name)/'db.sqlite'))
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def cards(self):return self.c.execute('SELECT count(*) FROM projects').fetchone()[0]
    def test_same_plant_with_and_without_file_number_becomes_one_card(self):
        save_event(self.c,ev('A','2025-01-10',exp='PFot-248',prom='COVADONGA SOLAR, S.L.U.'))
        save_event(self.c,ev('B','2025-06-02',prov=None,stage=('CONSTRUCTION_AUTH','AUTHORIZED')))
        self.assertEqual(self.cards(),2)
        self.assertEqual(merge_duplicate_projects(self.c)['merged_cards'],1)
        p=self.c.execute('SELECT * FROM projects').fetchone()
        self.assertEqual((p['expediente'],p['province'],p['commercial_stage']),('PFot-248','Toledo','AUTHORIZED'))
        self.assertEqual(self.c.execute('SELECT count(*) FROM events WHERE project_key=?',(p['project_key'],)).fetchone()[0],2)
        self.assertEqual(merge_duplicate_projects(self.c)['merged_cards'],0)
        # a later act carrying the old key lands on the merged card through the alias
        later=ev('C','2025-09-01',prov=None,stage=('EXPROPRIATION','PRECONSTRUCTION'))
        save_event(self.c,later);self.assertEqual(self.cards(),1)
    def test_conflicts_stay_apart(self):
        save_event(self.c,ev('A','2025-01-10',name='Bonastre 4',mw=48.8,prov='Teruel'))
        save_event(self.c,ev('B','2025-02-10',name='Bonastre 4',mw=48.8,prov='Zaragoza'))
        save_event(self.c,ev('C','2025-01-10',name='Planta X',mw=10.32,prov='Zaragoza',exp='G-Z-2023/030'))
        save_event(self.c,ev('D','2025-01-11',name='Planta X',mw=10.32,prov='Zaragoza',exp='G-Z-2023/026'))
        save_event(self.c,ev('E','2025-01-10',name='Solar Uno',mw=5.0,prom='Alfa Energía, SL'))
        save_event(self.c,ev('F','2025-03-10',name='Solar Uno',mw=5.0,prom='Beta Renovables Iberia, SLU'))
        save_event(self.c,ev('G','2025-01-10',name='Solar Dos',mw=5.0))
        save_event(self.c,ev('H','2025-03-10',name='Solar Dos',mw=5.5))
        self.assertEqual(merge_duplicate_projects(self.c)['merged_cards'],0)
    def test_parallel_administrations_and_notation_are_compatible(self):
        self.assertTrue(files_compatible(['INAGA 500806/01/2022/07032','G-T-2022-023']))
        self.assertTrue(files_compatible(['G-Z-251/2020','G-Z-2020/251']))
        self.assertFalse(files_compatible(['G-Z-2023/030','G-Z-2023/026']))
        self.assertTrue(promoters_compatible(['Arcesolar Energía, SL','Arcesolar Energía, SL (Número de identificación B-123)']))
        self.assertFalse(promoters_compatible(['Alfa Energía, SL','Beta Renovables Iberia, SLU']))
    def test_heading_fragments_are_never_a_merge_basis(self):
        save_event(self.c,ev('A','2025-01-10',name='de 1',mw=1.5,exp='40/2024'))
        save_event(self.c,ev('B','2025-02-10',name='de 1',mw=1.5,exp='EIAS/2024/SA/012'))
        self.assertEqual(merge_duplicate_projects(self.c)['merged_cards'],0)
