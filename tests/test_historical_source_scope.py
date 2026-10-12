"""Do not turn groundwater, waste or personnel notices into renewable plants."""
import unittest
from app.collectors.bocm import RELEVANT as MR, EXCLUDE as ME
from app.collectors.docm import RELEVANT as DR, EXCLUDE as DE
from app.collectors.borm import RELEVANT as RR, EXCLUDE as RE
from app.collectors.doe import RELEVANT as ER, EXCLUDE as EE

class SourceScopeRegressionTests(unittest.TestCase):
 def test_multi_plant_zoning_plan_is_not_single_plant_energy_permit(self):
  notice='Plan especial infraestructuras: aprobación definitiva del Plan Especial de Infraestructuras referente a las plantas solares fotovoltaicas de Abeto, Grillete y Cerezo Solar'
  self.assertTrue(MR.search(notice));self.assertTrue(ME.search(notice))
 def test_battery_recycling_is_not_electrical_storage(self):
  notice='Información pública de planta de tratamiento de residuos de pilas y baterías en Azuqueca de Henares'
  self.assertTrue(DR.search(notice));self.assertTrue(DE.search(notice))
 def test_water_pump_auxiliary_pv_is_not_independent_solar_plant(self):
  notice='Proyecto de implantación fotovoltaica para suministro complementario a la elevación de Valdelentisco II'
  self.assertTrue(RR.search(notice));self.assertTrue(RE.search(notice))
 def test_staff_recruitment_is_not_energy_project(self):
  notice='Convocatoria para la cobertura de una plaza de personal científico-investigador para el Centro Ibérico de Investigación en Almacenamiento Energético'
  self.assertTrue(ER.search(notice));self.assertTrue(EE.search(notice))
 def test_real_authorizations_remain_in_scope(self):
  for pattern,excluded in ((MR,ME),(DR,DE),(RR,RE),(ER,EE)):
   text='Se otorga autorización administrativa de construcción para la instalación fotovoltaica Solar del Sur de 42 MW'
   with self.subTest(source=pattern):self.assertTrue(pattern.search(text));self.assertFalse(excluded.search(text))
