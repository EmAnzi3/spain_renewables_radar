"""Adversarial semantic contracts; synthetic tests do not certify live coverage."""
import copy
from decimal import Decimal
import unittest
from app.dogc_semantics import Document, classify_document, decimal_number, verify_evidence


def candidate(title, identity='9000001'):
    return {'document_id':identity,'title':title,'publication_date':'2026-10-04','edition':'9763',
            'source_url':'https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?documentId='+identity+'&type=01&language=ca_ES',
            'pdf_sha256':'a'*64}


def classify(title, body, identity='9000001'):
    return classify_document(candidate(title,identity),[{'page':1,'text':body}])


AUTH = "Resolució per la qual s'atorguen l'autorització administrativa prèvia i l'autorització administrativa de construcció del projecte de la planta d'emmagatzematge anomenada Prova, de 5,04 MW (exp. FUE-2025-04391587)"
GRANT = "Resolc: Atorgar a l'empresa Prova, SL, l'autorització administrativa prèvia i l'autorització administrativa de construcció del projecte de la planta d'emmagatzematge anomenada Prova. Descripció de les instal·lacions: Potència instal·lada: 5.040 kW. Potència d'accés a la xarxa: 4.999 kW. Energia màxima acumulable: 20.060 kWh. Aquesta Resolució es dicta amb condicions."
REQUEST="Anunci pel qual se sotmet a informació pública la sol·licitud d'autorització administrativa prèvia i autorització administrativa de construcció de la planta solar fotovoltaica Prova, de 2,7 MW"
ENV="Resolució per la qual es fa públic l'Acord d'informe d'impacte ambiental del Projecte de planta solar fotovoltaica Prova (5,3 kWn)"
SCREEN="La Ponència d'Energies Renovables acorda: Primer Emetre l'informe d'impacte ambiental sobre el Projecte Prova, pel qual es determina que no s'ha de sotmetre a una avaluació d'impacte ambiental ordinària."


class EvidenceTests(unittest.TestCase):
    def test_multiline_curly_apostrophe_maps_to_original_bytes(self):
        pages=[{'page':1,'text':"L’autorització\n   administrativa és condicionada."}]
        doc=Document(pages);m=doc.find("l'autorització administrativa")
        record={'evidence':doc.evidence(*m.span())}
        self.assertEqual(record['evidence'][0]['quote'],"L’autorització\n   administrativa")
        self.assertEqual(verify_evidence(record,pages),1)

    def test_cross_page_evidence_keeps_both_page_identities(self):
        pages=[{'page':1,'text':'Atorgar autorització'}, {'page':2,'text':'administrativa prèvia'}]
        doc=Document(pages);ev=doc.evidence(0,len(doc.text))
        self.assertEqual([v['page'] for v in ev],[1,2]);self.assertEqual(verify_evidence({'evidence':ev},pages),2)

    def test_modified_quote_or_page_digest_fails(self):
        pages=[{'page':1,'text':'Atorgar autorització'}];doc=Document(pages)
        for field,value in [('quote','fake'),('page_text_sha256','b'*64),('start',1),('page',2)]:
            record={'evidence':doc.evidence(0,len(doc.text))};record['evidence'][0][field]=value
            with self.assertRaises(ValueError):verify_evidence(record,pages)

    def test_reordered_missing_and_unbounded_pages_fail(self):
        for pages in [[],[{'page':2,'text':'wrong'}],[{'page':1,'text':None}]]:
            with self.assertRaises(ValueError):Document(pages)

    def test_required_original_fields_are_not_fabricated(self):
        c=candidate(AUTH);del c['pdf_sha256']
        with self.assertRaises(ValueError):classify_document(c,[{'page':1,'text':GRANT}])


