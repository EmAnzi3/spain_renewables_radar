import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import requests
from app.bocyl_identity import repair_bocyl_external_ids
from app.collectors.bocyl import BOCYLCollector
from app.db import connect
from app.parser import parse_event
from app.store import save_event

class BOCYLIdentityTests(unittest.TestCase):
    def test_dispositions_in_same_edition_are_not_deduplicated(self):
        rows=[{'enlace_fichero_xml':f'https://bocyl.jcyl.es/boletines/2026/09/14/xml/BOCYL-D-14092026-178-{i}.xml'} for i in (17,15)]
        self.assertEqual([BOCYLCollector._external_id(r) for r in rows],['BOCYL-D-14092026-178-17','BOCYL-D-14092026-178-15'])

    def test_xml_network_failure_uses_published_html_and_not_summary(self):
        collector=BOCYLCollector()
        row={'enlace_fichero_xml':'https://bocyl.jcyl.es/17.xml','enlace_fichero_html':'https://bocyl.jcyl.es/17.do','titulo':'Summary'}
        with patch.object(collector,'_get_text',side_effect=[requests.Timeout('timeout'),'<html><body>Summary '+('Official detailed text '*10)+'</body></html>']):
            text,url=collector._detail_text(row)
            self.assertIn('Official detailed text',text);self.assertEqual(url,row['enlace_fichero_html'])
        with patch.object(collector,'_get_text',side_effect=requests.Timeout('timeout')):
            with self.assertRaisesRegex(RuntimeError,'unavailable'):collector._detail_text(row)

    def test_html_maintenance_page_is_not_valid_detail(self):
        collector=BOCYLCollector()
        row={'enlace_fichero_html':'https://bocyl.jcyl.es/test.do','titulo':'Expected official disposition title'}
        with patch.object(collector,'_get_text',return_value='<html><body>'+('Temporarily unavailable '*12)+'</body></html>'):
            with self.assertRaisesRegex(RuntimeError,'expected official title'):
                collector._detail_text(row)

    def test_old_identity_is_repaired_from_source_without_payload_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            con=connect(str(Path(tmp)/'test.sqlite'))
            title='Información pública del parque fotovoltaico «La Loma» de 10 MW en Valle de Santibáñez (Burgos).'
            e=parse_event(source_code='BOCYL',external_id='BOCYL-D-14092026-178',publication_date='2026-09-14',title=title,
                          url='http://bocyl.jcyl.es/html/2026/09/14/html/BOCYL-D-14092026-178-17.do',raw_text=title)
            save_event(con,e);before=dict(con.execute('select * from events').fetchone())
            result=repair_bocyl_external_ids(con)
            self.assertEqual(result['changed'],1);self.assertTrue(Path(result['backup_path']).exists())
            after=dict(con.execute('select * from events').fetchone())
            self.assertEqual(after,dict(before,external_id='BOCYL-D-14092026-178-17'))
            audit=con.execute('select original_payload_json from source_identity_repair').fetchone()[0]
            self.assertEqual(json.loads(audit),before)
            e.external_id=after['external_id'];self.assertEqual(save_event(con,e),(False,False))
            self.assertEqual(repair_bocyl_external_ids(con),{'changed':0});con.close()

if __name__=='__main__':unittest.main()
