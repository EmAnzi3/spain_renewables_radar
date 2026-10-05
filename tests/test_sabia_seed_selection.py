import copy
import unittest
from datetime import datetime,timezone
from unittest.mock import Mock
from scripts.select_sabia_seed import eligible_runs,eligible_artifacts,select_seed

NOW=datetime(2026,10,5,17,0,tzinfo=timezone.utc)
REPO='owner/radar'

def run():
    return {'id':123,'status':'completed','event':'push','path':'.github/workflows/backfill-30d-validation.yml',
            'head_repository':{'full_name':REPO},'head_sha':'a'*40,'updated_at':'2026-10-05T16:00:00Z','conclusion':'failure'}

def artifact():
    return {'id':7,'name':'backfill-30d-output','expired':False,'size_in_bytes':50,
            'workflow_run':{'id':123},'created_at':'2026-10-05T16:00:00Z'}

class SeedSelectionTests(unittest.TestCase):
    def test_recent_completed_run_does_not_claim_source_success(self):
        self.assertEqual(eligible_runs([run()],REPO,999,NOW),[run()])
        self.assertEqual(run()['conclusion'],'failure')

    def test_fork_pr_current_incomplete_and_other_workflow_are_rejected(self):
        for key,value in [('head_repository',{'full_name':'fork/radar'}),('event','pull_request'),
                          ('status','in_progress'),('path','.github/workflows/other.yml'),('id',999)]:
            r=run();r[key]=value;self.assertEqual(eligible_runs([r],REPO,999,NOW),[])

    def test_expired_future_and_naive_timestamps_are_not_seeds(self):
        for at in ('2026-10-04T15:00:00Z','2026-10-05T18:00:00Z','2026-10-05T16:00:00'):
            r=run();r['updated_at']=at;self.assertEqual(eligible_runs([r],REPO,999,NOW),[])

    def test_stable_newest_ordering(self):
        a=run();b=run();b['id']=124;b['updated_at']='2026-10-05T16:30:00Z'
        self.assertEqual([x['id'] for x in eligible_runs([a,b],REPO,999,NOW)],[124,123])

    def test_expired_large_wrong_run_and_name_artifacts_are_rejected(self):
        for key,value in [('expired',True),('size_in_bytes',300000000),('workflow_run',{'id':124}),('name','foreign')]:
            a=artifact();a[key]=value;self.assertEqual(eligible_artifacts([a],123),[])

    def test_latest_attempt_artifact_selected_unambiguously(self):
        a=artifact();b=copy.deepcopy(a);b['id']=8;b['created_at']='2026-10-05T16:01:00Z'
        self.assertEqual(eligible_artifacts([a,b],123)[0]['id'],8)

    def test_selects_only_fixed_github_api_reads(self):
        s=Mock();responses=[]
        for data in [{'workflow_runs':[run()]},{'artifacts':[artifact()]}]:
            r=Mock(status_code=200);r.json.return_value=data;responses.append(r)
        s.get.side_effect=responses
        result=select_seed(s,REPO,999,NOW)
        self.assertEqual(result['run_id'],'123');self.assertEqual(result['artifact_id'],'7')
        self.assertEqual(s.get.call_count,2)
        for call in s.get.call_args_list:
            self.assertTrue(call.args[0].startswith('https://api.github.com/repos/owner/radar/actions/'))
            self.assertFalse(call.kwargs['allow_redirects'])

    def test_no_eligible_seed_means_live_acquisition(self):
        s=Mock();r=Mock(status_code=200);r.json.return_value={'workflow_runs':[]};s.get.return_value=r
        self.assertFalse(select_seed(s,REPO,999,NOW)['found'])

    def test_redirect_not_contacted_and_repo_path_injection_rejected(self):
        s=Mock();s.get.return_value=Mock(status_code=302)
        with self.assertRaises(ValueError):select_seed(s,REPO,999,NOW)
        with self.assertRaises(ValueError):select_seed(s,'../secret',999,NOW)
        self.assertEqual(s.get.call_count,1)
