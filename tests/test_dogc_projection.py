import copy
import hashlib
import unittest

from app.dogc_projection import event_from_record, project_geography, scalar_capacity
from app.enrichment.ine_municipalities import Municipality

CATALOG=[Municipality('Gurb','08100','Barcelona','Cataluña'),Municipality('Vic','08298','Barcelona','Cataluña'),
    Municipality('Ivorra','25114','Lleida','Cataluña'),Municipality('Estaràs','25085','Lleida','Cataluña'),
    Municipality('Castellfollit de Riubregós','08060','Barcelona','Cataluña'),Municipality('Pujalt','08176','Barcelona','Cataluña'),
    Municipality('Brunyola i Sant Martí Sapresa','17028','Girona','Cataluña'),Municipality('Vendrell, El','43163','Tarragona','Cataluña')]


def quantity(value='5.04',basis='UNSPECIFIED_POWER',component='BESS',scope='INDEX_TITLE'):
    return {'normalized_value':value,'basis':basis,'component':component,'normalized_unit':'MW','scope':scope,
            'source_number':value,'source_unit':'MW','evidence':[]}


def record(event='PRIOR_AND_CONSTRUCTION_AUTH'):
    text='Atorgar autorització al projecte'
    proof={'page':1,'start':0,'end':len(text),'quote':text,'page_text_sha256':hashlib.sha256(text.encode()).hexdigest()}
    row={'document_id':'1','publication_date':'2026-09-08','source_title':'Planta de bateries Demo al terme municipal de Vic, a la comarca d\'Osona',
        'source_url':'https://portaldogc.gencat.cat/example','source_pdf_url':'https://portaldogc.gencat.cat/example.pdf',
        'source_retrieved_at':'2026-10-05T07:00:00+00:00','pdf_sha256':'a'*64,'page_count':1,
        'document_classified':True,'category':'ENERGY_PROJECT','event':event,'decision':{'value':event,'evidence':[proof]},
        'project_name':{'value':'Demo','evidence':[]},'proponent':None,'primary_references':[{'value':'FUE-2025-12345678'}],
        'technologies':['BESS'],'components':[{'technology':'BESS','role':'PROJECT_COMPONENT'}],
        'capacity_observations':[quantity()],'capacity_conflicts':[],'flags':[]}
    return row,[{'page':1,'text':text}]


