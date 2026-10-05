"""Checker tests use synthetic records; source semantics are tested in the live artifact replay."""
import copy
import json
from pathlib import Path
import unittest
from scripts.classify_dogc_documents import check_review_fixture, unique_evidence_count

FIXTURE=Path(__file__).parent/'fixtures/dogc_review_20261004.json'


def sample():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    records=[]
    for case in fixture['documents']:
        r=dict(case,document_classified=True,decision={'value':case['event']},
               construction_start_date=None,construction_end_date=None,epc=None,bop=None,
               production_enabled=False,automatic_project_merge=False,live_collector_validated=False,
               field_completeness_certified=False,database_writes=0,components=[],capacity_observations=[],
               primary_references=[],flags=[],correction=None,
               capacity_conflicts=[{'code':'SOURCE_CAPACITY_CONFLICT'}] if case['document_id'] in fixture['capacity_conflict_document_ids'] else [])
        records.append(r)
    by_id={r['document_id']:r for r in records}
    for case in fixture['quantity_cases']:
        by_id[case['id']]['capacity_observations'].append(dict({k:v for k,v in case.items() if k!='id'},aggregation_allowed=False))
    for identity,refs in fixture['primary_reference_cases'].items():
        by_id[identity]['primary_references']=[{'value':v} for v in refs]
    by_id['1054540']['correction']={'automatic_lifecycle_change':False,'corrected_interpretation':'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA'}
    for identity in ('1054484','1054443'):
        by_id[identity]['flags'].append('EXISTING_PV_AUTHORIZATION_DOES_NOT_AUTHORIZE_NEW_STORAGE')
    by_id['1054455']['flags'].append('EXISTING_CAPACITY_IS_NOT_ADDED_CAPACITY')
    by_id['1055360']['flags'].append('SHARED_EVACUATION_DOES_NOT_CREATE_ADDITIONAL_PLANTS')
    return records,fixture,by_id


class SemanticReviewTests(unittest.TestCase):
    def test_review_fixture_accepts_only_the_exact_case_set(self):
        r,f,_=sample();result=check_review_fixture(r,f)
        self.assertEqual(result['reviewed_document_cases'],48)
        self.assertEqual(result['reviewed_quantity_cases'],12)

    def test_missing_and_duplicate_candidates_fail(self):
        for mutation in ('missing','duplicate'):
            r,f,_=sample();r=r[:-1] if mutation=='missing' else r+[copy.deepcopy(r[0])]
            with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_changed_decision_hash_and_page_count_fail(self):
        for key,value in [('event','CONSTRUCTION_AUTH'),('pdf_sha256','wrong'),('page_count',999)]:
            r,f,_=sample();r[0][key]=value
            with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_inferred_work_dates_and_contractors_fail(self):
        for key in ('construction_start_date','construction_end_date','epc','bop'):
            r,f,_=sample();r[0][key]='invented'
            with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_production_or_completeness_claim_fails(self):
        for key in ('production_enabled','automatic_project_merge','live_collector_validated','field_completeness_certified'):
            r,f,_=sample();r[0][key]=True
            with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_unsupported_scalar_capacity_and_summation_fail(self):
        for kind in ('scalar','sum'):
            r,f,by_id=sample()
            if kind=='scalar':r[0]['components']=[{'capacity_mw':123}]
            else:by_id['1054820']['capacity_observations'][0]['aggregation_allowed']=True
            with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_lost_source_conflict_fails(self):
        r,f,by_id=sample();by_id['1054428']['capacity_conflicts']=[]
        with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_wrong_converted_value_fails(self):
        r,f,by_id=sample();by_id['1054820']['capacity_observations'][0]['normalized_value']='999'
        with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_foreign_shared_reference_cannot_become_primary(self):
        r,f,by_id=sample();by_id['1054820']['primary_references'].append({'value':'FUE-2025-04391595'})
        with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_correction_and_existing_capacity_boundaries_are_checked(self):
        for identity in ('1054540','1054455','1054484','1055360'):
            r,f,by_id=sample()
            if identity=='1054540':by_id[identity]['correction']['automatic_lifecycle_change']=True
            else:by_id[identity]['flags']=[]
            with self.assertRaises(ValueError):check_review_fixture(r,f)

    def test_evidence_counter_does_not_duplicate_nested_spans(self):
        span={'page':1,'start':1,'end':4,'page_text_sha256':'a'*64,'quote':'abc'}
        r={'document_id':'1','decision':{'evidence':[span]},'details':[{'evidence':[copy.deepcopy(span)]}]}
        self.assertEqual(unique_evidence_count([r]),1)
