"""Source-shape fixtures and legal wording observed in official GVA probes.

References: inventory 37186210816, original acts 37186563752, text audit
37190420365. Test excerpts omit unrelated parts; no live network in unit tests.
"""
import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from app.collectors.gva_public import (
    BASE,GVAPublicCollector,act_header,classify_current_title,decimal_es,
    event_from_record,explicit_name,official_url,page_url,parse_listing,power_candidates,record_fields,
)


def record(title,text='',ident='415584926'):
    return {'external_id':ident,'title':title,'publication_date':'2026-09-29',
            'url':BASE+'?_pub_assetEntryId='+ident,
            'legal_documents':[{'url':'https://mediambient.gva.es/documents/resolucion.pdf','text':text}] if text else []}


def listing(first=1,last=1,total=2,ident='415641871',published='30/09/2026'):
    return f'''<div class="taglib-page-iterator">Mostrando {first} - {last} de {total} resultados
    <a href="{BASE}?_pub_cur=2&amp;_pub_delta=1">Siguiente</a></div>
    <div class="asset-abstract"><div class="asset-title"><a href="{BASE}?_pub_assetEntryId={ident}">Resolución “MSP1 Pinella 3”</a></div>
    <span class="metadata-publish-date">{published}</span><div class="asset-summary">Texto público</div></div>'''


class GVAHelpersTests(unittest.TestCase):
    def test_pagination_and_actual_web_publication_are_preserved(self):
        rows,bounds,route=parse_listing(listing(),BASE)
        self.assertEqual(bounds,(1,1,2));self.assertEqual(rows[0]['publication_date'],'2026-09-30')
        self.assertEqual(rows[0]['external_id'],'415641871')
        self.assertIn('_pub_cur=3',page_url(route,3));self.assertIn('_pub_delta=1',page_url(route,3))

    def test_missing_pagination_or_date_is_not_empty_success(self):
        for text in ['<html>maintenance</html>',listing().replace('metadata-publish-date','other-date'),listing(last=2)]:
            with self.assertRaises(ValueError):parse_listing(text,BASE)

    def test_duplicate_identity_is_a_structural_error(self):
        text=listing(last=2)+'<div class="asset-abstract">'+listing().split('<div class="asset-abstract">',1)[1]
        with self.assertRaises(ValueError):parse_listing(text,BASE)

    def test_unknown_or_non_https_hosts_are_not_contacted(self):
        for url in ['http://mediambient.gva.es/x','https://mediambient.gva.es.evil.invalid/x','https://user:pass@mediambient.gva.es/x']:
            with self.assertRaises(ValueError):official_url(url)
        self.assertEqual(official_url(BASE),BASE)

    def test_spanish_kw_thousands_and_mw_decimals(self):
        self.assertEqual(decimal_es('2.640'),2640);self.assertEqual(decimal_es('47,125'),47.125)
        self.assertEqual(power_candidates('potencia instalada 2.640 kW')[0]['value_mw'],2.64)
        self.assertEqual(power_candidates('potencia instalada 0,49695 MW')[0]['value_mw'],.49695)
        self.assertEqual(power_candidates('baterías de 10,00 MWh'),[])

    def test_access_capacity_is_not_installed_power(self):
        self.assertEqual(power_candidates('de 5 MW de capacidad de acceso concedida')[0]['basis'],'grid_access')

    def test_pv_battery_and_access_bases_are_separate(self):
        values=power_candidates('Pico 7,172 MWp, Pnom. inversores: 5 MW, Pmáx. almacenamiento BESS: 5MW y CA concedida: 5 MW')
        self.assertEqual([x['basis'] for x in values],['pv_peak','pv_inverters','storage_module','grid_access'])

    def test_structured_name_is_read_from_explicit_act_field(self):
        self.assertEqual(explicit_name('Denominación Instalación: PSF PIRAMIDE - Tecnología: fotovoltaica'),'PSF PIRAMIDE')
        self.assertEqual(explicit_name('Denominación de la instalación: PSF TERRABONA • Tecnología: fotovoltaica'),'PSF TERRABONA')
        self.assertIsNone(explicit_name('promovida por Developer Solar S.L.'))

    def test_header_does_not_include_antecedent_power(self):
        self.assertEqual(act_header('Baterías 4,8 MW. ANTECEDENTES Planta existente 5,55 MW'),'Baterías 4,8 MW. ')

    def test_grant_request_denial_withdrawal_and_procedural_end(self):
        cases=[('Resolución por la que se otorga a Demo SL AAP y AAC',('CONSTRUCTION_AUTH','AUTHORIZED')),
               ('Anuncio de información pública de solicitud de AAC',('PUBLIC_INFO','EARLY')),
               ('Resolución que acepta el desistimiento de solicitud de AAP/AAC',('WITHDRAWN','BLOCKED')),
               ('Resolución por la que se deniega la autorización de construcción',('DENIED','BLOCKED')),
               ('Res. por la que se declara la desaparición sobrevenida del objeto de la solicitud de AAC',('PROCEDURE_ENDED','BLOCKED')),
               ('Resolución de terminación procedimiento de tramitación de autorización',('PROCEDURE_ENDED','BLOCKED'))]
        for text,expected in cases:self.assertEqual(classify_current_title(text),expected)

    def test_request_for_grant_or_quote_of_past_decision_cannot_become_permit(self):
        cases=['Resolución que admite solicitud de otorgamiento de AAC','Solicitud de AAC: se otorga a Demo SL autorización',
               'Anuncio de información pública: resolución histórica por la que se otorga a Demo SL AAC','Resolución: no se otorga a Demo SL la AAC']
        for text in cases:self.assertNotEqual(classify_current_title(text)[1],'AUTHORIZED')

    def test_failed_archive_is_not_retried_thirty_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector=GVAPublicCollector(out_dir=tmp);collector._get=Mock(return_value=(b'<html>maintenance</html>',BASE))
            for day in (date(2026,10,1),date(2026,10,2)):
                with self.assertRaises((ValueError,RuntimeError)):collector.collect_day(day)
            collector._get.assert_called_once();self.assertFalse(collector.audit['complete'])


