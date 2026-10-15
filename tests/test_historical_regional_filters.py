import unittest
from app.collectors.docm import EXCLUDE as DOCM_EXCLUDE
from app.collectors.doe import EXCLUDE as DOE_EXCLUDE

class HistoricSourceFilters(unittest.TestCase):
    def test_docm_unauthorized_rooftop(self):
        self.assertRegex(
            "instalación sin autorización de placas fotovoltaicas en edificio de Sigüenza",
            DOCM_EXCLUDE)
        self.assertNotRegex(
            "Autorización de instalación fotovoltaica denominada Solar de Talavera",
            DOCM_EXCLUDE)

    def test_doe_non_energy_notices(self):
        self.assertRegex("Procesos selectivos para el centro de almacenamiento energético", DOE_EXCLUDE)
        self.assertRegex("residuos de construcción y demolición para almacenamiento", DOE_EXCLUDE)
        self.assertNotRegex("Parque eólico Talavera con autorización de construcción", DOE_EXCLUDE)
