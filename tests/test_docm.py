import unittest
from pathlib import Path

from app.collectors.docm import DOCMCollector

class DOCMCollectorTests(unittest.TestCase):
    def test_summary_parser_filters_and_keeps_nid(self):
        html=Path("tests/fixtures/docm_summary_sample.html").read_text(encoding="utf-8")
        rows=DOCMCollector.parse_summary_html(html)
        self.assertEqual(
            [x["external_id"] for x in rows],
            ["DOCM-2026-9991","DOCM-2026-9993"],
        )
        self.assertIn("FV La Sagra",rows[0]["title"])
        self.assertTrue(rows[0]["detail_url"].endswith(
            "verArchivoHtml.do?ruta=2026%2F10%2F02%2Fhtml%2F2026_9991.html&tipo=rutaDocm"
        ))

    def test_excludes_non_energy_chemical_storage(self):
        html='''<div><a href="./descargarArchivo.do?ruta=2026/09/23/pdf/2026_6759.pdf&amp;tipo=rutaDocm">Medio Ambiente</a>,
        Resolución sobre Almacenamiento de productos cosméticos en Toledo. [NID 2026/6759]</div>'''
        self.assertEqual(DOCMCollector.parse_summary_html(html),[])

    def test_terrpower_decimal_comma_name(self):
        from app.parser import parse_event
        title=(
            "Medio Ambiente. Resolución de 22/09/2026, por la que se modifican las condiciones "
            "de la declaración de impacto ambiental del proyecto denominado: Planta solar "
            "fotovoltaica de Terrapower Generación de 44,16 MWp, cuya promotora es la mercantil "
            "Terrapower Generación Híbrida, SL, e infraestructura de evacuación compartida, "
            "en Brazatortas (Ciudad Real), expediente PRO-CR-19-1331."
        )
        e=parse_event(
            source_code="DOCM",external_id="DOCM-2026-6949",publication_date="2026-09-30",
            title=title,url="x",raw_text=title
        )
        self.assertEqual(e.project_name,"Terrapower Generación")
        self.assertAlmostEqual(e.power_mw,44.16)
        self.assertEqual(e.promoter,"Terrapower Generación Híbrida, SL")
        self.assertEqual(e.province,"Ciudad Real")
        self.assertEqual(e.expediente,"PRO-CR-19-1331")

    def test_realistic_event_fields(self):
        html=Path("tests/fixtures/docm_summary_sample.html").read_text(encoding="utf-8")
        row=DOCMCollector.parse_summary_html(html)[0]
        from app.parser import parse_event
        e=parse_event(
            source_code="DOCM",
            external_id=row["external_id"],
            publication_date="2026-10-02",
            title=row["title"],
            url=row["detail_url"],
            raw_text=row["title"],
        )
        self.assertEqual(e.technology,"PV")
        self.assertAlmostEqual(e.power_mw,49.9)
        self.assertEqual(e.project_name,"FV La Sagra")
        self.assertEqual(e.province,"Toledo")
        self.assertEqual(e.ccaa,"Castilla-La Mancha")
        self.assertEqual(e.event_type,"PUBLIC_INFO")

if __name__=="__main__":
    unittest.main()
