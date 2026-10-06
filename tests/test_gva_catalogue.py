from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import requests
from app.gva_catalogue import load_catalogue,parse_receipts
from app.gva_transport import fetch_official
from app.collectors.gva_public import BASE
from test_gva_transport import response


def page(n, total=3, title='Plant', size=2):
    first=(n-1)*size+1;last=min(n*size,total)
    rows=''.join(f'<div class="asset-abstract"><h3 class="asset-title"><a href="?x_assetEntryId={i}">{title}{i}</a></h3><span class="metadata-publish-date">05/10/2026</span></div>' for i in range(first,last+1))
    return (rows+f'<div class="taglib-page-iterator">Mostrando {first} - {last} de {total} resultados<a href="?x_cur=2&amp;x_delta={size}">Next</a></div>').encode()


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.audit={'acquisitions':[]};self.calls=[]
        self.environment=patch.dict(os.environ,GITHUB_RUN_ID='5',GITHUB_RUN_ATTEMPT='1');self.environment.start()
    def tearDown(self):self.environment.stop();self.tmp.cleanup()
    def get(self,url):
        self.calls.append(url);n=2 if 'x_cur=2' in url else 1;raw=page(n)
        sha=hashlib.sha256(raw).hexdigest();(self.root/(sha+'.html')).write_bytes(raw)
        self.audit['acquisitions'].append({'url':url,'sha256':sha,'file':sha+'.html','bytes':len(raw),'retrieved_at':datetime.now(timezone.utc).isoformat()})
        return raw,url
    def load(self):return load_catalogue(self.get,self.root,self.audit)
    def test_full_catalogue_then_same_run_replay_only_live_boundaries(self):
        rows,meta=self.load();self.assertEqual(len(rows),3);self.assertEqual(len(self.calls),3)
        originals=json.loads((self.root/'catalogue_same_run.json').read_text())
        self.calls=[];again,meta=self.load()
        self.assertEqual(rows,again);self.assertEqual(len(self.calls),2)
        self.assertEqual(meta['catalogue_mode'],'SAME_RUN_ORIGINAL_REPLAY_WITH_LIVE_BOUNDARIES')
        self.assertEqual(json.loads((self.root/'catalogue_same_run.json').read_text()),originals)
    def test_new_attempt_cannot_reuse(self):
        self.load();self.calls=[]
        with patch.dict(os.environ,GITHUB_RUN_ATTEMPT='2'):self.load()
        self.assertEqual(len(self.calls),3)
    def test_other_run_cannot_reuse(self):
        self.load();self.calls=[]
        with patch.dict(os.environ,GITHUB_RUN_ID='6'):self.load()
        self.assertEqual(len(self.calls),3)
    def test_local_run_without_scope_does_not_persist_discovery_cache(self):
        with patch.dict(os.environ,GITHUB_RUN_ID='',GITHUB_RUN_ATTEMPT=''):
            self.load();self.load()
        self.assertEqual(len(self.calls),6);self.assertFalse((self.root/'catalogue_same_run.json').exists())
    def test_expired_and_future_snapshots_require_fresh_collection(self):
        for delta in (-7200,7200):
            self.load();p=self.root/'catalogue_same_run.json';d=json.loads(p.read_text())
            d['oldest_retrieved_at']=(datetime.now(timezone.utc)+timedelta(seconds=delta)).isoformat();p.write_text(json.dumps(d))
            self.calls=[];self.load();self.assertEqual(len(self.calls),3)
    def test_corrupt_original_requires_complete_live_recollection(self):
        self.load();p=self.root/'catalogue_same_run.json';d=json.loads(p.read_text())
        (self.root/d['pages'][1]['file']).write_bytes(b'bad');self.calls=[]
        self.load();self.assertEqual(len(self.calls),3)
    def test_no_cached_fallback_when_live_boundary_times_out(self):
        self.load();before=(self.root/'catalogue_same_run.json').read_bytes()
        with self.assertRaises(requests.Timeout):load_catalogue(Mock(side_effect=requests.Timeout('failure')),self.root,self.audit)
        self.assertEqual(before,(self.root/'catalogue_same_run.json').read_bytes())
    def test_incomplete_catalogue_is_not_published(self):
        def broken(url):
            if 'x_cur=2' in url:raise requests.Timeout('failure')
            return self.get(url)
        with self.assertRaises(requests.Timeout):load_catalogue(broken,self.root,self.audit)
        self.assertFalse((self.root/'catalogue_same_run.json').exists())
    def test_changed_title_cannot_reuse_stale_snapshot(self):
        self.load();original_get=self.get;self.calls=[]
        def changed(url):
            raw,location=original_get(url);raw=raw.replace(b'Plant',b'Changed')
            sha=hashlib.sha256(raw).hexdigest();(self.root/(sha+'.html')).write_bytes(raw)
            self.audit['acquisitions'].append({'url':url,'sha256':sha,'file':sha+'.html','bytes':len(raw),'retrieved_at':datetime.now(timezone.utc).isoformat()})
            return raw,location
        rows,meta=load_catalogue(changed,self.root,self.audit)
        self.assertEqual(meta['catalogue_mode'],'LIVE_FULL_CATALOGUE');self.assertTrue(all(r['title'].startswith('Changed') for r in rows))
    def test_altered_page_ranges_fail(self):
        self.load();d=json.loads((self.root/'catalogue_same_run.json').read_text());d['pages'].append(d['pages'][1])
        with self.assertRaises(ValueError):parse_receipts(d['pages'],self.root)
    def test_foreign_file_path_is_rejected(self):
        with self.assertRaises(ValueError):parse_receipts([{'sha256':'f'*64,'file':'../outside.html'}],self.root)
    def test_changed_total_fails_not_truncates(self):
        self.load();d=json.loads((self.root/'catalogue_same_run.json').read_text());d['pages']=d['pages'][:1]
        with self.assertRaises(ValueError):parse_receipts(d['pages'],self.root)


class SessionTests(unittest.TestCase):
    def test_session_reused_without_reopening_or_adapter_retry(self):
        s=requests.Session();s.get=Mock(side_effect=[response(),response()])
        with tempfile.TemporaryDirectory() as td,patch('app.gva_transport.time.sleep') as pause:
            a={}
            for _ in range(2):fetch_official(BASE,output=td,audit=a,timeout=10,user_agent='test',session=s)
            self.assertEqual(s.get.call_count,2);self.assertEqual(s.get_adapter(BASE).max_retries.total,0)
            self.assertEqual(len(a['acquisitions']),2);self.assertTrue(pause.called)
        s.close()
    def test_failure_resets_pool_but_retry_budget_stays_three(self):
        s=requests.Session();s.get=Mock(side_effect=requests.Timeout('failed'))
        with tempfile.TemporaryDirectory() as td,patch.object(s,'close') as close,patch('app.gva_transport.time.sleep'):
            with self.assertRaises(requests.Timeout):fetch_official(BASE,output=td,audit={},timeout=10,user_agent='test',session=s)
            self.assertEqual(s.get.call_count,3);self.assertEqual(close.call_count,2)
        s.close()
    def test_permanent_denial_never_retried(self):
        for status in (400,401,403,429):
            s=requests.Session();s.get=Mock(return_value=response(status))
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(requests.HTTPError):fetch_official(BASE,output=td,audit={},timeout=10,user_agent='test',session=s)
                self.assertEqual(s.get.call_count,1)
            s.close()
