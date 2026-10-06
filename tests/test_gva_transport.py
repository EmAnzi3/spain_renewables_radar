import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
from app.gva_transport import fetch_official, verified_url, MAX_ATTEMPTS
from app.collectors.gva_public import GVAPublicCollector

URL = 'https://mediambient.gva.es/es/web/energia/informacion-publica?page=2'


def response(status=200, chunks=None, headers=None):
    result = Mock()
    result.status_code = status
    result.headers = headers or {}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError('source error', response=result)
    result.iter_content.return_value = iter(chunks or [b'original'])
    return result


def session(values):
    result = Mock()
    result.headers = {}
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.get.side_effect = values
    return result


class GVATransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.audit = {'acquisitions': []}
    def tearDown(self):
        self.directory.cleanup()
    def fetch(self, url=URL, **kwargs):
        return fetch_official(url, output=self.root, audit=self.audit, timeout=(8,35), user_agent='test', **kwargs)
    def test_exact_source_bytes_and_receipt_are_preserved(self):
        s=session([response(chunks=[b'one',b'two'])])
        with patch('app.gva_transport.requests.Session',return_value=s):raw,url=self.fetch()
        self.assertEqual((raw,url),(b'onetwo',URL))
        receipt=self.audit['acquisitions'][0]
        self.assertEqual((self.root/receipt['file']).read_bytes(),raw)
        self.assertEqual(receipt['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertTrue(self.audit['transport_attempts'][0]['complete'])
    def test_connection_reset_gets_fresh_session_once(self):
        one=session([requests.ConnectionError('reset')]);two=session([response()])
        with patch('app.gva_transport.requests.Session',side_effect=[one,two]) as factory,patch('app.gva_transport.time.sleep'):
            self.fetch()
        self.assertEqual(factory.call_count,2)
        self.assertEqual(one.get.call_count,1);self.assertEqual(two.get.call_count,1)
        self.assertEqual(len(self.audit['acquisitions']),1)
    def test_stream_failure_preserves_partial_without_publishing_it(self):
        def broken():
            yield b'partial'
            raise requests.exceptions.ChunkedEncodingError('truncated')
        bad=response();bad.iter_content.return_value=broken()
        with patch('app.gva_transport.requests.Session',side_effect=[session([bad]),session([response(chunks=[b'complete'])])]),patch('app.gva_transport.time.sleep'):
            raw,_=self.fetch()
        self.assertEqual(raw,b'complete')
        failed=self.audit['transport_attempts'][0]['responses'][0]
        self.assertEqual((self.root/failed['partial_file']).read_bytes(),b'partial')
        self.assertEqual(len(self.audit['acquisitions']),1)
    def test_adapter_retries_disabled(self):
        s=session([response()])
        with patch('app.gva_transport.requests.Session',return_value=s):self.fetch()
        self.assertEqual(s.mount.call_args.args[1].max_retries.total,0)
    def test_permanent_timeout_has_one_bounded_budget(self):
        sessions=[session([requests.Timeout('read')]) for _ in range(MAX_ATTEMPTS)]
        with patch('app.gva_transport.requests.Session',side_effect=sessions) as factory,patch('app.gva_transport.time.sleep'):
            with self.assertRaises(requests.Timeout):self.fetch()
        self.assertEqual(factory.call_count,3);self.assertEqual(self.audit['acquisitions'],[])
        self.assertEqual(len(json.loads((self.root/'transport_attempts.json').read_text())),3)
    def test_forbidden_rate_limit_and_bad_requests_not_retried(self):
        for status in (400,401,403,404,429):
            with self.subTest(status=status),patch('app.gva_transport.requests.Session',return_value=session([response(status)])) as factory:
                with self.assertRaises(requests.HTTPError):self.fetch()
                self.assertEqual(factory.call_count,1)
    def test_certificate_error_never_uses_insecure_retry(self):
        with patch('app.gva_transport.requests.Session',return_value=session([requests.exceptions.SSLError('certificate')])) as factory:
            with self.assertRaises(requests.exceptions.SSLError):self.fetch()
        self.assertEqual(factory.call_count,1)
    def test_transient_server_errors_retry_complete_request(self):
        with patch('app.gva_transport.requests.Session',side_effect=[session([response(502)]),session([response()])]),patch('app.gva_transport.time.sleep'):
            self.assertEqual(self.fetch()[0],b'original')
    def test_source_redirect_keeps_final_url_and_original_origin(self):
        target='https://mediambient.gva.es/official/new'
        s=session([response(302,headers={'Location':target}),response()])
        with patch('app.gva_transport.requests.Session',return_value=s):self.assertEqual(self.fetch()[1],target)
        self.assertEqual(self.audit['transport_attempts'][-1]['origin_url'],URL)
        self.assertFalse(s.get.call_args.kwargs['allow_redirects'])
    def test_foreign_redirect_not_contacted(self):
        s=session([response(302,headers={'Location':'https://elsewhere.invalid/data'})])
        with patch('app.gva_transport.requests.Session',return_value=s) as factory:
            with self.assertRaises(ValueError):self.fetch()
        self.assertEqual(s.get.call_count,1);self.assertEqual(factory.call_count,1)
    def test_redirect_cycle_fails_without_retry(self):
        s=session([response(302,headers={'Location':URL})])
        with patch('app.gva_transport.requests.Session',return_value=s) as factory:
            with self.assertRaisesRegex(ValueError,'cycle'):self.fetch()
        self.assertEqual(factory.call_count,1)
    def test_empty_or_partial_success_remains_subject_to_source_parser(self):
        collector=GVAPublicCollector(out_dir=str(self.root))
        with patch.object(collector,'_get',return_value=(b'<html>maintenance</html>',URL)) as factory:
            with self.assertRaisesRegex(ValueError,'pagination'):collector._load()
            with self.assertRaises(RuntimeError):collector._load()
        self.assertEqual(factory.call_count,1)
        self.assertFalse(collector.audit['complete'])
    def test_content_length_truncation_restarts_from_zero(self):
        bad=response(chunks=[b'ab'],headers={'Content-Length':'3'})
        good=response(chunks=[b'abc'],headers={'Content-Length':'3'})
        with patch('app.gva_transport.requests.Session',side_effect=[session([bad]),session([good])]),patch('app.gva_transport.time.sleep'):
            self.assertEqual(self.fetch()[0],b'abc')
    def test_compressed_wire_length_not_compared_to_decoded_bytes(self):
        s=session([response(chunks=[b'decoded'],headers={'Content-Encoding':'gzip','Content-Length':'50'})])
        with patch('app.gva_transport.requests.Session',return_value=s):self.fetch()
    def test_oversized_response_not_retried(self):
        s=session([response(chunks=[b'too large'])])
        with patch('app.gva_transport.requests.Session',return_value=s) as factory:
            with self.assertRaisesRegex(ValueError,'bounded'):self.fetch(limit=3)
        self.assertEqual(factory.call_count,1);self.assertEqual(self.audit['acquisitions'],[])
    def test_invalid_urls_rejected_before_any_contact(self):
        for url in ['http://mediambient.gva.es/x','https://gva.es.evil.invalid/x','https://user@mediambient.gva.es/x','https://mediambient.gva.es:444/x']:
            with self.assertRaises(ValueError):verified_url(url)
    def test_retry_after_redirect_restarts_from_original_get(self):
        target='https://mediambient.gva.es/new'
        one=session([response(302,headers={'Location':target}),requests.ConnectionError('reset')])
        two=session([response()])
        with patch('app.gva_transport.requests.Session',side_effect=[one,two]),patch('app.gva_transport.time.sleep'):self.fetch()
        self.assertEqual(two.get.call_args.args[0],URL)
    def test_responses_and_sessions_are_closed(self):
        r=response(500);s=session([r])
        with patch('app.gva_transport.requests.Session',side_effect=[s,session([response()])]),patch('app.gva_transport.time.sleep'):self.fetch()
        r.close.assert_called_once();s.__exit__.assert_called_once()