class ProjectionTests(unittest.TestCase):
    def test_compound_municipality_not_split_at_conjunction(self):
        geo=project_geography('Planta al terme municipal de Brunyola i Sant Martí Sapresa (Selva)',CATALOG)
        self.assertEqual(geo['status'],'RESOLVED');self.assertEqual(len(geo['municipalities']),1)
        self.assertEqual(geo['provinces'],['Girona'])

    def test_all_secondary_location_clauses_are_preserved(self):
        geo=project_geography("als termes municipals d'Ivorra i Estaràs, a la comarca de la Segarra (Lleida), i Castellfollit de Riubregós i Pujalt, a la comarca de l'Anoia (Barcelona) (exp. FUE-2025-12345678)",CATALOG)
        self.assertEqual(geo['status'],'MULTI_PROVINCE');self.assertEqual(len(geo['municipalities']),4)
        self.assertEqual(geo['provinces'],['Barcelona','Lleida'])

    def test_county_or_province_not_used_as_city(self):
        geo=project_geography('al terme municipal de Gurb, a la província de Barcelona',CATALOG+[Municipality('Barcelona','08019','Barcelona','Cataluña')])
        self.assertEqual([m['name'] for m in geo['municipalities']],['Gurb'])

    def test_promoter_address_is_not_project_location(self):
        self.assertEqual(project_geography('Promotor domiciliat a Vic',CATALOG)['status'],'UNRESOLVED')

    def test_unmatched_town_does_not_force_known_towns_province(self):
        geo=project_geography('als termes municipals de Vic i Municipi desconegut',CATALOG)
        self.assertEqual(geo['status'],'UNRESOLVED');self.assertIn('desconegut',geo['unresolved_text'])

    def test_official_article_inversion_and_contraction(self):
        geo=project_geography('al terme municipal del Vendrell (exp. 1)',CATALOG)
        self.assertEqual(geo['status'],'RESOLVED');self.assertEqual(geo['provinces'],['Tarragona'])

    def test_no_heuristic_resolution_of_homonyms(self):
        catalog=CATALOG+[Municipality('Vic','99999','Girona','Cataluña')]
        self.assertEqual(project_geography('al terme municipal de Vic',catalog)['status'],'UNRESOLVED')

    def test_request_does_not_become_authorized(self):
        r,p=record('PUBLIC_INFO_AUTHORIZATION_REQUEST');event,_=event_from_record(r,p,CATALOG)
        self.assertEqual((event.event_type,event.commercial_stage),('PUBLIC_INFO','EARLY'))

    def test_screening_is_not_dia_or_construction_grant(self):
        for kind in ('ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA','ORDINARY_EIA_REQUIRED'):
            r,p=record(kind);event,_=event_from_record(r,p,CATALOG)
            self.assertEqual((event.event_type,event.commercial_stage),('ENVIRONMENTAL_SCREENING','PERMITTING'))

    def test_current_permit_only_sets_authorized(self):
        r,p=record();event,_=event_from_record(r,p,CATALOG)
        self.assertEqual((event.event_type,event.commercial_stage),('CONSTRUCTION_AUTH','AUTHORIZED'))

    def test_municipal_and_correction_do_not_create_energy_permits(self):
        for category in ('MUNICIPAL_PROJECT','CORRECTION','OUT_OF_SCOPE'):
            r,p=record();r['category']=category
            self.assertIsNone(event_from_record(r,p,CATALOG)[0])

    def test_conflicting_power_stays_missing(self):
        r,p=record();r['capacity_conflicts']=[{'component':'BESS'}]
        self.assertIsNone(event_from_record(r,p,CATALOG)[0].power_mw)

    def test_hybrid_powers_are_not_added(self):
        r,p=record();r['technologies']=['PV','BESS'];r['components']=[{'role':'HYBRID_COMPONENT'}]
        r['capacity_observations']=[quantity('4.95',component='PV'),quantity('1.26')]
        e,_=event_from_record(r,p,CATALOG);self.assertEqual(e.technology,'HYBRID');self.assertIsNone(e.power_mw)

    def test_existing_pv_does_not_replace_new_battery_scope(self):
        r,p=record();r['technologies']=['PV','BESS'];r['components']=[{'role':'EXISTING_PV_CONTEXT'},{'role':'PROJECT_COMPONENT'}]
        e,_=event_from_record(r,p,CATALOG);self.assertEqual(e.technology,'BESS');self.assertIsNone(e.power_mw)

    def test_grid_access_and_device_power_not_selected(self):
        r,_=record();r['capacity_observations']=[quantity('4.999','GRID_ACCESS'),quantity('0.21','DEVICE_UNIT_POWER')]
        self.assertIsNone(scalar_capacity(r,'BESS')[0])

    def test_nominal_and_peak_are_separate_not_added(self):
        r,p=record();r['technologies']=['PV'];r['components']=[{'role':'PROJECT_COMPONENT'}]
        r['capacity_observations']=[quantity('3.63','NOMINAL_AC','PV'),quantity('4.13','PEAK_DC','PV')]
        e,m=event_from_record(r,p,CATALOG);self.assertEqual(e.power_mw,3.63)
        self.assertEqual(m['extraction']['capacity_selection']['basis'],'NOMINAL_AC')

    def test_same_dossier_accumulates_events_under_one_identity(self):
        r,p=record();one,_=event_from_record(r,p,CATALOG)
        r['document_id']='2';r['event']='PUBLIC_INFO_AUTHORIZATION_REQUEST';two,_=event_from_record(r,p,CATALOG)
        self.assertEqual(one.project_key,two.project_key);self.assertNotEqual(one.external_id,two.external_id)

    def test_joint_dossiers_are_explicit_not_one_arbitrary_reference(self):
        r,p=record();r['primary_references']+=[{'value':'FUE-2025-87654321'}]
        e,_=event_from_record(r,p,CATALOG);self.assertIsNone(e.expediente)
        r['primary_references'].reverse();self.assertEqual(e.project_key,event_from_record(r,p,CATALOG)[0].project_key)

    def test_short_reference_is_not_completed(self):
        r,p=record();r['primary_references']=[{'value':'FUE-2024-03839'},{'value':'OTAATA20240139'}]
        e,m=event_from_record(r,p,CATALOG);self.assertEqual(e.expediente,'OTAATA20240139')
        self.assertIn('FUE-2024-03839',m['extraction']['current_references'])

    def test_unknown_identity_or_wording_fails_closed(self):
        r,p=record();r['primary_references']=[]
        with self.assertRaises(ValueError):event_from_record(r,p,CATALOG)
        r,p=record();r['category']='REVIEW_REQUIRED';r['document_classified']=False
        with self.assertRaises(ValueError):event_from_record(r,p,CATALOG)

    def test_source_record_and_original_text_are_unchanged(self):
        r,p=record();before=copy.deepcopy((r,p));e,_=event_from_record(r,p,CATALOG)
        self.assertEqual((r,p),before);self.assertEqual(e.raw_text,p[0]['text'])
