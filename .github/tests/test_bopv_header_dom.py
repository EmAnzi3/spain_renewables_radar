import unittest
from test_bopv_reconciliation import m,HTML,URL,DAY,FILE

class SidebarHeadingTests(unittest.TestCase):
    def test_observed_sidebar_search_labels_are_not_edition_mastheads(self):
        html='<h2 class="tituGeneral">Consulta</h2><h2 class="tituGeneral">Consulta simple</h2>'+HTML
        self.assertEqual(len(m.parse_summary(html,URL,DAY,FILE)),1)
    def test_two_actual_edition_mastheads_remain_an_error(self):
        html='<h2 class="tituGeneral">Sumario n.º 170, lunes 7 de septiembre de 2026</h2>'+HTML
        with self.assertRaises(ValueError):m.parse_summary(html,URL,DAY,FILE)
