"""Synthetic DOM fixtures modeled on the official Xunta probe; no live tests here."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.galicia_archive import (
    ARCHIVES, GaliciaArchive, act_date, official_page, parse_detail,
    parse_index, reconcile, source_id, write_outputs,
)
from datetime import date

ROOT = ARCHIVES['consultations']
TITLE = ('ACUERDO de 20 de abril de 2026, por el que se someten a información pública '
         'las solicitudes del proyecto de almacenamiento eléctrico Ebro Energy O Rosal.')
INDEX = ("<html><p>Tiene disponible para consulta 1 expedientes</p>"
         "<a class='contedor__env__resultado' href='?content=expediente_0058.xml'>"+TITLE+"</a></html>")
DETAIL = ("<html><h2>"+TITLE+"</h2><p>Estado actual: cerrada a fase de envío de sugerencias</p>"
          "<p>Plazo en el que estuvo abierta la consulta: 27/04/2026 - 09/06/2026</p>"
          "<a href='https://www.xunta.gal/dog/Publicados/2026/20260427/AnuncioG0760-210426-0001_es.pdf'>PDF Anuncio DOG</a>"
          "<a href='https://descargas.xunta.es/test/project.zip'>Proyecto</a></html>")


def row():
    return parse_index(INDEX, ROOT, 'consultations')[1][0]


def snapshot(rows):
    return {'source':'XUNTA_PUBLIC','complete':True,'records':rows,'archives':{'consultations':{'records':len(rows),'details':len(rows),'pages':1}}}


class GaliciaArchiveTests(unittest.TestCase):
    def test_original_ids_are_namespaced_not_merged_by_short_code(self):
        a = parse_index(INDEX, ROOT, 'consultations')[1][0]
        b = parse_index(INDEX, ROOT, 'authorizations')[1][0]
        self.assertEqual(a['external_id'],b['external_id'])
        self.assertNotEqual(a['record_key'],b['record_key'])

    def test_actual_act_dates_bilingual_and_unknown(self):
        self.assertEqual(act_date(TITLE),'2026-04-20')
        self.assertEqual(act_date('ACORDO do 6 de marzo de 2026, instalación'),'2026-03-06')
        self.assertIsNone(act_date('Parque eólico presentado en 2026'))
        with self.assertRaises(ValueError):act_date('ACUERDO de 31 de febrero de 2026')

    def test_closed_consultation_is_not_a_blocked_or_authorized_project(self):
        record = parse_detail(DETAIL,row())
        self.assertEqual(record['consultation_start'],'2026-04-27')
        self.assertEqual(record['consultation_end'],'2026-06-09')
        self.assertIsNone(record['web_publication_date'])
        for k in ('commercial_stage','event_type','power_mw','promoter','epc'):
            self.assertNotIn(k,record)

    def test_linked_dog_date_is_not_verified_publication(self):
        record = parse_detail(DETAIL,row())
        doc = next(x for x in record['documents'] if x['dog_date_from_link'])
        self.assertEqual(doc['dog_date_from_link'],'2026-04-27')
        self.assertFalse(doc['publication_verified'])
        self.assertFalse(doc['document_downloaded'])
        self.assertIn('cerrada',record['raw_text'])

    def test_index_errors_are_not_valid_zero_results(self):
        for text in ('<html>Service unavailable</html>', INDEX.replace('1 expedientes','2 expedientes').split('<a')[0]+'</html>'):
            with self.assertRaises(ValueError):parse_index(text,ROOT,'consultations')
        duplicate = INDEX.replace('</html>',INDEX+'</html>')
        with self.assertRaises(ValueError):parse_index(duplicate,ROOT,'consultations')

    def test_foreign_url_or_ambiguous_identity_rejected(self):
        for url in ('http://economia.xunta.gal/', 'https://economia.xunta.gal.evil.test/',
                    'https://economia.xunta.gal@evil.test/', 'https://economia.xunta.gal:444/es/transparencia/informacion-publica/'):
            with self.assertRaises(ValueError):official_page(url)
        with self.assertRaises(ValueError):source_id(ROOT+'?content=expediente_1.xml&content=expediente_2.xml')

    def test_detail_mismatch_is_not_silently_skipped(self):
        with self.assertRaises(ValueError):parse_detail(DETAIL.replace(TITLE,'Other project'),row())

    def test_initial_inventory_is_baseline_not_new_projects(self):
        current = snapshot([parse_detail(DETAIL,row())])
        changes = reconcile(None,current)
        self.assertEqual(changes['mode'],'BASELINE')
        self.assertEqual(changes['baseline_records'],1)
        self.assertEqual(changes['newly_observed'],[])

    def test_replay_ignores_runtime_and_tracks_semantic_changes(self):
        a = snapshot([parse_detail(DETAIL,row())]);b = copy.deepcopy(a)
        b['retrieved_at']='2099-01-01';b['records'][0]['raw_text']+=' Updated page clock'
        self.assertEqual(reconcile(a,b)['changed'],[])
        b['records'][0]['consultation_end']='2026-06-10'
        self.assertEqual(reconcile(a,b)['changed'],[row()['record_key']])

    def test_disappearing_record_is_not_inferred_withdrawal(self):
        before=snapshot([parse_detail(DETAIL,row())]);after=snapshot([])
        changes = reconcile(before,after)
        self.assertEqual(changes['not_seen'],[row()['record_key']])
        self.assertNotIn('WITHDRAWN',str(changes))

    def test_incomplete_snapshot_cannot_replace_baseline(self):
        current = snapshot([]);current['complete']=False
        with self.assertRaises(ValueError):reconcile(None,current)

    def test_redirect_destination_checked_before_request(self):
        session=Mock();response=Mock(status_code=302,headers={'Location':'https://evil.test/'})
        session.get.return_value=response
        with tempfile.TemporaryDirectory() as tmp:
            collector=GaliciaArchive(tmp,session=session,pause=0)
            with self.assertRaises(ValueError):collector.get(ROOT)
        self.assertEqual(session.get.call_count,1)

    def test_backfill_window_never_certifies_missing_web_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap=snapshot([parse_detail(DETAIL,row())])
            summary=write_outputs(snap,reconcile(None,snap),tmp,date(2026,10,3))
            self.assertEqual(summary['dated_acts_in_window'],0)
            self.assertFalse(summary['historical_web_backfill_certified'])
            self.assertEqual(summary['project_events_created'],0)
            self.assertEqual(summary['unknown_web_publication_dates'],1)
            self.assertIn('NO_RECENT_DATED_ACTS_IN_ARCHIVE',summary['source_warnings'])
            self.assertTrue((Path(tmp)/'index.html').exists())


if __name__=='__main__':unittest.main()
