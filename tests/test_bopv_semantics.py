"""Synthetic source-shaped clauses, not a substitute for official live coverage."""
import copy
from decimal import Decimal
import unittest
from app.bopv_semantics import (classify_document,paragraphs_from_html,check_evidence,evidence,number,quantities)


def source(title,body,identity='2026/00001'):
    rows=[{'index':i,'text':t,'source_class':[]} for i,t in enumerate([title]+body)]
    return {'title':title,'external_id':identity,'source_url':'https://www.euskadi.eus/bopv2/datos/2026/09/2600001a.shtml','publication_date':'2026-09-16'},rows


def wind(name='Demo',power='30'):
    return source(f'ANUNCIO por el que se somete a información pública la solicitud de autorización administrativa previa para el parque eólico denominado «{name}», en Ayala y Okondo (Álava).',[
        'Se anuncia la solicitud de autorización administrativa previa.',
        'Solicitante: Wind Developer, S.L.',
        'Potencia bruta instalada: '+power+' MW.',
        'Términos municipales afectados: Ayala y Okondo.',
        'Procedimiento: GE–Y.',
        'El promotor tiene domicilio en Madrid.'
    ])


def dia():
    return source('RESOLUCIÓN por la que se formula la declaración de impacto ambiental del proyecto de parque eólico Demo (31,2 MW) y sus infraestructuras (Álava).',[
        'Históricamente el proyecto tenía una potencia de 30 MW y se pidió autorización.',
        'RESUELVO:',
        'Primero.– Formular, a los solos efectos ambientales, declaración de impacto ambiental del proyecto de parque eólico «Demo» (31,2 MW), promovido por Developer, S.L., en los términos municipales de Amurrio y Ayala (Álava).',
        'Segundo.– Fijar las siguientes condiciones que resultan vinculantes.',
        'Tercero.– El plazo para el inicio de la ejecución será cuatro años desde la publicación.'
    ])


def cluster():
    return source('ANUNCIO por el que se someten a información pública las solicitudes de autorización administrativa previa y declaración de impacto ambiental del Clúster Eólico Uno-Dos (Gipuzkoa).',[
        'Se someten a información pública el proyecto y el estudio de impacto ambiental.',
        'Expediente: 20-GE-Y-2025-00004.',
        'Clúster eólico formado por los dos (2) parques eólicos «Uno» y «Dos». Cada uno de estos parques cuenta con una potencia instalada de 4,99 MW, ubicados en el término municipal de Villabona (Gipuzkoa).',
        'Solicitante: Group Applicant, S.L.',
        '– «PE Uno», Owner One, S.L.',
        '– «PE Dos», Owner Two, S.L.',
        'Línea en los términos municipales de Andoain, Urnieta y Hernani.'
    ])


def pair():
    return source('ANUNCIO por el que se someten a información pública solicitudes de autorización administrativa previa para las plantas fotovoltaicas «Alpha Solar» (10,12 MW) y «Beta Solar» (1 MW), en Álava (Álava).',[
        'Se someten a información pública los proyectos y el estudio ambiental.',
        'Peticionario: Developer PV, S.L.U., con CIF A1234567.',
        'Expediente 01–GE–Y–2025–00021.',
        '• Proyecto «Alpha Solar» consistente en:',
        'Planta solar fotovoltaica «Alpha Solar» de 21252 módulos de 620 Wp, en los municipios de Vitoria-Gasteiz y Arratzua-Ubarrundia.',
        'El proyecto Other Solar 1, expediente 01–GE–Y–2024–00006, comparte la línea.',
        'Expediente 01–GE–Y–2025–00031.',
        '• Proyecto «Beta Solar» consistente en:',
        'Planta solar fotovoltaica «Beta Solar», 5 inversores de 200 kW en el término municipal de Vitoria-Gasteiz.',
        '• Proyecto «Subestación Beta Solar 400/30 kV», en el término municipal de Vitoria-Gasteiz.'
    ])


def hybrid():
    return source('ANUNCIO por el que se somete a información pública la solicitud de autorización administrativa previa para la hibridación de cogeneración existente con parque solar y almacenamiento de baterías «Industry», en Berantevilla (Álava).',[
        'Se somete a información pública el proyecto correspondiente a la hibridación.',
        '• Expediente 01–GE–Y–2025–00049.',
        '• Peticionario: Industry, S.A., con CIF A01234567.',
        '• Finalidad: producción de energía mediante fotovoltaica y almacenamiento para autoconsumo con excedentes.',
        '• Proyecto «Industry» consistente en:',
        '– 26 inversores fotovoltaicos de 320 kVA. Con una potencia total de 8.320 kVAn.',
        '– Almacenamiento: 7 contenedores de 1.629,4 kWh y 28 PCS con una potencia total de 5.600 kW.',
        '• Término municipal afectado: Berantevilla.',
        'El proyecto se sometió a evaluación de impacto ambiental simplificada.'
    ])


