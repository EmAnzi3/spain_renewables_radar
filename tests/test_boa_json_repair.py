import unittest
from datetime import date
from unittest import mock

from app.collectors.boa import BOACollector


class Resp:
    status_code = 200
    def __init__(self, text): self.text = text; self.encoding = None
    def raise_for_status(self): pass


class BOAJsonRepairTests(unittest.TestCase):
    def test_invalid_unicode_escape_is_repaired_not_dropped(self):
        body = '[{"DOCN":"123","Titulo":"Planta fotovoltaica en C:\\uploads y \\x ok \\u00e9"}]'
        c = BOACollector()
        c.session.get = mock.Mock(return_value=Resp(body))
        rows = c._day_rows(date(2025, 6, 25))
        self.assertEqual(rows[0]["DOCN"], "123")
        self.assertIn("\\uploads", rows[0]["Titulo"])
        self.assertTrue(rows[0]["Titulo"].endswith("é"))


if __name__ == "__main__":
    unittest.main()
