"""Synthetic contract failures and replay tests, not claims of live coverage."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from app.and_public_catalogue import (API, acquire_catalogue, count_value, parse_part,
    reconcile, replay_catalogue, search_parameters, validate_contract)


def contract():
    return {'paths': {'/api/v0/public-documents/count': {'get': {}},
        '/api/v0/public-documents/search': {'get': {'parameters': [
            {'name': name, 'in': 'query'} for name in search_parameters(1,'ASC')]}}},
        'components': {'schemas': {key: {'enum': values} for key, values in {
            '_Enum_Mode':['ASC','DESC'], '_Enum_fields':['id'], '_Enum_Organisms':['-'],
            '_Enum_Themes':['-'], '_Enum_Counselings':['-']}.items()}}}


def originals(n=401):
    rows=[{'id':str(i), 'title':'Original '+str(i), 'publication_date':None,
           'update_date':'2026-10-05T12:00:00Z'} for i in range(1,n+1)]
    rows.sort(key=lambda r:r['id']);size=search_parameters(n,'ASC')['size']
    return {'count':{'result':n}}, {'hits':size,'total_hits':n,'results':copy.deepcopy(rows[:size])}, \
        {'hits':size,'total_hits':n,'results':copy.deepcopy(list(reversed(rows[-size:])))}, {'count':{'result':n}}


def response(data, status=200):
    raw=json.dumps(data).encode()
    r=Mock(status_code=status);r.iter_content.return_value=[raw]
    if status>=400:r.raise_for_status.side_effect=requests.HTTPError('failure',response=r)
    return r


def session_fixture():
    session=Mock();session.get.side_effect=[response(contract())]+[response(x) for x in originals()]
    return session


class CatalogueTests(unittest.TestCase):
    def test_complete_union_and_overlap_preserve_original_dates(self):
        data=originals();saved=copy.deepcopy(data);records,metrics=reconcile(*data)
        self.assertEqual(len(records),401);self.assertEqual(metrics['overlap_checked'],201)
        self.assertEqual(data,saved);self.assertIsNone(records[0]['publication_date'])
        self.assertEqual(records[0]['update_date'],'2026-10-05T12:00:00Z')

    def test_order_is_source_lexical_not_numeric(self):
        _,a,_,_=originals();self.assertEqual([r['id'] for r in a['results'][:3]],['1','10','100'])
        parse_part(a,401,'ASC')

    def test_bad_or_out_of_bound_count_fails(self):
        for value in (None, True, False, '4', 0, -1, 19001):
            with self.subTest(value=value),self.assertRaises(ValueError):count_value({'count':{'result':value}})

    def test_truncated_and_ignored_size_are_not_complete(self):
        before,a,b,after=originals();a['results'].pop()
        with self.assertRaises(ValueError):reconcile(before,a,b,after)

    def test_wrong_total_and_boolean_hits_fail(self):
        for field,value in [('total_hits',402),('hits',True)]:
            data=list(originals());data[1][field]=value
            with self.assertRaises(ValueError):reconcile(*data)

    def test_internal_duplicates_not_silently_deduplicated(self):
        data=list(originals());data[1]['results'][1]=data[1]['results'][0]
        with self.assertRaises(ValueError):reconcile(*data)

    def test_malformed_identity_not_coerced(self):
        for value in (None,1,True,'x'):
            data=list(originals());data[1]['results'][0]['id']=value
            with self.assertRaises(ValueError):reconcile(*data)

    def test_unordered_rows_fail(self):
        data=list(originals());data[1]['results'].reverse()
        with self.assertRaises(ValueError):reconcile(*data)

    def test_same_count_but_incomplete_union_fails(self):
        before,a,_,after=originals();b=copy.deepcopy(a);b['results'].reverse()
        with self.assertRaisesRegex(ValueError,'identity union'):reconcile(before,a,b,after)

    def test_changed_overlapping_original_fails(self):
        data=list(originals());data[2]['results'][-1]['title']='Changed'
        with self.assertRaisesRegex(ValueError,'overlapping'):reconcile(*data)

    def test_count_drift_fails(self):
        data=list(originals());data[-1]['count']['result']=402
        with self.assertRaisesRegex(ValueError,'changed during'):reconcile(*data)

    def test_small_catalogue_and_single_record_supported(self):
        for n in (1,2,20,200):self.assertEqual(len(reconcile(*originals(n))[0]),n)

    def test_search_does_not_filter_title_date_theme_or_organism(self):
        params=search_parameters(13636,'ASC')
        self.assertEqual(params['size'],6918)
        for key in ('organism','themes','counseling','title'):self.assertEqual(params[key],'-')
        self.assertNotIn('publication_date',params)

    def test_changed_official_contract_fails(self):
        spec=contract();validate_contract(spec);spec['components']['schemas']['_Enum_Mode']['enum']=['ASC']
        with self.assertRaises(ValueError):validate_contract(spec)

    def test_original_byte_replay_and_request_scope(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);session=session_fixture();records,audit=acquire_catalogue(session,root)
            self.assertEqual(replay_catalogue(root,audit),records)
            self.assertEqual(session.get.call_count,5)
            self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
            raw=root/audit['catalogue_generation'];manifest=json.loads((raw/'manifest.json').read_text())
            manifest[2]['parameters']['title']='solar'
            (raw/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'provenance'):replay_catalogue(root,audit)

    def test_corrupted_original_bytes_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);_,audit=acquire_catalogue(session_fixture(),root)
            raw=root/audit['catalogue_generation'];manifest=json.loads((raw/'manifest.json').read_text())
            (raw/manifest[2]['file']).write_bytes(b'[]')
            with self.assertRaisesRegex(ValueError,'integrity'):replay_catalogue(root,audit)

    def test_failed_attempt_cannot_publish_a_catalogue(self):
        with tempfile.TemporaryDirectory() as td:
            session=Mock();session.get.return_value=response({},403)
            with self.assertRaises(requests.HTTPError):acquire_catalogue(session,Path(td))
            self.assertEqual(session.get.call_count,1)
            audit=json.loads(next(Path(td).rglob('audit.json')).read_text())
            self.assertFalse(audit['complete']);self.assertFalse(list(Path(td).rglob('catalogue.json')))

    def test_redirect_and_rate_limit_do_not_trigger_fallback(self):
        for status in (302,429):
            with tempfile.TemporaryDirectory() as td:
                session=Mock();session.get.return_value=response({},status)
                with self.assertRaises((ValueError,requests.HTTPError)):acquire_catalogue(session,Path(td))
                self.assertEqual(session.get.call_count,1)

    def test_timeout_has_only_two_attempts_and_preserves_failure_evidence(self):
        with tempfile.TemporaryDirectory() as td,patch('app.and_public_catalogue.time.sleep'):
            session=Mock();session.get.side_effect=requests.Timeout('timeout')
            with self.assertRaises(requests.Timeout):acquire_catalogue(session,Path(td))
            self.assertEqual(session.get.call_count,2)
            self.assertEqual(len(json.loads(next(Path(td).rglob('manifest.json')).read_text())),2)

    def test_certificate_failure_not_retried_insecurely(self):
        with tempfile.TemporaryDirectory() as td:
            session=Mock();session.get.side_effect=requests.exceptions.SSLError('certificate')
            with self.assertRaises(requests.exceptions.SSLError):acquire_catalogue(session,Path(td))
            self.assertEqual(session.get.call_count,1)