class BOPVSemanticsTests(unittest.TestCase):
    def test_request_not_prior_or_construction_authorization(self):
        got=classify_document(*wind())['assets'][0]
        self.assertEqual((got['event_type'],got['commercial_stage']),('PUBLIC_INFO','EARLY'))
    def test_no_specific_dossier_is_not_fabricated_from_ge_y(self):
        got=classify_document(*wind())['assets'][0]
        self.assertIsNone(got['expediente']);self.assertTrue(got['identity_is_provisional'])
    def test_promoter_address_not_generation_location(self):
        got=classify_document(*wind())['assets'][0]
        self.assertEqual((got['province'],got['site_municipalities_text']),('Álava','Ayala y Okondo'))
    def test_classifier_not_keyed_by_name_capacity_or_document_number(self):
        r,ps=wind('Another project','22,3');r['external_id']='2026/00123'
        got=classify_document(r,ps)['assets'][0]
        self.assertEqual((got['project_name'],got['power_mw']),('Another project',22.3))
    def test_missing_current_body_keeps_unreviewed(self):
        r,ps=wind();ps[1]['text']='A prior act opened a consultation.'
        self.assertEqual(classify_document(r,ps)['classification'],'REVIEW_REQUIRED')
    def test_conflicting_explicit_power_not_arbitrarily_selected(self):
        r,ps=wind();ps.append({'index':len(ps),'text':'Potencia bruta instalada: 35 MW.','source_class':[]})
        self.assertIsNone(classify_document(r,ps)['assets'][0]['power_mw'])
    def test_absent_project_power_never_comes_from_device_total(self):
        r,ps=wind();ps[3]['text']='Equipamiento: seis aerogeneradores de 5 MW.'
        self.assertIsNone(classify_document(r,ps)['assets'][0]['power_mw'])
    def test_dia_current_dispositive_not_old_requested_authorization(self):
        got=classify_document(*dia())['assets'][0]
        self.assertEqual((got['event_type'],got['commercial_stage'],got['power_mw']),('DIA','PERMITTING',31.2))
    def test_environmental_validity_does_not_create_a_construction_schedule(self):
        got=classify_document(*dia())['assets'][0]
        self.assertIsNone(got['work_start']);self.assertIsNone(got['work_end'])
        self.assertFalse(got['permit_to_build_inferred'])
    def test_resolution_heading_without_operative_act_not_a_dia(self):
        r,ps=dia();ps[2]['text']='ANTECEDENTES:'
        self.assertEqual(classify_document(r,ps)['classification'],'REVIEW_REQUIRED')
    def test_repeated_operative_heading_is_ambiguous(self):
        r,ps=dia();ps.append({'index':len(ps),'text':'RESUELVO:','source_class':[]})
        self.assertEqual(classify_document(r,ps)['classification'],'REVIEW_REQUIRED')
    def test_dia_current_name_must_agree_with_title(self):
        r,ps=dia();ps[3]['text']=ps[3]['text'].replace('«Demo»','«Other»')
        with self.assertRaises(ValueError):classify_document(r,ps)
    def test_dia_title_power_conflict_is_preserved_not_resolved(self):
        r,ps=dia();r['title']=r['title'].replace('31,2','32,1');ps[0]['text']=r['title']
        got=classify_document(r,ps)['assets'][0]
        self.assertIsNone(got['power_mw']);self.assertIn('EXPLICIT_TITLE_AND_CURRENT_PROJECT_POWER_CONFLICT',got['quality_flags'])
    def test_explicit_negative_dia_is_not_permission(self):
        r,ps=dia();ps[3]['text']=ps[3]['text'].replace('declaración de impacto ambiental del','declaración de impacto ambiental desfavorable del')
        got=classify_document(r,ps)['assets'][0]
        self.assertEqual(got['commercial_stage'],'BLOCKED')
    def test_two_named_wind_assets_have_different_owners_and_one_applicant(self):
        got=classify_document(*cluster())['assets']
        self.assertEqual([a['power_mw'] for a in got],[4.99,4.99])
        self.assertEqual([a['promoter'] for a in got],['Owner One, S.L.','Owner Two, S.L.'])
        self.assertTrue(all(a['applicant']=='Group Applicant, S.L.' for a in got))
        self.assertEqual(len({a['asset_key'] for a in got}),2)
    def test_shared_dossier_does_not_collapse_two_plants(self):
        got=classify_document(*cluster())['assets']
        self.assertTrue(all(a['expediente_shared_by_explicit_plants'] for a in got))
        self.assertEqual(len({a['expediente'] for a in got}),1)
        self.assertEqual(len({a['asset_key'] for a in got}),2)
    def test_cluster_count_needs_explicit_name_list(self):
        r,ps=cluster();ps[3]['text']=ps[3]['text'].replace('(2)','(3)')
        with self.assertRaises(ValueError):classify_document(r,ps)
    def test_missing_owner_not_assigned_group_applicant(self):
        r,ps=cluster();ps[5]['text']='No plant owner specified.'
        self.assertIsNone(classify_document(r,ps)['assets'][0]['promoter'])
    def test_generation_site_not_shared_evacuations_route(self):
        got=classify_document(*cluster())['assets']
        self.assertTrue(all(a['site_municipalities_text']=='Villabona' for a in got))
    def test_pv_dossiers_and_capacities_stay_per_plant(self):
        got=classify_document(*pair())['assets']
        self.assertEqual([a['power_mw'] for a in got],[10.12,1.0])
        self.assertEqual([a['expediente'] for a in got],['01–GE–Y–2025–00021','01–GE–Y–2025–00031'])
        self.assertEqual(len(got),2)
    def test_other_plants_and_substation_are_not_additional_assets(self):
        got=classify_document(*pair())['assets']
        self.assertEqual([a['project_name'] for a in got],['Alpha Solar','Beta Solar'])
    def test_missing_individual_section_cannot_borrow_other_reference(self):
        r,ps=pair();ps[8]['text']=ps[8]['text'].replace('Beta Solar','Other')
        with self.assertRaises(ValueError):classify_document(r,ps)
    def test_hybrid_self_consumption_remains_visible_but_separate(self):
        got=classify_document(*hybrid())
        self.assertEqual(got['classification'],'SELF_CONSUMPTION_LEAD')
        self.assertIsNone(got['assets'][0]['power_mw']);self.assertEqual(got['assets'][0]['event_type'],'PUBLIC_INFO')
        self.assertEqual(got['database_events_created'],0)
    def test_apparent_power_is_not_active_mw_and_energy_not_power(self):
        got=classify_document(*hybrid());qs=got['quantities']
        self.assertEqual(next(q for q in qs if q['unit']=='kVAn')['kind'],'APPARENT_POWER')
        self.assertEqual(next(q for q in qs if q['unit']=='kWh')['kind'],'ENERGY')
        self.assertTrue(all(not q['automatically_summable'] for q in qs))
    def test_peak_power_is_not_mislabeled_as_nominal(self):
        qs=quantities([{'index':0,'text':'715 Wp y 5 MWn.'}])
        self.assertEqual([q['kind'] for q in qs],['SOLAR_PEAK_POWER','NOMINAL_ACTIVE_POWER'])
    def test_exact_source_spans_verified_and_not_mutated(self):
        args=pair();before=copy.deepcopy(args);got=classify_document(*args)
        self.assertEqual(args,before)
        for a in got['assets']:
            for spans in a['evidence'].values():
                for span in spans:check_evidence(args[1],span)
    def test_changed_evidence_quote_fails(self):
        _,ps=wind();ev=evidence(ps[1]);ev['quote']='invented'
        with self.assertRaises(ValueError):check_evidence(ps,ev)
    def test_title_sequence_and_document_identity_required(self):
        r,ps=wind();ps[0]['text']='Wrong title'
        with self.assertRaises(ValueError):classify_document(r,ps)
        r,ps=wind();r['external_id']='missing'
        with self.assertRaises(ValueError):classify_document(r,ps)
    def test_exact_replay_has_no_timestamp_mutation_or_random_ids(self):
        args=cluster();self.assertEqual(classify_document(*args),classify_document(*copy.deepcopy(args)))
    def test_owner_is_not_epc(self):
        for a in classify_document(*pair())['assets']:
            self.assertIsNone(a['epc']);self.assertEqual(a['epc_status'],'EPC_UNKNOWN')
    def test_numbers_use_spanish_thousands_and_decimal(self):
        self.assertEqual(number('1.629,4'),Decimal('1629.4'));self.assertEqual(number('5.600'),Decimal('5600'))
        self.assertEqual(number('4,99'),Decimal('4.99'))
    def test_invalid_quantities_are_rejected(self):
        for value in ('nan','-1','Infinity','1.2.3,4','abc'):
            with self.assertRaises(ValueError):number(value)
    def test_heading_tag_is_preserved_in_source_order(self):
        raw=b'<p class="BOPVTitulo">Title</p><p class="BOPVDetalle">Past</p><h6 class="BOPVClave">RESUELVO:</h6><p class="BOPVDetalle">Current</p>'
        self.assertEqual([p['text'] for p in paragraphs_from_html(raw,'utf-8')],['Title','Past','RESUELVO:','Current'])
    def test_pdf_only_tables_flag_does_not_invent_coordinates(self):
        r,ps=wind();ps.append({'index':len(ps),'text':'(Véase el .PDF)','source_class':[]})
        self.assertIn('SOME_TABLES_AVAILABLE_ONLY_IN_OFFICIAL_PDF',classify_document(r,ps)['assets'][0]['quality_flags'])
