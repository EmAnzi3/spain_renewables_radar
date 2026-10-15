import json
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from app.collectors.dogv import DOGVCollector

FIX = Path(__file__).parent / "fixtures" / "dogv"
def load(name): return json.loads((FIX / name).read_text(encoding="utf-8"))


class DOGVTests(unittest.TestCase):
    def test_summary_keeps_only_same_day_energy_and_excludes_grants(self):
        items = DOGVCollector.summary_candidates(load("summary_2025_10_01.json"), date(2025, 10, 1))
        self.assertEqual([i["id"] for i in items], ["900001"])
        self.assertEqual(items[0]["url_pdf"], "https://dogv.gva.es/datos/2025/10/01/pdf/2025_99001_es.pdf")

    def test_malformed_summary_fails_closed(self):
        with self.assertRaises(ValueError):
            DOGVCollector.summary_candidates({"cabecera": {}}, date(2025, 10, 1))

    def test_external_id_prefers_official_cve(self):
        self.assertEqual(DOGVCollector.external_id({"id": "1", "codigo": "2025/99001"}, {"cve": "DOGV-2025-99001"}), "DOGV-2025-99001")
        self.assertEqual(DOGVCollector.external_id({"id": "1", "codigo": "2025/99001"}, {"cve": "None"}), "DOGV-2025-99001")

    def _collector(self):
        c = DOGVCollector()
        def fake(path, params):
            if path == "/dogv/calendar": return load("calendar_2025_10.json")
            if path == "/dogv": return load("summary_2025_10_01.json")
            if path == "/disposicion/900001": return load("detail_900001.json")
            raise AssertionError(path)
        c._json = mock.Mock(side_effect=fake)
        return c

    def test_collect_day_parses_event_with_valencian_scope(self):
        events = self._collector().collect_day(date(2025, 10, 1))
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual((e.source_code, e.external_id, e.technology, e.power_mw), ("DOGV", "DOGV-2025-99001", "PV", 49.9))
        self.assertEqual((e.province, e.ccaa), ("Valencia", "Comunitat Valenciana"))
        self.assertTrue(e.promoter.startswith("Ejemplo Solar, SL"))

    def test_day_without_bulletin_is_empty_not_error(self):
        c = self._collector()
        self.assertEqual(c.collect_day(date(2025, 10, 4)), [])
        self.assertEqual([call.args[0] for call in c._json.call_args_list], ["/dogv/calendar"])


if __name__ == "__main__":
    unittest.main()
