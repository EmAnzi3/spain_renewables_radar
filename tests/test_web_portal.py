import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app.db import connect
from app.parser import ParsedEvent
from app.store import save_event
from app.web_portal import write_portal
from app.valencian_alternatives import mpt_inventory,from_probe

class PortalTests(unittest.TestCase):
    def test_read_only_render_preserves_originals_and_escapes_script_end(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=root/'demo.sqlite';c=connect(str(db))
            e=ParsedEvent(source_code='BOE',external_id='fixture',publication_date='2026-10-01',title='Progetto di prova',
                url='https://www.boe.es/fixture',raw_text='</script><script>window.INJECTED=true</script>',project_name='Demo',
                technology='PV',power_mw=5.0,promoter=None,expediente='DEMO-01',province='Madrid',ccaa='Madrid',
                event_type='PUBLIC_INFO',commercial_stage='EARLY',project_key='demo')
            save_event(c,e);before=list(c.iterdump());c.close()
            receipt=write_portal(db,root/'site',{'state':'PARTIAL','sources':{'BOE':{'status':'UNAVAILABLE'}},'full_certification':False})
            text=(root/'site/index.html').read_text();data=json.loads((root/'site/data.json').read_text())
            self.assertNotIn(e.raw_text,text);self.assertIn('\\u003c/script',text)
            self.assertEqual(data['records'][0]['events'][0]['raw_text'],e.raw_text)
            self.assertEqual(receipt['projects'],1);self.assertFalse(receipt['full_certification'])
            with sqlite3.connect(db) as c:self.assertEqual(list(c.iterdump()),before)
            self.assertNotIn('<script src=',text)
    def test_structural_quality_error_is_not_published(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=root/'demo.sqlite';connect(str(db)).close()
            with patch('app.web_portal.write_quality_issues',return_value=([{'severity':'ERROR'}],None,None)):
                with self.assertRaises(ValueError):write_portal(db,root/'site',{'state':'PARTIAL'})
            self.assertFalse((root/'site/index.html').exists())

class AlternativeTests(unittest.TestCase):
    def fixture(self):
        return '''<html><div><h2>Fotovoltaica in another region</h2></div><section class="dnt-vertical-menu-content"><h1>Procedimientos de información pública</h1><div id="title-province"><h2 class="cmp-title__text">ALICANTE</h2></div><div id="title-demo"><h2 class="cmp-title__text">PLANTA FOTOVOLTAICA DEMO</h2></div><div class="cmp-text"><p>Expediente y texto original</p><a href="https://almacen.redsara.es/demo">Documentos</a></div></section></html>'''.encode()
    def test_navigation_is_excluded_and_web_dates_are_unknown(self):
        out=mpt_inventory(self.fixture(),'https://mptmd.gob.es/portal/example')
        self.assertEqual(len(out),1);self.assertEqual(out[0]['province_section'],'ALICANTE')
        self.assertIsNone(out[0]['publication_date']);self.assertIsNone(out[0]['power_mw'])
        self.assertIsNone(out[0]['project_name']);self.assertEqual(out[0]['database_events_created'],0)
        self.assertEqual(out[0]['document_links'][0]['label'],'Documentos')
    def test_wrong_page_or_ambiguous_sections_fail(self):
        for raw in [self.fixture().replace(b'Procedimientos de informaci',b'Otra p'),self.fixture()+self.fixture()]:
            with self.assertRaises(ValueError):mpt_inventory(raw,'https://mptmd.gob.es/example')
    def test_unknown_source_host_fails(self):
        with self.assertRaises(ValueError):mpt_inventory(self.fixture(),'https://elsewhere.invalid')
    def test_artifact_original_is_verified_not_only_probe_success_flag(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'raw').mkdir();raw=self.fixture();sha=hashlib.sha256(raw).hexdigest()
            (root/'raw'/f'{sha}.bin').write_bytes(raw)
            row={'source_code':'MPT_VALENCIA','access':'RESPONSE_ACQUIRED','final_url':'https://mptmd.gob.es/x',
                 'receipts':[{'sha256':sha,'bytes':len(raw),'status':200,'retrieved_at':'2026-10-06T08:17:00Z'}]}
            (root/'probe.json').write_text(json.dumps([row]));self.assertEqual(len(from_probe(root)[0]['lead_links']),1)
            (root/'raw'/f'{sha}.bin').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):from_probe(root)
