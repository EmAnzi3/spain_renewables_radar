import unittest
from datetime import date
from unittest.mock import patch

from app.collectors.andalucia_public import (
    AndaluciaPublicCollector, document_links, event_from_record, publication_date,
    relevant_record, validate_archive,
)

RONDA = {
    'id':'686479', 'publication_date':'01/10/2026', 'update_date':'2026-10-02T07:21:03.000Z',
    'title':'Anuncio por el que se somete al trámite de información pública la solicitud de declaración '
            'de utilidad pública del proyecto de la planta solar fotovoltaica denominada "PSF Ronda 3" '
            'en el término municipal de Cañete la Real (Málaga), formulada por Cobra Concesiones, S.L. '
            '(expediente CG- 870).',
    'document_type':'ANUNCIO IP DUP PUBLICADO BOE',
    'date':[{'allegations_start_date':'02/10/2026','allegations_end_date':'16/11/2026'}],
    'documents':[{'field_titulo':'RESOLUCION AAC FV', 'field_documento_p':[
        {'field_media_file':[{'uri':'/sites/default/files/2026-03/5.- CG-870 Resolucion AAC FV.pdf'}]}]}],
}

class AndaluciaPublicTests(unittest.TestCase):
    def test_observed_date_formats(self):
        self.assertEqual(publication_date('2026-10-01'), '2026-10-01')
        self.assertEqual(publication_date('01/10/2026'), '2026-10-01')
        self.assertIsNone(publication_date('31/02/2026'))
        self.assertIsNone(publication_date(None))

    def test_official_ronda_notice_does_not_infer_grant_from_attachment(self):
        e = event_from_record(RONDA)
        self.assertEqual(e.external_id,'686479')
        self.assertEqual(e.publication_date,'2026-10-01')
        self.assertEqual(e.project_name,'PSF Ronda 3')
        self.assertEqual(e.expediente,'CG-870')
        self.assertEqual(e.province,'Málaga')
        self.assertEqual(e.event_type,'PUBLIC_INFO')
        self.assertEqual(e.commercial_stage,'EARLY')
        self.assertEqual(e.ccaa,'Andalucía')
        self.assertIn('Cobra',e.promoter)
        self.assertIn('RESOLUCION AAC FV',e.raw_text)
        self.assertIsNone(e.power_mw)

    def test_missing_publication_date_not_replaced_with_update(self):
        with self.assertRaisesRegex(ValueError,'publication date'):
            event_from_record(dict(RONDA,publication_date=None))

    def test_fossil_storage_company_is_not_bess(self):
        record = dict(RONDA,title='Anuncio de Naturgy Almacenamientos Andalucia, S.A. Exp. CR-50.')
        self.assertFalse(relevant_record(record))
        self.assertIsNone(event_from_record(record))

    def test_known_snapshot_count_reconciled(self):
        self.assertEqual(validate_archive([RONDA],1), [RONDA])
        with self.assertRaisesRegex(ValueError,'count mismatch'):
            validate_archive([RONDA],2)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            validate_archive([RONDA,RONDA],2)

    def test_schema_error_not_empty_result(self):
        with self.assertRaises(ValueError):
            validate_archive({'error':'unavailable'},1)

    def test_official_document_links_preserved(self):
        links = document_links(RONDA)
        self.assertEqual(len(links),1)
        self.assertEqual(links[0]['title'],'RESOLUCION AAC FV')
        self.assertTrue(links[0]['url'].startswith('https://www.juntadeandalucia.es/sites/'))

    def test_daily_filter_uses_publication_not_update_or_allegations(self):
        collector = AndaluciaPublicCollector()
        collector._records = [RONDA]
        self.assertEqual(len(collector.collect_day(date(2026,10,1))),1)
        self.assertEqual(collector.collect_day(date(2026,10,2)),[])

if __name__ == '__main__':
    unittest.main()
