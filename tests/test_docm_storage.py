import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import date

from app.db import connect
from app.parser import parse_event
from app.store import save_event
from app.docm_storage import (storage_evidence,project_storage,repair_and_record,validate_docm_storage,
                              source_fingerprint,REVIEWED_RAW_SHA)
from app.enrichment.ine_municipalities import Municipality, municipalities_in_text, enrich_missing_project_geography
from app.collectors.docm import DOCMCollector

RAW=Path('tests/fixtures/docm_almagro_storage.txt').read_text(encoding='utf-8').strip()
TITLE=next(line for line in RAW.splitlines() if line.startswith('Anuncio de'))
URL='https://docm.jccm.es/docm/verArchivoHtml.do?ruta=2026%2F10%2F05%2Fhtml%2F2026_7037.html&tipo=rutaDocm'


def event(raw=RAW,title=TITLE,identity='DOCM-2026-7037'):
    return parse_event(source_code='DOCM',external_id=identity,publication_date='2026-10-05',title=title,url=URL,raw_text=raw)


class StorageTests(unittest.TestCase):
    def test_frozen_original_matches_reviewed_hash(self):
        self.assertEqual(hashlib.sha256(RAW.encode()).hexdigest(),REVIEWED_RAW_SHA)

    def test_battery_name_power_and_scope_not_existing_pv(self):
        e=project_storage(event())
        self.assertEqual((e.project_name,e.technology,e.power_mw),('BESS Almagro I','BESS',7.2))
        self.assertEqual((e.event_type,e.commercial_stage),('PUBLIC_INFO','EARLY'))
        self.assertEqual(e.expediente,'13270209226')
        self.assertEqual(e.project_key,event().project_key)

    def test_source_text_and_dates_are_not_modified(self):
        old=event();new=project_storage(old)
        for k in ('source_code','external_id','publication_date','title','url','raw_text','promoter','expediente','event_type','commercial_stage'):
            self.assertEqual(getattr(old,k),getattr(new,k))
        self.assertEqual(old.power_mw,7.4)

    def test_original_quantity_spans_no_mwh_or_kva_conversion(self):
        evidence=storage_evidence(TITLE,RAW)
        self.assertFalse(evidence['quantity_aggregation_performed'])
        self.assertEqual({q['quote'] for q in evidence['source_quantities']},
                         {'7,4 MW','5,016 MWh','3600 kVA','7,2 MW','8 MVA','14,6 MW','6.690.000 W'})
        for span in evidence['source_quantities']+[evidence['power_evidence']]:
            self.assertEqual(RAW[span['start']:span['end']],span['quote'])

    def test_other_name_id_and_power_use_rules_not_case_lookup(self):
        e=project_storage(event(raw=RAW.replace('Almagro I','Demo II').replace('7,2 MW','9,6 MW'),
                              title=TITLE.replace('Almagro I','Demo II'),identity='DOCM-2026-9999'))
        self.assertEqual((e.project_name,e.power_mw),('BESS Demo II',9.6))

    def test_missing_scope_total_never_falls_back_to_existing_pv(self):
        e=project_storage(event(raw=RAW.replace('(potencia instalada total de 7,2 MW)','')))
        self.assertIsNone(e.power_mw)

    def test_mwh_and_apparent_power_cannot_be_scalar_mw(self):
        for unit in ('MWh','kVA','MVA'):
            e=project_storage(event(raw=RAW.replace('(potencia instalada total de 7,2 MW)',f'(potencia instalada total de 7,2 {unit})')))
            self.assertIsNone(e.power_mw)

    def test_explicit_kw_can_be_converted(self):
        e=project_storage(event(raw=RAW.replace('7,2 MW','7200 kW')))
        self.assertEqual(e.power_mw,7.2)

    def test_conflicting_totals_are_not_resolved(self):
        raw=RAW.replace('(potencia instalada total de 7,2 MW)','(potencia instalada total de 7,2 MW) (potencia instalada total de 8 MW)')
        result=storage_evidence(TITLE,raw)
        self.assertIsNone(result['power_mw'])
        self.assertIn('DOCM_BATTERY_POWER_CONFLICT',[f['code'] for f in result['quality_flags']])

    def test_duplicate_scope_is_ambiguous(self):
        result=storage_evidence(TITLE,RAW+'\n'+RAW)
        self.assertIsNone(result['power_mw']);self.assertIsNone(result['project_name'])

    def test_bodyless_candidate_keeps_mw_unknown(self):
        self.assertIsNone(project_storage(event(raw=TITLE)).power_mw)

    def test_historical_and_out_of_scope_totals_not_selected(self):
        raw=RAW.replace('(potencia instalada total de 7,2 MW)','')+'\n(potencia instalada total de 7,2 MW)'
        self.assertIsNone(project_storage(event(raw=raw)).power_mw)

    def test_unrelated_source_or_pv_unchanged(self):
        e=event(title='Planta fotovoltaica Demo de 7,4 MW')
        self.assertIs(project_storage(e),e)
        e=event();e.source_code='BOE'
        self.assertIs(project_storage(e),e)

    def test_singular_and_plural_municipal_scope(self):
        catalog=[Municipality('Almagro','13013','Ciudad Real','Castilla-La Mancha')]
        for text in [RAW,'Término municipal de Almagro.','Términos municipales de Almagro.']:
            self.assertEqual(municipalities_in_text(text,catalog,'Castilla-La Mancha'),catalog)
        self.assertEqual(municipalities_in_text('Domicilio: Almagro.',catalog),[])

    def test_live_collector_path_uses_scoped_projection(self):
        collector=DOCMCollector();item={'external_id':'DOCM-2026-7037','title':TITLE,'detail_url':URL,'pdf_url':'unused'}
        with patch.object(collector,'_get',side_effect=['summary','<div>'+RAW.replace('\n','<br>')+'</div>']),patch.object(collector,'parse_summary_html',return_value=[item]):
            rows=collector.collect_day(date(2026,10,5))
        self.assertEqual((rows[0].project_name,rows[0].power_mw),('BESS Almagro I',7.2))
        collector.session.close()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.conn=connect(str(self.root/'db.sqlite'))
    def tearDown(self):
        self.conn.close();self.tmp.cleanup()
    def run_repair(self):
        return repair_and_record(self.conn,str(self.root/'repair'))

    def test_existing_wrong_record_is_backed_up_corrected_and_idempotent(self):
        save_event(self.conn,event());before=source_fingerprint(self.conn)
        result=self.run_repair()
        self.assertEqual(result['corrected_events'],1);self.assertTrue(Path(result['backup_path']).is_file())
        self.assertEqual(before,source_fingerprint(self.conn))
        p=self.conn.execute('SELECT * FROM projects').fetchone()
        self.assertEqual((p['project_name'],p['power_mw'],p['technology']),('BESS Almagro I',7.2,'BESS'))
        self.assertEqual(self.run_repair()['corrected_events'],0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM docm_projection_repairs').fetchone()[0],1)
        self.assertEqual(validate_docm_storage(self.conn)['source_scoped_events'],1)

    def test_new_correct_event_is_not_migrated(self):
        save_event(self.conn,project_storage(event()))
        self.assertEqual(self.run_repair()['corrected_events'],0)
        self.assertEqual(validate_docm_storage(self.conn)['source_scoped_events'],1)
        self.assertEqual(save_event(self.conn,project_storage(event())),(False,False))

    def test_modified_original_or_other_prior_projection_stops(self):
        save_event(self.conn,event(raw=RAW+' altered'))
        with self.assertRaises(ValueError):self.run_repair()
        self.assertEqual(self.conn.execute('SELECT power_mw FROM events').fetchone()[0],7.4)

    def test_shared_project_is_not_rebuilt_arbitrarily(self):
        save_event(self.conn,event());save_event(self.conn,event(identity='DOCM-2026-8888'))
        with self.assertRaises(ValueError):self.run_repair()
        self.assertEqual(self.conn.execute('SELECT power_mw FROM projects').fetchone()[0],7.4)

    def test_post_correction_gate_rejects_wrong_mw(self):
        save_event(self.conn,project_storage(event()));self.run_repair()
        self.conn.execute('UPDATE events SET power_mw=7.4');self.conn.commit()
        with self.assertRaises(ValueError):validate_docm_storage(self.conn)

    def test_source_invariant_failure_rolls_back(self):
        save_event(self.conn,event())
        with patch('app.docm_storage.source_fingerprint',side_effect=['before','changed']), self.assertRaises(ValueError):self.run_repair()
        self.assertEqual(self.conn.execute('SELECT power_mw FROM events').fetchone()[0],7.4)

    def test_geography_recovers_from_official_municipality_only(self):
        save_event(self.conn,event());self.run_repair()
        result=enrich_missing_project_geography(self.conn,[Municipality('Almagro','13013','Ciudad Real','Castilla-La Mancha')])
        self.assertEqual(result['resolved'],1)
        self.assertEqual(self.conn.execute('SELECT province FROM projects').fetchone()[0],'Ciudad Real')
        self.assertIsNone(self.conn.execute('SELECT province FROM events').fetchone()[0])
