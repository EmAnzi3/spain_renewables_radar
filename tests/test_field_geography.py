import sqlite3
import tempfile
import unittest
from pathlib import Path
from app.db import connect
from app.enrichment.ine_municipalities import Municipality
from app.field_geography import _municipal_lookup,audit_site,enrich_municipal_context

CAT=[
 Municipality('Ramiro','47131','Valladolid','Castilla y León'),
 Municipality('Medina del Campo','47085','Valladolid','Castilla y León'),
 Municipality('La Zarza','47145','Valladolid','Castilla y León'),
 Municipality('Santorcaz','28136','Madrid','Madrid'),
 Municipality('Anchuelo','28012','Madrid','Madrid'),
]
def event(text,kind='CONSTRUCTION_AUTH'):
 return {'source_code':'BOE','external_id':'BOE-A-1','publication_date':'2026-09-16',
         'url':'https://www.boe.es/','event_type':kind,'raw_text':text}
def project(province='Valladolid'):
 return {'project_key':'p','project_name':'Elawan Olmedo I',
         'province':province,'ccaa':'Castilla y León'}

class GeoEvidenceTests(unittest.TestCase):
 def test_plant_location_beats_evacuating_line(self):
    source=event('Se autoriza la instalación fotovoltaica «Elawan Olmedo I», '
       'y sus infraestructuras, en los términos municipales de Ramiro y Medina del Campo.')
    line=event('Actas de la línea eléctrica de evacuación de la instalación '
       'fotovoltaica \"Elawan Olmedo I\" en los términos municipales de '
       'Ramiro, La Zarza y Olmedo.','EXPROPRIATION')
    r=audit_site(project(),[source,line],_municipal_lookup(CAT))
    self.assertEqual(r['status'],'DOCUMENTED_MUNICIPAL_CONTEXT')
    self.assertEqual(r['municipalities'],['Medina del Campo','Ramiro'])
    self.assertNotIn('La Zarza',r['municipalities'])

 def test_company_address_is_not_project_location(self):
    e=event('Promotor con domicilio social en Ramiro. '
            'Línea eléctrica de evacuación en Medina del Campo.')
    self.assertEqual(audit_site(project(),[e],_municipal_lookup(CAT))['status'],'UNVERIFIED')

 def test_source_province_and_existing_geo_not_overwritten(self):
    with tempfile.TemporaryDirectory() as td:
      c=connect(str(Path(td)/'x.sqlite'))
      c.execute("""INSERT INTO projects
      (project_key,project_name,technology,province,ccaa,commercial_stage,first_seen,last_seen,latest_event_type)
      VALUES ('p','Elawan Olmedo I','PV','Valladolid','Castilla y León',
      'AUTHORIZED','2026-09-16','2026-09-16','CONSTRUCTION_AUTH')""")
      c.execute("""INSERT INTO events(source_code,external_id,publication_date,title,url,raw_text,
        project_key,event_type,commercial_stage) VALUES('BOE','BOE-A-1',
        '2026-09-16','Rectificación','https://www.boe.es/',
        'Autorización de la instalación fotovoltaica Elawan Olmedo I en los términos municipales de Ramiro y Medina del Campo.',
        'p','CONSTRUCTION_AUTH','AUTHORIZED')""")
      c.commit()
      r=enrich_municipal_context(c,CAT)
      self.assertEqual(r['documented'],1)
      self.assertEqual(enrich_municipal_context(c,CAT)['documented'],0)
      self.assertEqual(c.execute('SELECT province FROM projects').fetchone()[0],'Valladolid')
      geo=c.execute('SELECT municipalities_json,status FROM project_geo_enrichment').fetchone()
      self.assertIn('Medina del Campo',geo['municipalities_json'])
      self.assertEqual(geo['status'],'DOCUMENTED_MUNICIPAL_CONTEXT')
      c.close()

 def test_conflicting_scopes_do_not_invent_a_single_site(self):
    e1=event('Planta fotovoltaica Elawan Olmedo I en el término municipal de Ramiro')
    e2=event('Planta fotovoltaica Elawan Olmedo I en el término municipal de Medina del Campo')
    self.assertEqual(audit_site(project(),[e1,e2],_municipal_lookup(CAT))['status'],'CONFLICT')