class OperativeActTests(unittest.TestCase):
    def test_grant_requires_operative_body(self):
        self.assertEqual(classify(AUTH,AUTH+' '+GRANT)['event'],'PRIOR_AND_CONSTRUCTION_AUTH')

    def test_title_or_historical_grant_alone_cannot_authorize(self):
        for body in [AUTH, AUTH+' Antecedents: Atorgar autorització administrativa de construcció el 2023.']:
            self.assertEqual(classify(AUTH,body)['category'],'REVIEW_REQUIRED')

    def test_bulleted_grant_is_supported(self):
        self.assertEqual(classify(AUTH,AUTH+' '+GRANT.replace('Resolc: Atorgar','Resolc: - Atorgar'))['event'],'PRIOR_AND_CONSTRUCTION_AUTH')

    def test_request_with_an_older_pv_authorization_is_not_new_authorization(self):
        text=REQUEST+" Aquesta instal·lació disposa d'autorització administrativa prèvia i de construcció de 2024. Se sotmet a informació pública la nova ampliació."
        self.assertEqual(classify(REQUEST,text)['event'],'PUBLIC_INFO_AUTHORIZATION_REQUEST')

    def test_environmental_consultation_without_final_body_is_not_screening_decision(self):
        text=ENV+" L'Ajuntament considera que no s'ha de sotmetre a una avaluació d'impacte ambiental ordinària."
        self.assertEqual(classify(ENV,text)['category'],'REVIEW_REQUIRED')

    def test_environmental_screening_is_not_construction_permission(self):
        r=classify(ENV,ENV+' '+SCREEN)
        self.assertEqual(r['event'],'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA')
        self.assertFalse(r['production_enabled'])

    def test_positive_need_for_ordinary_eia_is_not_denial(self):
        r=classify(ENV,ENV+' '+SCREEN.replace("no s'ha", "s'ha"))
        self.assertEqual(r['event'],'ORDINARY_EIA_REQUIRED')

    def test_unsupported_denial_is_retained_for_review(self):
        r=classify('Resolució que denega el projecte de planta solar fotovoltaica Prova','Es denega.')
        self.assertEqual(r['category'],'REVIEW_REQUIRED')

    def test_unknown_subject_retained_not_silently_excluded(self):
        self.assertEqual(classify('Anunci de tràmit especial','Informació incompleta')['category'],'REVIEW_REQUIRED')

    def test_initial_municipal_approval_never_promotes_conditional_final(self):
        title="Edicte sobre aprovació inicial del Projecte d'instal·lació fotovoltaica"
        r=classify(title,"ADMINISTRACIÓ LOCAL AJUNTAMENT DE PROVA "+title+" Es va acordar aprovar inicialment el projecte. En cas que no es presentin al·legacions esdevindrà aprovat definitivament.")
        self.assertEqual(r['event'],'MUNICIPAL_INITIAL_PROJECT_APPROVAL')

    def test_municipal_final_approval_is_not_electricity_construction_permission(self):
        title="Edicte sobre aprovació definitiva del Projecte d'instal·lació fotovoltaica"
        r=classify(title,'ADMINISTRACIÓ LOCAL '+title+' Primer. Aprovar definitivament el projecte.')
        self.assertEqual(r['event'],'MUNICIPAL_FINAL_PROJECT_APPROVAL')

    def test_municipal_heading_without_body_stays_unreviewed(self):
        title="Edicte sobre aprovació definitiva del Projecte d'instal·lació fotovoltaica"
        self.assertEqual(classify(title,'ADMINISTRACIÓ LOCAL '+title)['category'],'REVIEW_REQUIRED')

    def test_requested_public_utility_is_not_granted_utility(self):
        title="Anunci pel qual se sotmet a informació pública la sol·licitud de declaració d'utilitat pública del parc eòlic Prova"
        self.assertEqual(classify(title,title)['event'],'PUBLIC_INFO_PUBLIC_UTILITY')

    def test_urban_information_is_not_energy_authorization(self):
        title="Anunci d'informació pública sobre el Projecte d'actuació específica de bateries stand-alone Prova, al terme municipal de Prova"
        self.assertEqual(classify(title,title+' La Comissió exposa el projecte esmentat a informació pública.')['event'],'PUBLIC_INFO_LAND_USE')

    def test_changed_document_id_does_not_change_semantic_rule(self):
        one=classify(AUTH,AUTH+' '+GRANT,'123');two=classify(AUTH,AUTH+' '+GRANT,'456')
        self.assertEqual(one['event'],two['event']);self.assertEqual(one['capacity_observations'],two['capacity_observations'])

    def test_nonrenewable_storage_and_subsidy_subjects_are_explicitly_excluded(self):
        for text in ["Resolució sobre emmagatzematge de metalls",'Resolució sobre emmagatzematge, processament i distribució de dades',"Anunci de bases reguladores per mobilitat elèctrica"]:
            r=classify(text,text);self.assertEqual(r['category'],'OUT_OF_SCOPE');self.assertFalse(r['components'])

    def test_correction_reads_replacement_not_retracted_wording(self):
        title="Correcció d'errades d'informe d'impacte ambiental BESS Can Magí"
        body=title+' Al punt primer, on diu: debe someterse a una evaluación de impacto ambiental ordinaria. ha de dir: no debe someterse a una evaluación de impacto ambiental ordinaria. Barcelona, 9 de setembre de 2026'
        r=classify(title,body)
        self.assertEqual(r['event'],'CORRECTION')
        self.assertEqual(r['correction']['corrected_interpretation'],'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA')
        self.assertFalse(r['correction']['automatic_lifecycle_change'])
        self.assertFalse(r['automatic_project_merge'])

    def test_missing_replacement_cannot_be_silently_accepted(self):
        title="Correcció d'errades d'informe d'impacte ambiental BESS Prova"
        self.assertEqual(classify(title,title+' on diu: text anterior')['category'],'REVIEW_REQUIRED')


