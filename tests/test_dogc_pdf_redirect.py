import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from scripts.acquire_dogc_bodies import BodyClient, validated_pdf_redirect

ORIGIN='https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?documentId=1&type=01&language=ca_ES'
CANDIDATE={'source_url':ORIGIN,'document_id':'1','edition':'9747','base_edition':'9747','publication_date':'2026-09-08'}
TARGET='https://portaldogc.gencat.cat/utilsEADOP/PDF/9747/1234567.pdf'

class RedirectTests(unittest.TestCase):
    def test_source_provided_official_same_edition_target(self):
        self.assertEqual(validated_pdf_redirect(ORIGIN,TARGET,CANDIDATE),TARGET)
        self.assertEqual(validated_pdf_redirect(ORIGIN,'/utilsEADOP/PDF/9747/1234567.pdf',CANDIDATE),TARGET)

    def test_wrong_edition_domain_scheme_path_and_query_rejected(self):
        for location in [TARGET.replace('9747','9748'),TARGET.replace('portaldogc.gencat.cat','other.invalid'),
                         TARGET.replace('https:','http:'),TARGET+'?token=wrong',TARGET.replace('/PDF/','/other/'),None]:
            with self.assertRaises(ValueError):validated_pdf_redirect(ORIGIN,location,CANDIDATE)

    def response(self,status,location=None):
        r=Mock();r.status_code=status;r.headers={'Location':location};r.iter_content.return_value=[b'%PDF-1.7\nbody\n%%EOF']
        return r

    def test_original_and_final_url_are_audited(self):
        with tempfile.TemporaryDirectory() as td:
            client=BodyClient(Path(td));first=self.response(302,TARGET);last=self.response(200)
            client.session.get=Mock(side_effect=[first,last])
            _,meta=client.get_pdf(CANDIDATE)
            self.assertEqual(meta['url'],ORIGIN);self.assertEqual(meta['final_url'],TARGET)
            self.assertEqual(meta['redirect']['location'],TARGET)
            self.assertFalse(client.session.get.call_args.kwargs['allow_redirects'])
            self.assertEqual(client.session.get.call_count,2)

    def test_foreign_redirect_is_rejected_before_contact(self):
        with tempfile.TemporaryDirectory() as td:
            client=BodyClient(Path(td));client.session.get=Mock(return_value=self.response(302,'https://other.invalid/x.pdf'))
            with self.assertRaises(ValueError):client.get_pdf(CANDIDATE)
            self.assertEqual(client.session.get.call_count,1)

    def test_redirect_loop_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            client=BodyClient(Path(td));client.session.get=Mock(side_effect=[self.response(302,TARGET),self.response(302,TARGET)])
            with self.assertRaises(ValueError):client.get_pdf(CANDIDATE)
            self.assertEqual(client.session.get.call_count,2)