class GVAFieldTests(unittest.TestCase):
    def test_observed_picassent_discrepancy_leaves_power_unknown(self):
        title='PICASSENT_ Resolución STIEM Valencia que acepta el desistimiento de solicitud y se declara la terminación del procedimiento AAP/AAC, de la instalación producción de energía eléctrica de 4 MW de potencia por VIII FONTIVSOLAR, S.L. Expediente: ATALFE/2023/3/46.'
        doc='Resolución de la instalación fotovoltaica denominada "PSFV PICASSENT", de 4,824 MW de potencia instalada. ANTECEDENTES Se solicitó autorización.'
        fields,flags=record_fields(record(title,doc))
        self.assertEqual(fields['commercial_stage'],'BLOCKED');self.assertEqual(fields['project_name'],'PSFV PICASSENT')
        self.assertIsNone(fields['power_mw']);self.assertIn('SOURCE_POWER_DISAGREEMENT',{x['code'] for x in flags})
        self.assertEqual(fields['expediente'],'ATALFE/2023/3/46')

    def test_existing_pv_power_not_attached_to_new_bess_module(self):
        title='Resolución del ST de Industria, Energía y Minas de Castellón, por la que se otorga a BEAVIER PHOTO POWER, S.L., autorización administrativa previa y de construcción, para hibridación con sistema de almacenamiento con baterías, de planta fotovoltaica existente “PFV BURRIANA I”, en Burriana (Castellón), denominada “Hibridación PFV BURRIANA I”. Expediente ATREGI/2025/31/12'
        doc='Resolución para hibridación con baterías de 4,8 MW de potencia instalada. ANTECEDENTES Planta fotovoltaica existente de 5,55 MW de potencia instalada.'
        fields,_=record_fields(record(title,doc))
        self.assertEqual(fields['power_mw'],4.8);self.assertEqual(fields['technology'],'HYBRID')
        self.assertEqual(fields['project_name'],'Hibridación PFV BURRIANA I');self.assertEqual(fields['event_type'],'CONSTRUCTION_AUTH')

    def test_hybrid_components_are_not_summed_as_one_capacity(self):
        title='PICASSENT_Anuncio se someten información pública solicitudes AAP/AAC y ocupación vías pecuarias, correspondientes central fotovoltaica hibridada « Inst. Fotovoltaica Espioca Solar y BESS Espioca Power» e infraestructura evacuación; con Pmáx. módulos fotovoltaicos bifaciales (pico): 7,172 MWp, Pnom. inversores: 5 MW, Pmáx. almacenamiento BESS: 5MW y CA concedida: 5 MW. Expediente ATALFE/2023/63/46'
        fields,flags=record_fields(record(title))
        self.assertEqual(fields['technology'],'HYBRID');self.assertIsNone(fields['power_mw'])
        self.assertEqual(len(fields['evidence']['power_assertions']),4)
        self.assertIn('MULTI_COMPONENT_POWER_NOT_SUMMED',{x['code'] for x in flags})

    def test_access_only_power_not_used_even_for_blocked_project(self):
        title='Resolución por la que se acepta el desistimiento de solicitud correspondiente a instalación FV: “ISF El Fondo Benifaió Solar”, de 5 MW de capacidad de acceso concedida, promovida por ENERGIA OCASUS, S.L.U. ATALFE/2022/46/46.'
        fields,_=record_fields(record(title));self.assertIsNone(fields['power_mw']);self.assertEqual(fields['event_type'],'WITHDRAWN')

    def test_image_only_act_does_not_block_clear_title_evidence(self):
        row=record('Resolución por la que se otorga a HUERTO SOLAR CUZCO, S.L., AAP, AAC para CF, de pot inst 1,6 MW, denominada “FV CUZCO”, en Pilar de la Horadada (Alicante). ATALFE/2023/3/03.')
        row['legal_documents']=[{'url':'https://mediambient.gva.es/x.pdf','text':'','text_status':'IMAGE_OR_NO_TEXT'}]
        fields,flags=record_fields(row);self.assertEqual(fields['power_mw'],1.6)
        self.assertEqual(fields['project_name'],'FV CUZCO');self.assertEqual(fields['province'],'Alicante')
        self.assertIn('LEGAL_ACT_IMAGE_ONLY',{x['code'] for x in flags})

    def test_grid_only_documents_are_inventory_not_generation(self):
        row=record('Resolución de otorgamiento a SOLAER ENERGÍAS BAHÍA BLANCA, S.L., AAP, AAC para una subestación “S.T. PROMOTORES NOVELDA” y línea de 220 kV.')
        self.assertIsNone(event_from_record(row));self.assertEqual(row['extraction']['disposition'],'GRID_CONTEXT_ONLY')

    def test_raw_source_kept_and_replay_does_not_duplicate_or_mutate_core(self):
        from app.db import connect
        from app.store import save_event
        row=record('Resolución por la que se otorga a FASTIGHETSBYRAN TORREVIEJA, S.L., AAC para CF, en Los Montesinos (Alicante) potencia instalada 0,49695 MW, denominada “LAS CASICAS”. ATALFE/2023/14/03.')
        original=copy.deepcopy(row);event=event_from_record(row)
        for key,value in original.items():self.assertEqual(json.loads(event.raw_text)[key],value)
        with tempfile.TemporaryDirectory() as tmp:
            con=connect(str(Path(tmp)/'test.sqlite'))
            self.assertEqual(save_event(con,event),(True,True));self.assertEqual(save_event(con,event),(False,False))
            self.assertEqual(con.execute('SELECT count(*) FROM projects').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT count(*) FROM events').fetchone()[0],1);con.close()


if __name__=='__main__':unittest.main()
