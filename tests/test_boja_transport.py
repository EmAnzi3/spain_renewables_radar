from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import unittest
from unittest.mock import patch

import requests
from app.collectors.boja import BOJACollector


class BOJATransportTests(unittest.TestCase):
    def test_only_transient_get_failures_are_retried(self):
        collector = BOJACollector()
        self.addCleanup(collector.session.close)
        retry = collector.session.get_adapter('https://').max_retries
        self.assertEqual(retry.total, 3)
        self.assertEqual(retry.allowed_methods, frozenset({'GET'}))
        self.assertIn(503, retry.status_forcelist)
        self.assertNotIn(400, retry.status_forcelist)
        self.assertNotIn(403, retry.status_forcelist)
        self.assertFalse(retry.is_retry('POST', 503))

    def test_live_local_http_503_is_retried_then_original_json_returned(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                body = json.dumps({'body': 'official original text'}).encode()
                self.send_response(503 if len(received) == 1 else 200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_args):
                pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            collector = BOJACollector(timeout=3)
            self.addCleanup(collector.session.close)
            result = collector._get_json(f'http://127.0.0.1:{server.server_port}/original')
            self.assertEqual(result, {'body': 'official original text'})
            self.assertEqual(received, ['/original', '/original'])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_exhausted_detail_failure_is_not_replaced_by_search_summary(self):
        collector = BOJACollector()
        self.addCleanup(collector.session.close)
        row = {'id': 'disposition.2024.200.1', 'summary': 'Planta solar fotovoltaica de 20 MW'}
        with patch.object(collector, '_get_json', side_effect=requests.ConnectionError('source disconnected')):
            with self.assertRaises(requests.ConnectionError):
                collector._detail(row)

    def test_failed_detail_prevents_certifying_the_source_day(self):
        collector = BOJACollector()
        self.addCleanup(collector.session.close)
        row = {'id': 'disposition.2024.200.1', 'summary': 'Planta solar fotovoltaica de 20 MW'}
        with patch.object(collector, '_day_rows', return_value=iter([row])), \
             patch.object(collector, '_get_json', side_effect=requests.Timeout('detail unavailable')):
            with self.assertRaises(requests.Timeout):
                collector.collect_day(date(2024, 10, 5))

    def test_missing_detail_identity_is_not_generic_source_evidence(self):
        collector = BOJACollector()
        self.addCleanup(collector.session.close)
        with self.assertRaisesRegex(ValueError, 'identity missing'):
            collector._detail({'summary': 'Planta fotovoltaica'})

    def test_empty_detail_is_not_replaced_by_search_summary(self):
        collector = BOJACollector()
        self.addCleanup(collector.session.close)
        with patch.object(collector, '_get_json', return_value={}):
            with self.assertRaisesRegex(ValueError, 'no original source text'):
                collector._detail({'id': 'x', 'summary': 'Planta fotovoltaica de 20 MW'})
