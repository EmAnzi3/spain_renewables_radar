import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests
from app.and_public_transport import download_archive

URL='https://datos.juntadeandalucia.es/api/v0/public-documents/all?format=json'
BODY=b'[{"id":123,"title":"Fotovoltaica"}]'

def response(parts, status=200, headers=None):
    r=Mock(status_code=status, url=URL, headers=headers or {})
    r.iter_content.return_value=iter(parts)
    if status>=400:r.raise_for_status.side_effect=requests.HTTPError(str(status), response=r)
    return r

class ArchiveTransportTests(unittest.TestCase):
    def test_interrupted_body_restarts_from_zero_and_preserves_partial_evidence(self):
        first=response([])
        def interrupted():
            yield b'[{"id":'
            raise requests.exceptions.ChunkedEncodingError('IncompleteRead')
        first.iter_content.return_value=interrupted()
        second=response([BODY]);s=Mock();s.get.side_effect=[first,second];audit={}
        with tempfile.TemporaryDirectory() as tmp, patch('app.and_public_transport.time.sleep'):
            raw,url=download_archive(s,URL,tmp,(10,90),audit)
            self.assertEqual(raw,BODY)
            self.assertEqual((Path(tmp)/'archive_attempt_1.partial').read_bytes(),b'[{"id":')
        self.assertEqual(s.get.call_count,2)
        self.assertTrue(audit['download_recovered_after_retry'])
        self.assertFalse(audit['download_attempts'][0]['complete'])
        self.assertEqual(audit['download_attempts'][1]['sha256'],hashlib.sha256(BODY).hexdigest())
        first.close.assert_called_once();second.close.assert_called_once()

    def test_content_length_mismatch_is_retried_not_accepted(self):
        s=Mock();s.get.side_effect=[response([b'[]'],headers={'Content-Length':'100'}),response([BODY])]
        with tempfile.TemporaryDirectory() as tmp, patch('app.and_public_transport.time.sleep'):
            self.assertEqual(download_archive(s,URL,tmp,30,{})[0],BODY)

    def test_gzip_wire_length_is_not_compared_with_decoded_length(self):
        s=Mock();s.get.return_value=response([BODY],headers={'Content-Encoding':'gzip','Content-Length':'15'})
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(download_archive(s,URL,tmp,30,{})[0],BODY)
        self.assertEqual(s.get.call_count,1)

    def test_permanent_transport_failure_exhausts_one_bounded_budget(self):
        s=Mock();s.get.side_effect=requests.exceptions.ConnectionError('broken');audit={}
        with tempfile.TemporaryDirectory() as tmp, patch('app.and_public_transport.time.sleep'):
            with self.assertRaises(requests.exceptions.ConnectionError):download_archive(s,URL,tmp,30,audit)
        self.assertEqual(s.get.call_count,3)
        self.assertFalse(any(x['complete'] for x in audit['download_attempts']))

    def test_forbidden_response_is_not_retried(self):
        s=Mock();r=response([],403);s.get.return_value=r
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(requests.HTTPError):download_archive(s,URL,tmp,30,{})
        self.assertEqual(s.get.call_count,1);r.close.assert_called_once()

    def test_successful_transport_does_not_make_invalid_json_valid(self):
        s=Mock();s.get.return_value=response([b'<html>Unavailable</html>'])
        with tempfile.TemporaryDirectory() as tmp:
            raw,_=download_archive(s,URL,tmp,30,{})
            with self.assertRaises(ValueError):json.loads(raw)
        self.assertEqual(s.get.call_count,1)

    def test_overlarge_body_not_retried(self):
        s=Mock();s.get.return_value=response([BODY])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'size limit'):download_archive(s,URL,tmp,30,{},max_bytes=5)
        self.assertEqual(s.get.call_count,1)

    def test_actual_retrieval_timestamp_and_bytes_audited(self):
        s=Mock();s.get.return_value=response([BODY]);audit={}
        with tempfile.TemporaryDirectory() as tmp:download_archive(s,URL,tmp,30,audit)
        info=audit['download_attempts'][0]
        self.assertTrue(info['complete']);self.assertEqual(info['bytes'],len(BODY))
        self.assertIn('+00:00',info['retrieved_at'])

    def test_observed_official_dataset_redirect_is_followed_and_audited(self):
        target='https://www.juntadeandalucia.es/ssdigitales/festa/download-pro/dataset-documento_sometido_a_informacion.json'
        first=response([],302,{'Location':target});last=response([BODY]);last.url=target
        session=Mock();session.get.side_effect=[first,last];audit={}
        with tempfile.TemporaryDirectory() as tmp:
            raw,url=download_archive(session,URL,tmp,30,audit)
        self.assertEqual((raw,url),(BODY,target))
        self.assertEqual(audit['download_attempts'][0]['redirects'][0]['to'],target)
        self.assertEqual(audit['download_attempts'][0]['download_url'],target)
        self.assertFalse(session.get.call_args_list[0].kwargs['allow_redirects'])
        first.close.assert_called_once();last.close.assert_called_once()

    def test_foreign_redirect_rejected_before_contacting_destination(self):
        session=Mock();session.get.return_value=response([],302,{'Location':'https://evil.test/data.json'})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'destination'):download_archive(session,URL,tmp,30,{})
        self.assertEqual(session.get.call_count,1)

    def test_other_path_even_on_official_domain_is_not_assumed_to_be_the_dataset(self):
        session=Mock();session.get.return_value=response([],302,{'Location':'https://www.juntadeandalucia.es/other.json'})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'destination'):download_archive(session,URL,tmp,30,{})
        self.assertEqual(session.get.call_count,1)

    def test_repeated_redirects_stop_without_downloading_a_body(self):
        session=Mock();session.get.return_value=response([],302,{'Location':URL})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'budget'):download_archive(session,URL,tmp,30,{})
        self.assertEqual(session.get.call_count,4)

if __name__=='__main__':unittest.main()
