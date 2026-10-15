"""Regression of false positives proven in original October 2024 DOCM/DOE acts."""
import unittest
from app.collectors.docm import DOCMCollector, EXCLUDE as DOCM_EXCLUDE
from app.collectors.doe import DOECollector, EXCLUDE as DOE_EXCLUDE
from app.parser import parse_event

ROOFTOP = ("Notificaciones. Notificación de 22/10/2024, de la Delegación Provincial "
           "de Educación, Cultura y Deportes de Guadalajara, en relación al "
           "requerimiento de instalación sin autorización de placas fotovoltaicas "
           "en edificio sito en calle Cuestas, 12 de Sigüenza, Guadalajara")
TRILLO = ("Notificaciones. Notificación de 22/10/2024, de la Delegación Provincial "
          "de Educación, Cultura y Deportes de Guadalajara, en relación a la "
          "resolución de cambio de trazado de línea de la planta fotovoltaica "
          "Trillo Solar 2 infraestructuras de evacuación en los términos "
          "municipales de Cifuentes y Solanillos del Extremo en la provincia "
          "de Guadalajara")
JOBS = (
    "Procesos selectivos.- Anuncio de 24 de octubre de 2024 sobre una oferta de "
    "trabajo (Ref. IS-Ciclado de baterías S8), para el Centro Ibérico de "
    "Investigación en Almacenamiento Energético (CIIAE).")
WASTE = (
    "Información pública.- Anuncio relativo a la instalación de una planta de "
    "gestión, valorización y/o reciclaje y almacenamiento y restauración de "
    "hueco minero de residuos de construcción y demolición en Mérida (Badajoz).")
PV = 'Información pública.- Autorización previa de instalación fotovoltaica "PSFV Talavera" de 30 MW'

class HistoricExclusionTests(unittest.TestCase):
    def test_docm_unauthorized_rooftop_not_a_utility_project(self):
        self.assertRegex(ROOFTOP, DOCM_EXCLUDE)
        self.assertNotRegex(TRILLO, DOCM_EXCLUDE)

    def test_docm_line_routing_explicit_project_name_is_not_synthetic(self):
        event = parse_event(source_code="DOCM", external_id="DOCM-2024-8520",
                            publication_date="2024-10-30", title=TRILLO,
                            url="https://docm.jccm.es/", raw_text=TRILLO)
        self.assertEqual(event.project_name, "Trillo Solar 2")
        self.assertEqual(event.technology, "PV")
        self.assertEqual(event.province, "Guadalajara")
        # Merely naming the plant does not imply grant or construction start.
        self.assertNotEqual(event.event_type, "CONSTRUCTION_START")

    def test_unidentified_pv_not_inferred_from_generic_line_notice(self):
        title = "Resolución de la planta fotovoltaica y infraestructuras de evacuación"
        event = parse_event(source_code="DOCM", external_id="N",
                            publication_date="2024-10-30", title=title,
                            url="https://docm.jccm.es/", raw_text=title)
        self.assertIsNone(event.project_name)

    def test_doe_employment_and_waste_storage_are_not_energy_plants(self):
        self.assertRegex(JOBS, DOE_EXCLUDE)
        self.assertRegex(WASTE, DOE_EXCLUDE)
        self.assertNotRegex(PV, DOE_EXCLUDE)

    def test_doe_title_level_filter_keeps_real_renewable_act(self):
        def html(title, ident):
            return (f'<p>{title}<a href="/otrosFormatos/html.php?xml={ident}&amp;anio=2024">'
                    f'HTML</a></p>')
        source = html(JOBS, "2024081760") + html(WASTE, "2024081010") + html(PV, "2024081767")
        candidates = DOECollector.parse_summary_html(source)
        self.assertEqual([x["external_id"] for x in candidates], ["DOE-2024081767"])

if __name__ == "__main__":
    unittest.main()
