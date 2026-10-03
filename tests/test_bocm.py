import unittest
from pathlib import Path

from app.collectors.bocm import BOCMCollector
from app.parser import parse_event

class BOCMCollectorTests(unittest.TestCase):
    def test_summary_xml_filters_procurement_and_deduplicates(self):
        xml=Path("tests/fixtures/bocm_summary_sample.xml").read_text(encoding="utf-8")
        rows=BOCMCollector.parse_summary_xml(xml)
        self.assertEqual([x["external_id"] for x in rows],["BOCM-20260903-42"])
        self.assertIn("FV Madrid Sur",rows[0]["title"])

    def test_madrid_project_fields(self):
        xml=Path("tests/fixtures/bocm_summary_sample.xml").read_text(encoding="utf-8")
        row=BOCMCollector.parse_summary_xml(xml)[0]
        e=parse_event(
            source_code="BOCM",
            external_id=row["external_id"],
            publication_date="2026-09-03",
            title=row["title"],
            url=row["url_html"],
            raw_text=row["title"]+"\nComunidad de Madrid",
        )
        self.assertEqual(e.technology,"PV")
        self.assertAlmostEqual(e.power_mw,49.8)
        self.assertEqual(e.project_name,"FV Madrid Sur")
        self.assertEqual(e.province,"Madrid")
        self.assertEqual(e.ccaa,"Madrid")
        self.assertEqual(e.event_type,"PUBLIC_INFO")

if __name__=="__main__":
    unittest.main()
