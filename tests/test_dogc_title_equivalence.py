"""Display-only comparison retains original titles and substantive differences."""
import copy
import unittest
from scripts.reconcile_dogc_daily import comparison_title, compare_indexes, require_same_index

class TitleEquivalenceTests(unittest.TestCase):
    def pair(self, a, b):
        key=('1053764','2026-09-07')
        return {key:{'title':a}}, {key:{'title':b}}

    def test_observed_catalan_apostrophes_are_equivalent(self):
        left,right=self.pair("l'Acord d'informe (4,80 MW)", "l’Acord d’informe (4,80 MW)")
        originals=copy.deepcopy((left,right))
        require_same_index(left,right)
        diff=compare_indexes(left,right)
        self.assertEqual(len(diff['typographic_variants']),1)
        self.assertFalse(diff['title_conflicts'])
        self.assertEqual((left,right),originals)

    def test_numeric_change_remains_a_conflict(self):
        left,right=self.pair("d'instal·lació 4,80 MW", "d’instal·lació 4,81 MW")
        with self.assertRaises(ValueError):require_same_index(left,right)

    def test_decision_and_reference_changes_are_not_typography(self):
        for a,b in [("s'atorga", "es denega"),("FUE-2023-03606263", "FUE-2024-03606263")]:
            with self.assertRaises(ValueError):require_same_index(*self.pair(a,b))

    def test_typography_does_not_erase_punctuation_case_or_accents(self):
        for a,b in [("A-B","AB"),("Eòlic","Eolic"),("MW","mw"),("4,80","480"),("d'obra","dobra")]:
            self.assertNotEqual(comparison_title(a),comparison_title(b))

    def test_unicode_composition_and_quote_shape_only(self):
        self.assertEqual(comparison_title('“Eòlic”'), comparison_title('"Eo\u0300lic"'))
