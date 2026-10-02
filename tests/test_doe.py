import unittest
from pathlib import Path

from app.collectors.doe import DOECollector
from app.parser import parse_event

class DOECollectorTests(unittest.TestCase):
    def test_summary_parser_uses_html_disposition_links(self):
        html=Path("tests/fixtures/doe_summary_sample.html").read_text(encoding="utf-8")
        rows=DOECollector.parse_summary_html(html)
        self.assertEqual(
            [r["external_id"] for r in rows],
            ["DOE-2026062441","DOE-2026062021"],
        )
        self.assertIn("Atalaya",rows[0]["title"])
        self.assertTrue(rows[0]["detail_url"].startswith("https://doe.juntaex.es/otrosFormatos/html.php"))

    def test_atalaya_fields(self):
        html=Path("tests/fixtures/doe_summary_sample.html").read_text(encoding="utf-8")
        row=DOECollector.parse_summary_html(html)[0]
        e=parse_event(
            source_code="DOE",external_id=row["external_id"],publication_date="2026-10-01",
            title=row["title"],url=row["detail_url"],raw_text=row["title"]
        )
        self.assertEqual(e.technology,"PV")
        self.assertEqual(e.project_name,"Atalaya")
        self.assertEqual(e.expediente,"IA26/0263")

    def test_cabo_power_and_location(self):
        html=Path("tests/fixtures/doe_summary_sample.html").read_text(encoding="utf-8")
        row=DOECollector.parse_summary_html(html)[1]
        e=parse_event(
            source_code="DOE",external_id=row["external_id"],publication_date="2026-08-06",
            title=row["title"],url=row["detail_url"],raw_text=row["title"]
        )
        self.assertEqual(e.technology,"PV")
        self.assertAlmostEqual(e.power_mw,4.9)
        self.assertEqual(e.province,"Cáceres")
        self.assertEqual(e.ccaa,"Extremadura")

if __name__=="__main__":
    unittest.main()
