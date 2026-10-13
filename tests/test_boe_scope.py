import unittest
from app.collectors.boe import BOECollector
class OfficialBOEScopeTests(unittest.TestCase):
 def parse(self,title):
  return BOECollector.parse_api_json({'identificador':'BOE-B-2026-99999','titulo':title})
 def test_groundwater_pumps_are_not_battery_projects(self):
  title=('Anuncio de la Comisaría de Aguas de la Confederación Hidrográfica del Júcar '
    'de modificación de la inscripción en el Registro de Aguas de un aprovechamiento '
    'de aguas subterráneas formado por las Baterías nº 1 a nº 7 en Alto Vinalopó')
  self.assertEqual(self.parse(title),[])
 def test_auxiliary_pumping_supply_is_not_a_utility_plant(self):
  title=('Anuncio de sometimiento a información pública del Proyecto 10/25 de '
    'implantación fotovoltaica para suministro complementario a la elevación de '
    'Valdelentisco II (Murcia/Mazarrón).')
  self.assertEqual(self.parse(title),[])
 def test_actual_bess_and_regular_pv_are_not_filtered(self):
  for title in ('Información pública del parque fotovoltaico La Puebla 3, de 150 MW',
                'Autorización del módulo de almacenamiento por baterías BESS Arcos I'):
   with self.subTest(title=title):self.assertEqual(len(self.parse(title)),1)


from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from app.boe_scoping import notice_scope
from app.parser import parse_event

class HistoricalOfficialScopeTests(unittest.TestCase):
 def test_false_positives_from_frozen_historical_boe_titles(self):
  examples=[
   ('Resolución de 23 de enero de 2025, de la Universidad Pública de Navarra, por la que se publica el plan de estudios de Máster Universitario en Energías Renovables: Conversión Eléctrica e Integración en Sistemas Eólicos y Fotovoltaicos.','OUT_OF_SCOPE'),
   ('Anuncio de la Autoridad Portuaria de Tarragona para la ocupación en régimen de concesión administrativa de una nave en el muelle de Castilla, destinada a la manipulación portuaria y almacenaje de graneles, así como para generación de energía fotovoltaica.','OUT_OF_SCOPE'),
   ('Extracto de la Resolución de 27 de enero de 2026, del IDAE, por la que se modifica la primera convocatoria de ayudas para proyectos innovadores de almacenamiento energético.','OUT_OF_SCOPE'),
   ('Extracto de la convocatoria de ayudas a proyectos de producción de baterías y pilas de combustible de hidrógeno del vehículo eléctrico.','OUT_OF_SCOPE'),
   ('Resolución de la Comisión Nacional de los Mercados y la Competencia por la que se emplaza en recurso contencioso-administrativo sobre reconocimiento singular de actuaciones de inversión en relación con las baterías de una subestación.','OUT_OF_SCOPE'),
   ('Sentencia del Tribunal Supremo que estima el recurso contra el régimen al que han de estar sometidas las plantas fotovoltaicas flotantes.','OUT_OF_SCOPE'),
   ('Anuncio de la Comisaría de Aguas sobre autorización para instalación de planta solar fotovoltaica en zona de policía de un barranco.','REVIEW_NON_ENERGY_PERMIT'),
   ('Resolución para la infraestructura de evacuación conjunta de las tres plantas fotovoltaicas de la Isla Peralveche (Mimas Solar, Titán Solar y Dione Solar).','REVIEW_MULTI_ASSET'),
   ('Resolución del proyecto de la instalación de las plantas fotovoltaicas Vallejón y Calera y sus infraestructuras de evacuación.','REVIEW_MULTI_ASSET'),
   ('Anuncio del proyecto Parques Fotovoltaicos Magec I-II-III-IV, de 2 MW, en Telde.','REVIEW_MULTI_ASSET'),
   ('Resolución del proyecto «Parques solares fotovoltaicos Azor Solar de 162,5 MWp y Avutarda Solar de 162,5 MWp» y su infraestructura de evacuación.','REVIEW_MULTI_ASSET'),
  ]
  for title,expected in examples:
   with self.subTest(title=title):
    self.assertEqual(notice_scope(title)[0],expected)
 def test_legal_hybrid_arana_and_single_bolarque_2_not_lost(self):
  titles=[
    ('Se desestima la solicitud de autorización de la instalación híbrida Araña (eólica y solar fotovoltaica), de 72,95 MW de potencia instalada.','Araña'),
    ('Proyecto de la Instalación solar fotovoltaica Bolarque 2 y sus infraestructuras de evacuación (compartidas con Bolarque 1 y Bolarque 3).','Bolarque 2')
  ]
  for i,(title,name) in enumerate(titles):
   with self.subTest(name=name):
    event=parse_event(source_code='BOE',external_id=f'BOE-A-2025-{i}',
      publication_date='2025-03-01',title=title,url='https://www.boe.es/',raw_text=title)
    self.assertEqual(event.project_name,name)
    self.assertEqual(notice_scope(title)[0],'CANDIDATE')
 def test_group_is_full_text_review_lead_not_project(self):
  title=('Convocatoria sobre la infraestructura de evacuación conjunta de las tres '
         'plantas fotovoltaicas de la Isla Peralveche (Mimas Solar, Titán Solar y Dione Solar).')
  body='Texto original completo con referencia 2101/00263 y firmantes oficiales.'
  class Stub(BOECollector):
   def _summary_items(self,day):
    return [{'external_id':'BOE-B-2024-42058','title':title,'url_html':'https://www.boe.es/test'}]
   def _detail_text(self,item):return body,item['url_html']
  with TemporaryDirectory() as td:
   old=Path.cwd()
   import os
   os.chdir(td)
   try:
    c=Stub()
    self.assertEqual(c.collect_day(date(2024,11,18)),[])
    c.persist_metadata(None)
    import json
    out=json.loads(Path('reports/boe/review_leads.json').read_text())
    self.assertEqual(out['lead_count'],1)
    self.assertEqual(out['leads'][0]['raw_text'],body)
    self.assertFalse(out['leads'][0]['added_to_projects'])
   finally:os.chdir(old)
 def test_ordinary_energy_plants_remain_candidates(self):
  for title in (
    'Anuncio de instalación fotovoltaica La Puebla 1, de 59,4 MW para autorización administrativa de construcción.',
    'Anuncio del módulo de almacenamiento mediante baterías BESS La Puebla 3, de 150 MW.',
    'Autorización de proyecto de parque eólico Hernani I de 4,99 MW.'
  ):
   self.assertEqual(notice_scope(title)[0],'CANDIDATE')
