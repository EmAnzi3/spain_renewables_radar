import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
from app.collectors.sabia import SABIACollector
from test_sabia import SEARCH_HTML

FORM='<form id="formulario"><input type="hidden" name="nonce" value="anonymous"></form>'

def response(text, status=200):
    r=Mock();r.text=text;r.content=text.encode();r.status_code=status;r.url='https://sede.miteco.gob.es/portal/site/seMITECO/navServicioContenido'
    if status>=400:r.raise_for_status.side_effect=requests.HTTPError('source failure',response=r)
    return r

def session(get=None, post=None):
    s=Mock();s.__enter__=Mock(return_value=s);s.__exit__=Mock(return_value=False)
    s.get=Mock(side_effect=get if isinstance(get,BaseException) else None,return_value=get or response(FORM))
    s.post=Mock(side_effect=post if isinstance(post,BaseException) else None,return_value=post or response(SEARCH_HTML))
    return s

class IndexRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'SABIA_CACHE_DIR':self.temp.name});self.env.start();self.collector=SABIACollector()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_body_timeout_restarts_fresh_form_not_each_source_day(self):
        first=session(get=requests.ConnectionError('Read timed out.'));second=session()
        with patch.object(self.collector,'_session',side_effect=[first,second]),patch('app.collectors.sabia.time.sleep'):
            self.assertEqual(self.collector._fetch_index_html('FTV'),SEARCH_HTML)
        first.post.assert_not_called();second.get.assert_called_once();second.post.assert_called_once()
        self.assertEqual([x['completed'] for x in self.collector.audit['index_attempts']],[False,True])
    def test_post_timeout_restarts_entire_anonymous_read_transaction(self):
        one=session(post=requests.exceptions.ChunkedEncodingError('partial'));two=session()
        with patch.object(self.collector,'_session',side_effect=[one,two]),patch('app.collectors.sabia.time.sleep'):
            self.collector._fetch_index_html('FTV')
        self.assertEqual(one.get.call_count+two.get.call_count,2)
        self.assertEqual(one.post.call_count+two.post.call_count,2)
    def test_no_nested_adapter_retry_budget(self):
        s=session()
        with patch.object(self.collector,'_session',return_value=s):self.collector._fetch_index_html('FTV')
        self.assertEqual(s.mount.call_args.args[1].max_retries.total,0)
    def test_persistent_read_failure_exhausts_two_transactions(self):
        with patch.object(self.collector,'_session',side_effect=[session(get=requests.Timeout()),session(get=requests.Timeout())]) as factory,patch('app.collectors.sabia.time.sleep'):
            with self.assertRaises(requests.Timeout):self.collector._fetch_index_html('FTV')
        self.assertEqual(factory.call_count,2);self.assertTrue((self.collector.cache_dir/'index_attempts.json').exists())
    def test_denial_rate_limit_and_bad_request_are_not_retried(self):
        for status in (400,401,403,429):
            with self.subTest(status=status),patch.object(self.collector,'_session',return_value=session(get=response('',status))) as factory:
                with self.assertRaises(requests.HTTPError):self.collector._fetch_index_html('FTV')
                self.assertEqual(factory.call_count,1)
    def test_certificate_errors_not_retried(self):
        with patch.object(self.collector,'_session',return_value=session(get=requests.exceptions.SSLError('certificate'))) as factory:
            with self.assertRaises(requests.exceptions.SSLError):self.collector._fetch_index_html('FTV')
        self.assertEqual(factory.call_count,1)
    def test_source_semantic_failure_is_not_transport_retry(self):
        with patch.object(self.collector,'_session',return_value=session(post=response('<html>maintenance</html>'))) as factory:
            with self.assertRaisesRegex(RuntimeError,'table missing'):self.collector._fetch_index_html('FTV')
        self.assertEqual(factory.call_count,1)
    def test_missing_form_is_not_a_success_or_a_network_retry(self):
        with patch.object(self.collector,'_session',return_value=session(get=response('<html>no form</html>'))) as factory:
            with self.assertRaisesRegex(RuntimeError,'form missing'):self.collector._fetch_index_html('FTV')
        self.assertEqual(factory.call_count,1)
    def test_transient_server_error_is_retried_once(self):
        with patch.object(self.collector,'_session',side_effect=[session(post=response('',502)),session()]),patch('app.collectors.sabia.time.sleep'):
            self.assertEqual(self.collector._fetch_index_html('FTV'),SEARCH_HTML)
    def test_original_complete_response_bytes_are_saved(self):
        s=session()
        with patch.object(self.collector,'_session',return_value=s):self.collector._fetch_index_html('FTV')
        metadata=self.collector.audit['index_attempts'][0]['responses'];self.assertEqual(len(metadata),2)
        self.assertEqual((self.collector.cache_dir/metadata[1]['file']).read_bytes(),SEARCH_HTML.encode())
        payload=s.post.call_args.kwargs['data'];self.assertEqual(payload['select_estado_tramitacion'],'');self.assertEqual(payload['select_tipo'],'FTV')
