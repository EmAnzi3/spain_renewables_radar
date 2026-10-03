import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from app.collectors.sabia import SABIACollector, parse_detail_html, parse_search_html
from test_sabia import MUEL_DETAIL, CIUDAD_RODRIGO_DETAIL, CLAVELLINAS_DETAIL, SEARCH_HTML


class SABIAHardeningTests(unittest.TestCase):
    def test_empty_fields_do_not_consume_following_sections(self):
        for html in (CIUDAD_RODRIGO_DETAIL, CLAVELLINAS_DETAIL):
            d = parse_detail_html(html)
            self.assertIsNone(d['municipality'])
            self.assertIsNone(d['resolution_sense'])
            self.assertIsNone(d['resolution_date'])
            self.assertIsNone(d['authorization_date'])

    def test_substantive_authority_not_confused_with_code_label(self):
        d = parse_detail_html(MUEL_DETAIL)
        self.assertTrue(d['substantive_body'].startswith('D.G.'))
        self.assertNotIn('PFOT-150', d['substantive_body'])
        self.assertEqual(d['substantive_code'], 'PFOT-150')

    def test_unrecognized_success_page_is_not_zero_results(self):
        with self.assertRaisesRegex(RuntimeError, 'table missing'):
            parse_search_html('<html><body>Buscador de proyectos</body></html>', 'FTV')

    def test_truncated_index_row_is_structural_error(self):
        with self.assertRaisesRegex(RuntimeError, 'Malformed'):
            parse_search_html('<table id="tablaResultados"><tr><td>20260111</td><td>Incomplete</td></tr></table>', 'FTV')

    def test_new_pagination_is_not_silently_ignored(self):
        with self.assertRaisesRegex(RuntimeError, 'pagination'):
            parse_search_html(SEARCH_HTML + '<a href="?page=2">Siguiente</a>', 'FTV')

    def test_later_states_not_filtered_from_inventory(self):
        rows = parse_search_html(SEARCH_HTML.replace('CONSULTAS PREVIAS', 'PROYECTO AUTORIZADO'), 'FTV')
        self.assertEqual(rows[0]['state'], 'PROYECTO AUTORIZADO')

    def test_failed_snapshot_does_not_repeat_every_day(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SABIA_CACHE_DIR': tmp}):
            collector = SABIACollector()
            collector._fatal_error = 'deliberate incomplete snapshot'
            with patch.object(collector, '_load_candidates') as load:
                for day in (date(2026,10,1), date(2026,10,2)):
                    with self.assertRaisesRegex(RuntimeError, 'incomplete snapshot'):
                        collector.collect_day(day)
                load.assert_not_called()

    def test_all_five_type_queries_have_no_state_filter(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SABIA_CACHE_DIR': tmp}):
            collector = SABIACollector()
            for index, kind in enumerate(('FTV','EOL','EOM','HIB','ALM')):
                (collector.cache_dir / (kind + '-index.html')).write_text(
                    SEARCH_HTML.replace('20260236', '20260' + str(100 + index)), encoding='utf-8')
            with patch.object(collector, '_session') as network:
                self.assertEqual(len(collector._load_candidates()), 5)
                network.assert_not_called()
            self.assertEqual(len(collector.audit['queries']), 5)
            self.assertTrue(all(q['state_filter'] is None for q in collector.audit['queries']))

if __name__ == '__main__':
    unittest.main()
