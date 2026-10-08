"""Frozen official-wording fixtures: no inference from names, suppliers or grid lines."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from app.db import connect
from app.field_integrity import (
    company_mentions, promoter_status, explicit_capacity_corrections,
    audit_project, apply_verified_field_repairs,
)
from app.parser import ParsedEvent
from app.store import save_event

ELAWAN = ('Por resolución se otorgó a la sociedad Elawan Energy Olmedo 1, S.L. '
    'la autorización administrativa de construcción para la instalación fotovoltaica '
    '"Elawan Olmedo I", de 50,064 MW de potencia instalada. '
    'La potencia instalada de la instalación es de 50,064 MW, debiendo ser de 49,61 MW.')
COLLARADA = ('Se otorgó a Collarada Solar, S.L.U., autorización de construcción '
    'para la instalación fotovoltaica Collarada Solar, de 50,24 MW. '
    'Se otorgó a Popa Solar, S.L.U., autorización de construcción para la '
    'instalación fotovoltaica Popa Solar, de 61,12 MW. '
    'Se otorgó a Maladeta Solar, S.L.U., autorización de construcción para la '
    'instalación fotovoltaica Maladeta Solar.')
MAZO = ('Otorgar a Inver Generación 2, S.L., autorización administrativa previa '
    'para la instalación BESS Mazo. La empresa productora, dispone de capacidad '
    'legal, técnica y económico-financiera para la realización del proyecto.')

def event(name, raw, *, code='BOE-A-2026-TEST', kind='CONSTRUCTION_AUTH'):
    return ParsedEvent(
        'BOE', code, '2026-09-16', 'Corrección de errores de '+name,
        'https://www.boe.es/diario_boe/txt.php?id='+code, raw, 'PV', 50.064,
        name, None, None, 'Valladolid','Castilla y León', kind,'AUTHORIZED','scoped-test-key')

class FieldReviewTests(unittest.TestCase):
    def test_project_linked_company_in_multi_plant_announcement(self):
        p={'project_key':'p','project_name':'Collarada Solar','promoter':None,'power_mw':50.24}
        e={'raw_text':COLLARADA,'title':'Anuncio Collarada Solar','source_code':'BOE',
           'external_id':'BOE-X','publication_date':'2026-09-18','url':'https://www.boe.es/'}
        r=audit_project(p,[e])
        self.assertEqual(r['company_proposal'],'Collarada Solar, S.L.U')
        self.assertTrue(any(x['role'].endswith('_PROJECT_LINKED') for x in r['company_evidence']))
        self.assertEqual(len(r['company_candidates']),3)

    def test_same_group_does_not_assign_popa_to_collarada(self):
        p={'project_key':'p','project_name':'Collarada Solar','promoter':None,'power_mw':50.24}
        e={'raw_text':'Se otorgó a Popa Solar, S.L.U., autorización para Popa Solar',
           'title':'Collarada y Popa','source_code':'BOE','external_id':'BOE-Y',
           'publication_date':'2026-09-18','url':'https://www.boe.es/'}
        r=audit_project(p,[e])
        # A single unrelated company in a grouped act is not sufficient.
        self.assertFalse(any(x['role'].endswith('_PROJECT_LINKED') for x in r['company_evidence']))

    def test_junk_company_fragment_is_not_accepted(self):
        self.assertEqual(promoter_status('productora, dispone de capacidad legal, técnica y económico-financiera'),'REVIEW_REQUIRED')
        self.assertEqual(promoter_status('Inver Generación 2, S.L.'),'LEGAL_NAME_FORMAT')
        self.assertEqual(company_mentions('La empresa productora, dispone de capacidad legal.'),[])

    def test_rectification_not_first_obsolete_mw(self):
        fixes=explicit_capacity_corrections(ELAWAN)
        self.assertEqual([(old,e.value) for old,e in fixes],[(50.064,'49.61')])
        self.assertEqual(explicit_capacity_corrections('50,064 MWp de paneles; 49,61 MWh batería'),[])
        self.assertEqual(explicit_capacity_corrections('Potencia instalada es de 1.000 MW, debiendo ser de 900 MW'),[])

    def test_multi_component_conflicts_stay_unresolved(self):
        p={'project_key':'p','project_name':'Elawan Olmedo I','power_mw':50.064,'promoter':None}
        e={'title':'Rectificación','raw_text':ELAWAN+'\nLa potencia instalada es de 10 MW, debiendo ser de 11 MW.',
           'source_code':'BOE','external_id':'BOE-C','publication_date':'2026-09-16','url':'https://www.boe.es/'}
        r=audit_project(p,[e])
        self.assertTrue(r['power_conflict'])
        self.assertIsNone(r['installed_power_proposal'])

    def test_correct_just_two_project_fields_and_preserve_immutable_source(self):
        with tempfile.TemporaryDirectory() as temp:
            c=connect(str(Path(temp)/'radar.sqlite'))
            original=event('Elawan Olmedo I',ELAWAN)
            save_event(c,original)
            before=tuple(c.execute('SELECT source_code,external_id,publication_date,title,url,raw_text,project_key,event_type,commercial_stage FROM events').fetchone())
            result=apply_verified_field_repairs(c)
            self.assertEqual((result['promoters'],result['power_mw']),(1,1))
            record=c.execute('SELECT * FROM projects').fetchone()
            self.assertEqual((record['promoter'],record['power_mw']),('Elawan Energy Olmedo 1, S.L',49.61))
            self.assertEqual(tuple(c.execute('SELECT source_code,external_id,publication_date,title,url,raw_text,project_key,event_type,commercial_stage FROM events').fetchone()),before)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM project_field_repair_audit').fetchone()[0],2)
            self.assertEqual(apply_verified_field_repairs(c)['changed_fields'],0)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            c.close()

    def test_individual_company_and_source_evidence_are_kept(self):
        with tempfile.TemporaryDirectory() as temp:
            c=connect(str(Path(temp)/'radar.sqlite'))
            save_event(c,event('BESS Mazo',MAZO,code='BOE-A-2026-MAZO'))
            c.execute('UPDATE projects SET promoter=?',(
                'productora, dispone de capacidad legal, técnica y económico-financiera',))
            c.commit()
            result=apply_verified_field_repairs(c)
            self.assertEqual(result['promoters'],1)
            self.assertEqual(c.execute('SELECT promoter FROM projects').fetchone()[0],'Inver Generación 2, S.L')
            row=c.execute('SELECT * FROM project_field_repair_audit').fetchone()
            self.assertEqual(row['external_id'],'BOE-A-2026-MAZO')
            self.assertEqual(row['role'],'GRANTEE_PROJECT_LINKED')
            c.close()
