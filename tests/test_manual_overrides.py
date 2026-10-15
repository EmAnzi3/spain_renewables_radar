import tempfile
import unittest
from pathlib import Path

from app.db import connect
from app.manual_overrides import apply, load
from app.parser import parse_event
from app.reporting import write_quality_issues
from app.store import save_event

HEADER = "selector,field,value,evidence_url,note,author,date\n"


class ManualOverridesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.conn = connect(str(root / "t.sqlite")); self.csv = root / "o.csv"
        e = parse_event(source_code="BOA", external_id="007961616", publication_date="2026-10-08",
                        title="Información pública de una instalación híbrida de 28 MW en Zaragoza.",
                        url="https://www.boa.aragon.es/x", raw_text="Instalación híbrida de 28 MW. Zaragoza.")
        save_event(self.conn, e)

    def tearDown(self):
        self.conn.close(); self.tmp.cleanup()

    def test_unnamed_record_is_warning_then_override_fills_it_without_touching_events(self):
        issues, _, _ = write_quality_issues(self.conn, out_dir=Path(self.tmp.name) / "r1")
        self.assertFalse([i for i in issues if i["severity"] == "ERROR"])
        self.assertIn("MISSING_PROJECT_NAME", {i["code"] for i in issues})
        before = self.conn.execute("SELECT title,raw_text,url FROM events").fetchall()
        self.csv.write_text(HEADER + "BOA:007961616,project_name,Hibrido Ejemplo,https://www.boa.aragon.es/x,verificato sull'atto,FC,2026-10-15\n", encoding="utf-8")
        result = apply(self.conn, path=self.csv)
        self.assertEqual((result["applied"], result["unmatched"]), (1, []))
        self.assertEqual(self.conn.execute("SELECT project_name FROM projects").fetchone()[0], "Hibrido Ejemplo")
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in self.conn.execute("SELECT title,raw_text,url FROM events")])
        log = self.conn.execute("SELECT selector,evidence_url,previous_value FROM manual_field_overrides").fetchone()
        self.assertEqual(log[0], "BOA:007961616"); self.assertIsNone(log[2])
        issues, _, _ = write_quality_issues(self.conn, out_dir=Path(self.tmp.name) / "r2")
        self.assertNotIn("MISSING_PROJECT_NAME", {i["code"] for i in issues})

    def test_reapplying_is_idempotent_and_keeps_original_previous_value(self):
        self.csv.write_text(HEADER + "BOA:007961616,power_mw,28.5,https://www.boa.aragon.es/x,,FC,2026-10-15\n", encoding="utf-8")
        apply(self.conn, path=self.csv); apply(self.conn, path=self.csv)
        rows = [tuple(r) for r in self.conn.execute("SELECT value,previous_value FROM manual_field_overrides")]
        self.assertEqual(rows, [("28.5", "28.0")])

    def test_unknown_selector_is_kept_for_later_and_invalid_rows_rejected(self):
        self.csv.write_text(HEADER + "BOE:NOT-YET,project_name,X,https://www.boe.es/x,,,\n", encoding="utf-8")
        self.assertEqual(apply(self.conn, path=self.csv)["unmatched"], ["BOE:NOT-YET"])
        for bad in ("BOA:007961616,epc,Foo,https://x.es,,,\n", "BOA:007961616,project_name,X,,,,\n",
                    "BOA:007961616,power_mw,0,https://x.es,,,\n"):
            self.csv.write_text(HEADER + bad, encoding="utf-8")
            with self.assertRaises(ValueError):
                load(self.csv)


if __name__ == "__main__":
    unittest.main()
