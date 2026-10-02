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
