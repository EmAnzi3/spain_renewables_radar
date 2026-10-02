import unittest
from pathlib import Path

from app.collectors.boe import BOECollector
from app.parser import parse_event

class ParserTests(unittest.TestCase):
    def test_boe_summary_filters(self):
        html=Path("tests/fixtures/boe_summary_sample.html").read_text(encoding="utf-8")
        got=BOECollector.parse_summary_html(html)
        self.assertEqual({x["external_id"] for x in got},{"BOE-A-2026-12701","BOE-B-2026-20000"})

    def test_pv_auth(self):
        e=parse_event(
            source_code="BOE",external_id="BOE-A-2026-12701",publication_date="2026-06-11",
            title="Resolución",url="x",
            raw_text="Se otorga autorización administrativa previa para la instalación fotovoltaica «FV Guijo», de 91 MW, en Cáceres."
        )
        self.assertEqual(e.technology,"PV")
        self.assertEqual(e.power_mw,91.0)
        self.assertEqual(e.project_name,"FV Guijo")
        self.assertEqual(e.province,"Cáceres")
        self.assertEqual(e.ccaa,"Extremadura")
        self.assertEqual(e.event_type,"PRIOR_AUTH")
        self.assertEqual(e.commercial_stage,"PERMITTING")

    def test_wind_public_info_with_promoter_and_code(self):
        e=parse_event(
            source_code="BOE",external_id="BOE-B-2026-31657",publication_date="2026-09-30",
            title="Anuncio",url="x",
            raw_text="Se somete a Información Pública la solicitud de Declaración de Impacto Ambiental y Autorización Administrativa Previa de la instalación Parque Eólico «Vientos del Cid I» de 78 MW de potencia instalada, en la provincia de Burgos; promovida por la mercantil «Ener Epsilon, S.L.». código PEol-1024."
        )
        self.assertEqual(e.technology,"WIND")
        self.assertAlmostEqual(e.power_mw,78.0)
        self.assertEqual(e.project_name,"Vientos del Cid I")
        self.assertEqual(e.promoter,"Ener Epsilon, S.L")
        self.assertEqual(e.expediente,"PEol-1024")
        self.assertEqual(e.event_type,"DIA")

    def test_expropriation_is_preconstruction(self):
        e=parse_event(
            source_code="BOE",external_id="BOE-B-2026-31854",publication_date="2026-10-02",
            title="Anuncio",url="x",
            raw_text='Se convoca para el levantamiento de actas previas a la ocupación de bienes y derechos afectados por la línea eléctrica que forma parte de las infraestructuras de evacuación de la instalación fotovoltaica "Elawan Olmedo I", de 50,064 MW de potencia instalada, en Valladolid.'
        )
        self.assertEqual(e.technology,"PV")
        self.assertAlmostEqual(e.power_mw,50.064)
        self.assertEqual(e.event_type,"EXPROPRIATION")
        self.assertEqual(e.commercial_stage,"PRECONSTRUCTION")
        self.assertEqual(e.province,"Valladolid")

if __name__=="__main__":
    unittest.main()
