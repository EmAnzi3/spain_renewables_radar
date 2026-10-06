"""Reviewed actual multi-plant act; no runtime rule keyed to its document ID."""
import copy
from datetime import date
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from app.db import connect
from app.store import save_event
from app.dogc_semantics import classify_document,Document,event_classification
from app.dogc_projection import events_from_record,event_from_record
from app.dogc_named_assets import plant_names
from app.collectors.dogc import DOGCCollector
from app.enrichment.ine_municipalities import Municipality

FIXTURE=Path(__file__).parent/'fixtures/dogc_1056019_original.json'
# Synthetic catalogue for deterministic tests; official INE is acquired in live runs.
CATALOG=[Municipality('Vallirana','08295','Barcelona','Cataluña'),Municipality('Olesa de Bonesvalls','08146','Barcelona','Cataluña'),Municipality('Begues','08020','Barcelona','Cataluña')]

def source():return json.loads(FIXTURE.read_text(encoding='utf-8'))

class NamedPlantTests(unittest.TestCase):
    def test_actual_resolution_is_screening_not_construction(self):
        f=source();r=classify_document(f['candidate'],f['pages'])
        self.assertEqual(r['event'],'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA')
        self.assertEqual({x['page'] for x in r['decision']['evidence']},{8})
        self.assertEqual(r['named_asset_group']['plant_count'],7)
        self.assertIsNone(r['epc']);self.assertIsNone(r['construction_start_date'])
    def test_seven_distinct_source_plants_not_one_or_eight(self):
        f=source();r=classify_document(f['candidate'],f['pages']);events=events_from_record(r,f['pages'],CATALOG)
        self.assertEqual(len(events),7);self.assertEqual(len({e.project_key for e,_ in events}),7)
        self.assertEqual(len({e.external_id for e,_ in events}),7)
        self.assertEqual({e.project_name for e,_ in events},{'BESS Begues '+x for x in ['I','II','III','IV','V','VI','VII']})
        for e,m in events:
            self.assertEqual((e.power_mw,e.technology,e.event_type,e.commercial_stage),(5.04,'BESS','ENVIRONMENTAL_SCREENING','PERMITTING'))
            self.assertEqual(e.province,'Barcelona');self.assertEqual(e.publication_date,'2026-10-05')
            self.assertEqual(m['extraction']['capacity_selection']['storage_energy_mwh'],'20.06')
    def test_group_companies_not_assigned_to_every_plant(self):
        f=source();r=classify_document(f['candidate'],f['pages'])
        self.assertIn('MACRINA SOLAR 21',r['named_asset_group']['group_promoters']['value'])
        for e,_ in events_from_record(r,f['pages'],CATALOG):self.assertIsNone(e.promoter)
    def test_original_pages_and_classification_never_mutated(self):
        f=source();r=classify_document(f['candidate'],f['pages']);old=copy.deepcopy((r,f))
        events_from_record(r,f['pages'],CATALOG);self.assertEqual((r,f),old)
    def test_no_single_event_shortcut_for_seven_plants(self):
        f=source();r=classify_document(f['candidate'],f['pages'])
        with self.assertRaises(ValueError):event_from_record(r,f['pages'],CATALOG)
    def test_identity_stable_across_document_ids_and_dated_events(self):
        f=source();one=classify_document(f['candidate'],f['pages']);candidate=dict(f['candidate'],document_id='9876543',publication_date='2026-10-06')
        two=classify_document(candidate,f['pages'])
        a=events_from_record(one,f['pages'],CATALOG);b=events_from_record(two,f['pages'],CATALOG)
        self.assertEqual({e.project_key for e,_ in a},{e.project_key for e,_ in b})
        self.assertFalse({e.external_id for e,_ in a}&{e.external_id for e,_ in b})
    def test_number_of_plants_must_match_actual_list(self):
        f=source();f['pages'][0]['text']=f['pages'][0]['text'].replace('implantació de set plantes','implantació de sis plantes')
        with self.assertRaisesRegex(ValueError,'count'):classify_document(f['candidate'],f['pages'])
    def test_title_body_power_conflict_not_fixed_or_summed(self):
        f=source();f['pages'][0]['text']=f['pages'][0]['text'].replace("d'energia de 5,04 MW","d'energia de 5,05 MW")
        with self.assertRaisesRegex(ValueError,'capacity conflict'):classify_document(f['candidate'],f['pages'])
    def test_missing_each_plant_evidence_does_not_allocate_total(self):
        f=source();f['pages'][7]['text']=f['pages'][7]['text'].replace('MWh cadascuna','MWh en total')
        with self.assertRaises(ValueError):classify_document(f['candidate'],f['pages'])
    def test_mismatched_operative_plant_is_not_ignored(self):
        f=source();f['pages'][7]['text']=f['pages'][7]['text'].replace('Begues VII','Begues VIII')
        with self.assertRaises(ValueError):classify_document(f['candidate'],f['pages'])
    def test_ambiguous_multiple_shared_references_not_chosen(self):
        f=source();r=classify_document(f['candidate'],f['pages']);r['primary_references'].append({'value':'FUE-2025-04353294','evidence':[]})
        with self.assertRaisesRegex(ValueError,'identity is ambiguous'):events_from_record(r,f['pages'],CATALOG)
    def test_no_number_range_expansion_or_duplicate(self):
        for value in ['BESS Begues I, BESS Begues I','BESS Begues I–VII']:
            with self.assertRaises(ValueError):plant_names(value)
    def test_persistence_keeps_seven_plants_and_one_original_act(self):
        f=source();record=classify_document(f['candidate'],f['pages']);projections=events_from_record(record,f['pages'],CATALOG)
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/'db.sqlite'));collector=DOGCCollector(output=str(Path(tmp)/'dogc'),catalog=CATALOG)
            for e,m in projections:save_event(conn,e);collector.metadata[e.external_id]=m
            collector.records[record['document_id']]={'classification':record,'pdf_file':'source.pdf'}
            collector.persist_metadata(conn)
            self.assertEqual(conn.execute('SELECT count(*) FROM projects').fetchone()[0],7)
            self.assertEqual(conn.execute('SELECT count(*) FROM events').fetchone()[0],7)
            self.assertEqual(conn.execute('SELECT count(*) FROM dogc_document_observations').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM regional_public_metadata').fetchone()[0],7)
            for e,_ in projections:self.assertEqual(save_event(conn,e),(False,False))
            collector.persist_metadata(conn);collector.close();conn.close()
    def test_absent_resolution_does_not_become_approved_from_title(self):
        f=source();f['pages'][7]['text']=f['pages'][7]['text'].replace('Resolc:\nPrimer','En estudi:')
        r=classify_document(f['candidate'],f['pages']);self.assertEqual(r['category'],'REVIEW_REQUIRED')
    def test_modified_asset_quantity_does_not_pass_original_replay(self):
        f=source();r=classify_document(f['candidate'],f['pages']);r['named_asset_group']['per_plant_power_mw']='35.28'
        with self.assertRaises(ValueError):events_from_record(r,f['pages'],CATALOG)
