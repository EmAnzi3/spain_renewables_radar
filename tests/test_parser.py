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
        e=parse_event(source_code="BOE",external_id="BOE-A-2026-12701",publication_date="2026-06-11",title="Resolución",url="x",raw_text="Se otorga autorización administrativa previa para la instalación fotovoltaica «FV Guijo», de 91 MW, en Cáceres.")
        self.assertEqual(e.technology,"PV")
        self.assertEqual(e.power_mw,91.0)
        self.assertEqual(e.project_name,"FV Guijo")
        self.assertEqual(e.province,"Cáceres")
        self.assertEqual(e.ccaa,"Extremadura")
        self.assertEqual(e.event_type,"PRIOR_AUTH")
        self.assertEqual(e.commercial_stage,"PERMITTING")

    def test_wind_public_info(self):
        e=parse_event(source_code="BOE",external_id="BOE-B-2026-20000",publication_date="2026-06-11",title="Anuncio",url="x",raw_text="Se somete a información pública el parque eólico «Viento Norte», de 49,5 MW, en Burgos.")
        self.assertEqual(e.technology,"WIND")
        self.assertAlmostEqual(e.power_mw,49.5)
        self.assertEqual(e.event_type,"PUBLIC_INFO")

if __name__=="__main__":unittest.main()
