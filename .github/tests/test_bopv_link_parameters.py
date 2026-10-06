import unittest
from test_bopv_reconciliation import m

URL=m.HOST+'/web01-bopv/es/bopv2/datos/2026/09/2604004a.shtml'
QUERY='BOPV_NOT_IN_PORTAL&BOPV_HIDE_CALENDAR&R01HNoPortal=true'

class PresentationParametersTests(unittest.TestCase):
    def test_observed_search_display_parameters_keep_same_identity(self):
        self.assertEqual(m.article_id(URL+'?'+QUERY),m.article_id(URL))
        self.assertEqual(m.article_id(URL+'?R01HNoPortal=true&BOPV_HIDE_CALENDAR&BOPV_NOT_IN_PORTAL'),'2026/04004')
    def test_unknown_changed_or_duplicate_parameters_are_not_ignored(self):
        for query in [QUERY+'&documentId=9',QUERY+'&BOPV_NOT_IN_PORTAL',QUERY.replace('true','false'),
                      'documentId=9','BOPV_NOT_IN_PORTAL=another',QUERY.replace('BOPV_HIDE_CALENDAR','UNKNOWN')]:
            with self.subTest(query=query),self.assertRaises(ValueError):m.article_id(URL+'?'+query)
