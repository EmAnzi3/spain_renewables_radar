"""Synthetic fixtures: they validate contracts, not live source coverage."""
import copy
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.reconcile_dogc_daily import (
    DAILY_LIMIT, daily_parameters, parse_complete_day, require_same_index,
    semantic_index, verify_originals, window_days,
)
from scripts.audit_dogc_index import parse_summary

DAY = date(2026, 9, 8)


def row(identity='1'):
    return {'idDocument': identity, 'date': '08/09/2026', 'tipusDiari': 'DOGC',
            'title': 'Resolució de prova', 'linkTitle': '?action=fitxa&documentId=' + identity}


def response(n=1):
    return {'numResultSearch': n, 'resultSearch': [row(str(i)) for i in range(n)]}


def summary():
    return {'sumaris': [{'numDOGC': '9747', 'dateDOGC': '08/09/2026', 'title': 'DOGC 9747',
        'linkDownloadDOGCPDF': 'https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?dogcId=9747&language=ca_ES',
        'section': [{'document': [{'title': 'Resolució de prova', 'linkDownloadDocumentPDF':
            'https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?documentId=0&type=01&language=ca_ES'}]}]}]}


class DailyIndexTests(unittest.TestCase):
    def test_disjoint_daily_query_keeps_all_states(self):
        q = daily_parameters(DAY)
        self.assertEqual(q['publicationDateInitial'], q['publicationDateFinal'])
        self.assertEqual(q['numResultsByPage'], str(DAILY_LIMIT))
        self.assertEqual(q['page'], '1')
        self.assertFalse(q['current'])
        self.assertEqual(q['value'], '')
        self.assertEqual(q['sectionDOGC'], [])

    def test_entire_day_larger_than_old_page_is_retained(self):
        self.assertEqual(len(parse_complete_day(response(101), DAY)), 101)

    def test_ignored_page_size_cannot_be_certified(self):
        data = response(101); data['resultSearch'] = data['resultSearch'][:50]
        with self.assertRaisesRegex(ValueError, 'Incomplete daily'):
            parse_complete_day(data, DAY)

    def test_same_count_with_duplicate_is_not_complete(self):
        data = response(2); data['resultSearch'][1] = copy.deepcopy(data['resultSearch'][0])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            parse_complete_day(data, DAY)

    def test_wrong_publication_date_is_not_replaced(self):
        data = response(); data['resultSearch'][0]['date'] = '07/09/2026'
        with self.assertRaises(ValueError): parse_complete_day(data, DAY)

    def test_foreign_journal_or_link_is_rejected(self):
        for field, value in [('tipusDiari', 'BOE'), ('linkTitle', 'https://elsewhere.invalid/?documentId=0'), ('linkTitle', '?documentId=9')]:
            data = response(); data['resultSearch'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): parse_complete_day(data, DAY)

    def test_unknown_count_and_boolean_are_not_zero(self):
        for value in [None, True, '1', -1, DAILY_LIMIT + 1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_complete_day({'numResultSearch': value, 'resultSearch': []}, DAY)

    def test_application_error_is_not_empty_success(self):
        for data in [{'error': True, 'numResultSearch': 0}, {'errorCode': 'failure', 'numResultSearch': 0}]:
            with self.assertRaises(ValueError): parse_complete_day(data, DAY)

    def test_explicit_zero_allows_absent_or_null_array(self):
        self.assertEqual(parse_complete_day({'numResultSearch': 0}, DAY), {})
        self.assertEqual(parse_complete_day({'numResultSearch': 0, 'resultSearch': None}, DAY), {})
        self.assertEqual(parse_complete_day(response(0), DAY), {})

    def test_zero_cannot_hide_a_nonempty_array(self):
        data = response(); data['numResultSearch'] = 0
        with self.assertRaises(ValueError): parse_complete_day(data, DAY)

    def test_original_source_fields_and_noncurrent_rows_are_kept(self):
        data = response(); data['resultSearch'][0].update(current=False, additional='preserved')
        parsed = parse_complete_day(data, DAY)
        self.assertEqual(next(iter(parsed.values()))['source_record'], data['resultSearch'][0])

    def test_missing_or_markup_only_title_fails(self):
        for value in [None, '', '<i></i>']:
            data = response(); data['resultSearch'][0]['title'] = value
            with self.assertRaises(ValueError): parse_complete_day(data, DAY)

    def test_missing_extra_and_different_titles_fail(self):
        one = parse_complete_day(response(), DAY)
        changed = copy.deepcopy(one); next(iter(changed.values()))['title'] = 'Different'
        for left, right in [(one, {}), ({}, one), (one, changed)]:
            with self.assertRaises(ValueError): require_same_index(left, right)

    def test_reordered_complete_responses_are_semantically_identical(self):
        data = response(3); one = parse_complete_day(data, DAY)
        data['resultSearch'].reverse(); two = parse_complete_day(data, DAY)
        require_same_index(one, two)
        self.assertEqual(semantic_index(one), semantic_index(two))

    def test_thirty_days_include_holidays_and_weekends(self):
        days = window_days(date(2026, 10, 4), date(2026, 10, 5))
        self.assertEqual((len(days), days[0], days[-1]), (30, date(2026, 9, 5), date(2026, 10, 4)))
        self.assertIn(date(2026, 9, 11), days)

    def test_today_and_future_are_not_complete_windows(self):
        for end in [date(2026, 10, 5), date(2026, 10, 6)]:
            with self.assertRaises(ValueError): window_days(end, date(2026, 10, 5))

    def evidence(self, root):
        observed = {'calendar': {DAY: '9747'}, 'summaries': parse_summary(summary(), '9747', DAY),
                    'search': parse_complete_day(response(), DAY)}
        manifest = []
        for num in (1, 2):
            for kind, data, parameters, route in [
                ('edition', summary(), {'numDOGC': '9747', 'language': 'ca'}, 'summaryDOGC'),
                ('daily', response(), daily_parameters(DAY), 'searchDOGC')]:
                raw = json.dumps(data).encode(); sha = hashlib.sha256(raw).hexdigest()
                (root / (sha + '.bin')).write_bytes(raw)
                manifest.append({'label': f'{kind}:{num}:{DAY}', 'sha256': sha, 'bytes': len(raw), 'status': 200,
                    'retrieved_at': '2026-10-05T06:00:00+00:00', 'method': 'POST', 'parameters': parameters,
                    'url': 'https://portaldogc.gencat.cat/eadop-rest/api/dogc/' + route})
        (root / 'acquisitions.json').write_text(json.dumps(manifest))
        return observed, manifest

    def test_both_passes_rebuild_from_original_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); observed, _ = self.evidence(root)
            verify_originals(root, observed, observed)

    def test_corrupt_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); observed, manifest = self.evidence(root)
            (root / (manifest[0]['sha256'] + '.bin')).write_bytes(b'corrupt')
            with self.assertRaises(ValueError): verify_originals(root, observed, observed)

    def test_wrong_request_scope_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); observed, manifest = self.evidence(root)
            manifest[1]['parameters']['publicationDateInitial'] = '01/01/2026'
            (root / 'acquisitions.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): verify_originals(root, observed, observed)

    def test_missing_day_and_duplicate_evidence_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); observed, manifest = self.evidence(root)
            for changed in [manifest[:-1], manifest + [manifest[0]]]:
                (root / 'acquisitions.json').write_text(json.dumps(changed))
                with self.assertRaises(ValueError): verify_originals(root, observed, observed)
