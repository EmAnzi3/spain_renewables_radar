"""Regressions for official GVA metadata, never authorization-category inference."""
import unittest
from app.collectors.gva_public import classify_current_title,record_fields
from test_gva_public import record

class GVASourceSemanticsTests(unittest.TestCase):
    def test_abbreviated_cheste_resolution_is_a_closed_proceeding(self):
        title='CHESTE_Res. del STIEMV, por la que se declara a desaparición sobrevenida del objeto de la solicitud presentada por ENERGIA INNOVACION Y DESARROLLO FOTOVOLTAICO S.A. de AAP, AAC y ocupación de VV.PP y DUP, en concreto, y el plan de desmantelamiento y de restauración correspondiente a la CF “EDF 267” de 5 MW de Pins, y su infraestructura de evacuación, sometida a EIA. ATALFE 2022/52/46'
        self.assertEqual(classify_current_title(title),('PROCEDURE_ENDED','BLOCKED'))

    def test_abbreviation_alone_or_request_cannot_create_a_grant(self):
        for title in ['CHESTE_R. STIEM Valencia informa sobre solicitud de AAC',
                      'Información pública: CHESTE_Res. declara desaparición sobrevenida del objeto',
                      'R. STIEM Valencia comunica la solicitud de declaración de pérdida sobrevenida']:
            self.assertIn(classify_current_title(title)[1],{'EARLY','PERMITTING'})

    def test_exact_province_category_fills_gap_without_grant_inference(self):
        row=record('PICASSENT_Anuncio de información pública de la central fotovoltaica hibridada “Espioca Solar y BESS Espioca Power”. Expediente ATALFE/2023/63/46')
        row['categories']=['Energias renovables','Valencia','Instalaciones autorizadas']
        fields,_=record_fields(row)
        self.assertEqual(fields['province'],'Valencia')
        self.assertEqual(fields['commercial_stage'],'EARLY')
        self.assertEqual(fields['event_type'],'PUBLIC_INFO')
        self.assertEqual(fields['evidence']['province_origin'],'official_geographic_category')

    def test_category_does_not_overwrite_explicit_source_province(self):
        row=record('Resolución por la que se otorga a Demo SL AAC para CF denominada “Demo”, en el término municipal de Alicante. ATALFE/2023/17/03')
        row['categories']=['Valencia','Instalaciones autorizadas']
        fields,flags=record_fields(row)
        self.assertEqual(fields['province'],'Alicante')
        self.assertIn('SOURCE_PROVINCE_DISAGREEMENT',{f['code'] for f in flags})

    def test_multiple_categories_or_incidental_text_is_not_single_province(self):
        for categories in [['Valencia','Alicante'],['Valencia Solar SL'],['Comunitat Valenciana']]:
            row=record('Anuncio de información pública de central fotovoltaica denominada “Demo”. ATALFE/2023/15')
            row['categories']=categories
            fields,_=record_fields(row)
            self.assertIsNone(fields['province'])

if __name__=='__main__':unittest.main()
