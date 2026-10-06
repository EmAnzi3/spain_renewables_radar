"""Publication failures must never be presented as a new source acquisition."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

M = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/prepare_radar_publication.py'))
RUN = {'id': 12, 'status': 'completed', 'conclusion': 'success', 'head_branch': 'main',
       'head_sha': 'a' * 40, 'path': M['WORKFLOW'], 'event': 'push',
       'head_repository': {'full_name': M['REPO']}}


def fixture(root):
    status = {'run_id': '12', 'head_sha': 'a' * 40, 'database_promoted': True,
              'state': 'PARTIAL', 'full_certification': False, 'quality': {'ERROR': 0},
              'projects': 1, 'events': 1, 'complete_sources': 1, 'configured_sources': 2,
              'sources': {'BOE': {'status': 'COMPLETE'}, 'GVA_PUBLIC': {'status': 'UNAVAILABLE'}},
              'window_start': '2026-09-29', 'window_end': '2026-10-05',
              'completed_at': '2026-10-06T09:00:00+00:00'}
    data = {'records': [{'project_key': 'test', 'events': [{'external_id': 'test'}]}],
            'status': status, 'generated_at': '2026-10-06T09:00:01+00:00'}
    browser = {'real_data_projects': 1, 'javascript_errors': [], 'mobile_horizontal_overflow': False}
    (root/'browser_receipt.json').write_text(json.dumps(browser))
    return data


def write(root, data, suffix=''):
    html = '<html><script id="radar-data" type="application/json">'+json.dumps(data)+'</script>'+suffix+'</html>'
    (root/'index.html').write_text(html)
    (root/'data.json').write_text(json.dumps(data))
    build = {'projects': len(data['records']), 'events': sum(len(r['events']) for r in data['records']),
             'state': data['status']['state'], 'full_certification': False, 'generated_at': data['generated_at'],
             'index_sha256': hashlib.sha256(html.encode()).hexdigest()}
    (root/'build_receipt.json').write_text(json.dumps(build))


class PublicationTests(unittest.TestCase):
    def test_own_successful_main_run_only(self):
        M['check_run'](RUN, '12')
        for key, value in [('id', 13), ('conclusion', 'failure'), ('status', 'in_progress'),
                           ('head_branch', 'other'), ('path', 'other.yml'), ('event', 'pull_request'),
                           ('head_repository', {'full_name': 'other/repo'}), ('head_sha', 'invalid')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                M['check_run'](dict(RUN, **{key: value}), '12')

    def test_partial_snapshot_preserves_original_dates_and_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); data = fixture(root); write(root, data)
            before = (root/'data.json').read_bytes()
            r = M['verify_site'](root, RUN)
            self.assertEqual(r['state'], 'PARTIAL'); self.assertEqual(r['unavailable_sources'], ['GVA_PUBLIC'])
            self.assertEqual(r['new_source_requests'], 0); self.assertFalse(r['full_certification'])
            self.assertEqual((root/'data.json').read_bytes(), before)

    def test_stale_or_structurally_invalid_source_state_fails(self):
        mutations = [('run_id', '11'), ('head_sha', 'b'*40), ('database_promoted', False),
                     ('state', 'FAILED'), ('full_certification', True), ('projects', 9),
                     ('quality', {'ERROR': 1}), ('complete_sources', 2), ('configured_sources', 9)]
        for key, value in mutations:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as td:
                root = Path(td); data = fixture(root); data['status'][key] = value; write(root, data)
                with self.assertRaises(ValueError): M['verify_site'](root, RUN)

    def test_hash_and_inline_data_must_agree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); data = fixture(root); write(root, data)
            (root/'index.html').write_text((root/'index.html').read_text()+'changed')
            with self.assertRaises(ValueError): M['verify_site'](root, RUN)
            write(root, data); data['records'][0]['project_key'] = 'tampered'
            (root/'data.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError): M['verify_site'](root, RUN)

    def test_duplicate_embedded_payload_or_external_script_fails(self):
        for extra in ['<script src="https://example.invalid/x.js"></script>',
                      '<script type="application/json" id="radar-data">{}</script>']:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td); data = fixture(root); write(root, data, extra)
                with self.assertRaises(ValueError): M['verify_site'](root, RUN)

    def test_failed_browser_and_duplicate_projects_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); data = fixture(root); write(root, data)
            (root/'browser_receipt.json').write_text(json.dumps({'javascript_errors':['error']}))
            with self.assertRaises(ValueError): M['verify_site'](root, RUN)
            data = fixture(root); data['records'] *= 2; write(root, data)
            with self.assertRaises(ValueError): M['verify_site'](root, RUN)

    def test_timezone_required_and_generation_not_redated(self):
        with self.assertRaises(ValueError): M['timestamp']('2026-10-06T09:00:00')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); data = fixture(root); data['generated_at'] = '2026-10-05T09:00:00+00:00'; write(root, data)
            with self.assertRaises(ValueError): M['verify_site'](root, RUN)