class QuantitiesTests(unittest.TestCase):
    def test_european_separators_and_explicit_decimal_dot(self):
        for source,expected in [('4.950','4950'),('4,950','4.950'),('7.047,936','7047.936'),('1814.4','1814.4'),('0','0')]:
            self.assertEqual(decimal_number(source),Decimal(expected))

    def test_invalid_or_nonfinite_number_rejected(self):
        for value in ['NaN','-1','inf','1,2,3','']:
            with self.assertRaises(ValueError):decimal_number(value)

    def test_access_power_is_distinct_from_installed_power_and_energy(self):
        r=classify(AUTH,AUTH+' '+GRANT)
        values={(q['basis'],q['normalized_value'],q['normalized_unit']) for q in r['capacity_observations']}
        self.assertIn(('INSTALLED_POWER','5.04','MW'),values)
        self.assertIn(('GRID_ACCESS','4.999','MW'),values)
        self.assertIn(('STORAGE_ENERGY','20.06','MWh'),values)
        self.assertFalse(r['capacity_conflicts'])

    def test_annual_generation_is_not_battery_capacity(self):
        r=classify(ENV,ENV+' 3. Descripció del Projecte Producció anual estimada 9.545.335,80 kWh/any. 4. Consultes '+SCREEN)
        q=next(x for x in r['capacity_observations'] if x['normalized_unit']=='MWh/year')
        self.assertEqual(q['component'],'PV');self.assertEqual(q['basis'],'ANNUAL_GENERATION')
        self.assertNotIn('BESS',r['technologies'])

    def test_apparent_kw_mw_source_typo_not_corrected(self):
        r=classify(ENV,ENV+' 3. Descripció del Projecte Potència: 5,3 MWp. 4. Consultes '+SCREEN)
        self.assertTrue(r['capacity_conflicts'])
        self.assertIsNone(r['components'][0]['capacity_mw'])
        self.assertEqual(r['capacity_observations'][0]['normalized_value'],'0.0053')

    def test_pv_peak_and_nominal_difference_not_automatically_conflict(self):
        title=ENV.replace('5,3 kWn','4 MWn')
        r=classify(title,title+' 3. Descripció del Projecte Potència: 5,3 MWp. 4. Consultes '+SCREEN)
        self.assertFalse(r['capacity_conflicts'])

    def test_law_thresholds_outside_technical_scope_are_not_project_capacity(self):
        r=classify(ENV,ENV+' 2. Marc normatiu instal·lacions de 100 kW a 50 MW. 3. Descripció del Projecte Potència 5,3 MWp. 4. Consultes '+SCREEN)
        self.assertFalse(any(q['source_number'] in ('100','50') for q in r['capacity_observations']))

    def test_unit_device_power_is_not_plant_total(self):
        r=classify(AUTH,AUTH+' '+GRANT.replace('Aquesta Resolució','6 inversors de 210 kW cadascun. Aquesta Resolució'))
        q=next(q for q in r['capacity_observations'] if q['source_number']=='210')
        self.assertEqual(q['basis'],'DEVICE_UNIT_POWER')

    def test_two_year_commissioning_term_never_creates_start_end_dates(self):
        body=AUTH+' '+GRANT+' El termini per a la posada en marxa és de dos anys a comptar de la publicació al Diari Oficial de la Generalitat de Catalunya.'
        r=classify(AUTH,body);self.assertTrue(r['time_terms'])
        self.assertIsNone(r['construction_start_date']);self.assertIsNone(r['construction_end_date'])

    def test_applicant_not_epc_or_bop(self):
        r=classify(AUTH,AUTH+' Persona peticionària: Developer, SL, amb domicili a Prova. '+GRANT)
        self.assertEqual(r['proponent']['value'],'Developer, SL')
        self.assertIsNone(r['epc']);self.assertIsNone(r['bop'])

    def test_references_to_other_plants_are_not_primary_identity(self):
        r=classify(AUTH,AUTH+' '+GRANT+' La línia connecta altres plantes FUE-2025-04391600.')
        self.assertEqual([x['value'] for x in r['primary_references']],['FUE-2025-04391587'])

    def test_zero_capacity_remains_zero_not_missing(self):
        title=AUTH.replace('5,04 MW','0 MW');r=classify(title,title+' '+GRANT)
        self.assertTrue(any(Decimal(q['normalized_value'])==0 for q in r['capacity_observations']))

    def test_no_reported_quantity_is_automatically_summable(self):
        r=classify(AUTH,AUTH+' '+GRANT)
        self.assertTrue(all(q['aggregation_allowed'] is False for q in r['capacity_observations']))

    def test_pure_classifier_has_no_production_or_database_effect(self):
        r=classify(AUTH,AUTH+' '+GRANT)
        self.assertFalse(r['production_enabled']);self.assertEqual(r['database_writes'],0)
        self.assertFalse(r['live_collector_validated']);self.assertFalse(r['field_completeness_certified'])


class ExistingCapacityTests(unittest.TestCase):
    def test_municipal_existing_capacity_is_not_increment(self):
        title="Edicte sobre aprovació definitiva del Projecte d'ampliació d'una instal·lació solar fotovoltaica en autoconsum col·lectiu existent de 20 kW a Bordils"
        row=classify(title,'ADMINISTRACIÓ LOCAL '+title+' Es va aprovar definitivament el projecte.')
        self.assertIn('EXISTING_CAPACITY_IS_NOT_ADDED_CAPACITY',row['flags'])
        self.assertEqual(row['components'][0]['role'],'EXPANSION_WITH_EXISTING_CAPACITY_ONLY')
        self.assertTrue(all(q['basis']=='EXISTING_CAPACITY_NOT_INCREMENT' for q in row['capacity_observations']))
        self.assertIsNone(row['components'][0]['capacity_mw'])

    def test_original_retrieval_date_is_carried_without_redating(self):
        c=candidate(AUTH);c['retrieved_at']='2026-10-05T06:48:14+00:00'
        row=classify_document(c,[{'page':1,'text':AUTH+' '+GRANT}])
        self.assertEqual(row['source_retrieved_at'],c['retrieved_at'])
        self.assertEqual(row['publication_date'],'2026-10-04')
