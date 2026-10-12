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
