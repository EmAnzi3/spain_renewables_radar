"""Source-backed dismissal is distinct from appeals, allegations and requests."""
import copy
import json
from pathlib import Path
import unittest
from app.collectors.gva_public import classify_current_title, record_fields, event_from_record

FIXTURE=Path(__file__).parent/'fixtures/gva_415857726_denied.json'

class DismissedApplicationTests(unittest.TestCase):
    def test_observed_publication_is_denied_not_early(self):
        f=json.loads(FIXTURE.read_text(encoding='utf-8'))
        fields,flags=record_fields(f['record'])
        for key,value in f['expected'].items():self.assertEqual(fields[key],value)
        self.assertNotIn('SOURCE_LIFECYCLE_UNMAPPED',{flag['code'] for flag in flags})
    def test_full_official_heading_has_same_decision(self):
        f=json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(classify_current_title(f['legal_header']),('DENIED','BLOCKED'))
    def test_original_date_title_and_record_fields_remain_unchanged(self):
        record=json.loads(FIXTURE.read_text(encoding='utf-8'))['record'];before=copy.deepcopy(record)
        event=event_from_record(record)
        for key,value in before.items():self.assertEqual(record[key],value)
        self.assertEqual(event.publication_date,'2026-10-05')
        self.assertEqual(event.event_type,'DENIED')
        self.assertEqual(event.title,before['title'])
        self.assertEqual(json.loads(event.raw_text)['title'],before['title'])
    def test_rule_is_not_keyed_to_company_place_or_document_id(self):
        for words in ('de AAP y AAC','de autorización administrativa previa','de autorización administrativa de construcción'):
            title='OTRO_Resolución del servicio por la que se desestima la solicitud presentada por Empresa Ejemplo, S.L., '+words+', de una planta fotovoltaica.'
            self.assertEqual(classify_current_title(title),('DENIED','BLOCKED'))
    def test_direct_application_dismissal(self):
        title='Resolución por la que se desestima la solicitud de autorización administrativa previa para la planta.'
        self.assertEqual(classify_current_title(title),('DENIED','BLOCKED'))
    def test_appeal_dismissal_is_not_a_denied_plant(self):
        for obj in ('el recurso','las alegaciones','la solicitud de revisión del expediente','la solicitud de ampliación de plazo'):
            title='Resolución por la que se desestima '+obj+' de una planta con AAP y AAC.'
            self.assertEqual(classify_current_title(title),('OTHER','EARLY'))
    def test_public_request_cannot_become_a_denial(self):
        title='Información pública sobre la solicitud de una resolución por la que se desestima la solicitud de AAP.'
        self.assertEqual(classify_current_title(title),('PUBLIC_INFO','EARLY'))
    def test_proposal_conditional_negative_and_uncertain_decisions_are_not_denials(self):
        for phrase in ('se propone desestimar','no se desestima','podría desestimarse','se estudia si se desestima'):
            title='Resolución por la que '+phrase+' la solicitud de AAP y AAC.'
            self.assertEqual(classify_current_title(title),('OTHER','EARLY'))
    def test_older_quoted_predicate_does_not_replace_current_decision(self):
        title='Resolución por la que se modifica un informe relacionado con la resolución por la que se desestima la solicitud de AAP.'
        self.assertEqual(classify_current_title(title),('OTHER','EARLY'))
    def test_rejected_withdrawal_request_does_not_block_granted_permit(self):
        title='Resolución por la que se desestima la solicitud presentada por Empresa, de desistimiento de la AAP y AAC.'
        self.assertEqual(classify_current_title(title),('OTHER','EARLY'))

if __name__=='__main__': unittest.main()
