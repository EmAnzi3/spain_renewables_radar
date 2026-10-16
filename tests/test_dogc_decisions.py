"""DOGC operative decisions on original acts (fixtures: official pages acquired by the certified 24-month backfill)."""
import json,unittest
from pathlib import Path
from app.dogc_semantics import classify_document,verify_evidence
from app.dogc_projection import events_from_record,IdentityReviewRequired

FIX=Path(__file__).parent/'fixtures/dogc_decisions'
def load(name):
    d=json.loads((FIX/(name+'.json')).read_text(encoding='utf-8'));return d['candidate'],d['pages']
def run(name):
    c,p=load(name);r=classify_document(c,p);return r,p

class DecisionTests(unittest.TestCase):
    def expect(self,name,category,event,lifecycle=None,project=None):
        r,p=run(name)
        self.assertEqual((r['category'],r['event']),(category,event))
        self.assertGreater(verify_evidence(r,p),0)
        if lifecycle:
            [(e,_)]=events_from_record(r,p,[])
            self.assertEqual((e.event_type,e.commercial_stage),lifecycle)
            if project:self.assertEqual(e.project_name,project)
        return r
    def test_construction_grant_after_page_header(self):
        self.expect('grant_matacan','ENERGY_PROJECT','PRIOR_AND_CONSTRUCTION_AUTH',('CONSTRUCTION_AUTH','AUTHORIZED'),'PS Matacan Solar')
    def test_prior_authorisation_alone_is_not_construction(self):
        self.expect('prior_auth_only_els_palous','ENERGY_PROJECT','PRIOR_AUTH_ONLY',('PRIOR_AUTH','PERMITTING'))
    def test_evacuation_line_grant_is_not_a_new_plant(self):
        self.expect('grant_evacuation_line_only','OUT_OF_SCOPE','EVACUATION_INFRASTRUCTURE_ONLY_NOT_PLANT')
    def test_evacuation_line_modification_does_not_authorise_the_plant(self):
        # Previously projected as CONSTRUCTION_AUTH/AUTHORIZED for the plant.
        self.expect('line_modification_el_prat_de_la_plana','OUT_OF_SCOPE','EVACUATION_INFRASTRUCTURE_ONLY_NOT_PLANT')
    def test_names_keep_codes_but_reject_heading_words(self):
        from app.dogc_semantics import clean_name
        self.assertEqual(clean_name('22CER'),'22CER')
        for junk in ("d'autoconsum col·lectiu",'al pavelló municipal','(autoconsum-injecció zero)','5 MW de bateries'):self.assertEqual(clean_name(junk),'')
        self.assertEqual(clean_name('stand-alone anomenada PB Mateu'),'PB Mateu')
        self.assertEqual(clean_name('Guixeres I de 19.968 kW al terme municipal de Montgat'),'Guixeres I')
    def test_denial(self):
        self.expect('denial_paradis','ENERGY_PROJECT','AUTHORIZATION_DENIED',('DENIED','BLOCKED'),'FV PARADÍS SOLAR')
    def test_unfavourable_dia_blocks(self):
        self.expect('dia_unfavourable_greentarraco','ENERGY_PROJECT','ENVIRONMENTAL_DIA_UNFAVOURABLE',('DIA_UNFAVOURABLE','BLOCKED'),'Greentarraco 1')
    def test_favourable_dia_is_permitting_not_authorisation(self):
        r=self.expect('dia_favourable_la_selva_22','ENERGY_PROJECT','ENVIRONMENTAL_DIA_FAVORABLE',('DIA','PERMITTING'))
        self.assertIn('ENVIRONMENTAL_ACT_IS_NOT_CONSTRUCTION_AUTH',r['flags'])
    def test_partially_unfavourable_dia_is_flagged(self):
        r=self.expect('dia_mixed_galera','ENERGY_PROJECT','ENVIRONMENTAL_DIA_MIXED',('DIA','PERMITTING'),'Galera Solar')
        self.assertIn('DIA_FAVOURABLE_ONLY_FOR_PART_OF_PROJECT',r['flags'])
    def test_storage_screening_subject_and_plural_decision(self):
        self.expect('screening_bess_pb_condor','ENERGY_PROJECT','ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA',('ENVIRONMENTAL_SCREENING','PERMITTING'),'PB Condor')
    def test_archive_ends_procedure(self):
        self.expect('archive_access_permit_lapsed','ENERGY_PROJECT','PROCEDURE_ARCHIVED',('PROCEDURE_ENDED','BLOCKED'))
    def test_land_occupation_survey_is_preconstruction(self):
        self.expect('expropriation_survey_la_ribera','ENERGY_PROJECT','EXPROPRIATION_PRIOR_SURVEY',('EXPROPRIATION','PRECONSTRUCTION'))
    def test_several_named_plants_are_never_one_project(self):
        r,p=run('multi_asset_brugen_held')
        self.assertIsNone(r['project_name'])
        with self.assertRaises(IdentityReviewRequired):events_from_record(r,p,[])
