import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from recover_unassigned_runner import API, MESSAGE, WORKFLOW, decide, execute

REPO='EmAnzi3/spain_renewables_radar'; SHA='a'*40

def evidence():
    run={'id':42,'repository':{'full_name':REPO},'head_repository':{'full_name':REPO},
         'head_sha':SHA,'head_branch':'main','path':WORKFLOW,'event':'push',
         'run_attempt':1,'status':'completed','conclusion':'failure'}
    job={'id':99,'run_id':42,'head_sha':SHA,'head_branch':'main','run_attempt':1,
         'name':'backfill','status':'completed','conclusion':'cancelled','steps':[],
         'runner_id':0,'runner_name':'','runner_group_id':0}
    annotations=[{'annotation_level':'failure','message':MESSAGE}]
    return run,[job],annotations

class RecoveryTests(unittest.TestCase):
    def test_only_observed_infrastructure_failure_is_eligible(self):
        self.assertTrue(decide(*evidence(),REPO,SHA)[0])
    def test_second_attempt_never_retried(self):
        r,j,a=evidence();r['run_attempt']=2
        self.assertFalse(decide(r,j,a,REPO,SHA)[0])
    def test_missing_or_boolean_attempt_not_valid(self):
        for value in [None,True,'1']:
            r,j,a=evidence();r['run_attempt']=value
            self.assertFalse(decide(r,j,a,REPO,SHA)[0])
    def test_data_failure_or_partial_run_not_retried(self):
        for field,value in [('steps',[{'name':'collect','conclusion':'failure'}]),('steps',None),('conclusion','failure'),('runner_id',1),('runner_name','hosted'),('runner_group_id',1)]:
            r,j,a=evidence();j[0][field]=value
            with self.subTest(field=field):self.assertFalse(decide(r,j,a,REPO,SHA)[0])
    def test_arbitrary_failure_not_hidden(self):
        for annotations in [[],None,[{'annotation_level':'failure','message':'timeout collecting official source'}],[{'annotation_level':'notice','message':MESSAGE}]]:
            r,j,_=evidence();self.assertFalse(decide(r,j,annotations,REPO,SHA)[0])
    def test_second_failure_annotation_blocks(self):
        r,j,a=evidence();a.append({'annotation_level':'failure','message':'Quality gate failed'})
        self.assertFalse(decide(r,j,a,REPO,SHA)[0])
    def test_fork_or_pull_request_cannot_request_write(self):
        for field,value in [('head_repository',{'full_name':'other/fork'}),('repository',{'full_name':'other/repo'}),('head_branch','feature'),('event','pull_request'),('path','.github/workflows/other.yml')]:
            r,j,a=evidence();r[field]=value
            with self.subTest(field=field):self.assertFalse(decide(r,j,a,REPO,SHA)[0])
    def test_success_cancelled_or_running_run_not_retried(self):
        for field,value in [('status','in_progress'),('conclusion','success'),('conclusion','cancelled')]:
            r,j,a=evidence();r[field]=value;self.assertFalse(decide(r,j,a,REPO,SHA)[0])
    def test_new_main_or_invalid_sha_not_retried(self):
        for sha in ['b'*40,'a',None]:self.assertFalse(decide(*evidence(),REPO,sha)[0])
    def test_unexpected_job_scope_not_retried(self):
        r,j,a=evidence()
        for jobs in [[],j+j,None]:self.assertFalse(decide(r,jobs,a,REPO,SHA)[0])
    def test_job_identity_must_match(self):
        for field,value in [('run_id',43),('id',None),('head_sha','b'*40),('head_branch','feature'),('run_attempt',2),('name','another')]:
            r,j,a=evidence();j[0][field]=value;self.assertFalse(decide(r,j,a,REPO,SHA)[0])
    def api(self, second_run=None, second_sha=SHA):
        r,j,a=evidence();api=Mock()
        api.request.side_effect=[r,{'object':{'sha':SHA}},{'total_count':1,'jobs':j},a,second_run or r,{'object':{'sha':second_sha}},{}]
        return api
    def test_exactly_one_post_for_eligible_case(self):
        api=self.api();self.assertEqual(execute(api,REPO,42,apply=True)['action'],'ONE_RETRY_REQUESTED')
        writes=[c for c in api.request.call_args_list if c.kwargs.get('post')]
        self.assertEqual(len(writes),1);self.assertEqual(writes[0].args,('/actions/jobs/99/rerun',))
    def test_manual_retry_race_prevents_second_post(self):
        r,_,_=evidence();r['run_attempt']=2;api=self.api(r)
        self.assertEqual(execute(api,REPO,42,apply=True)['action'],'SKIPPED')
        self.assertFalse(any(c.kwargs.get('post') for c in api.request.call_args_list))
    def test_new_commit_race_prevents_post(self):
        api=self.api(second_sha='b'*40);self.assertEqual(execute(api,REPO,42,apply=True)['action'],'SKIPPED')
    def test_dry_run_does_not_write(self):
        api=self.api();self.assertEqual(execute(api,REPO,42)['action'],'ELIGIBLE_DRY_RUN')
        self.assertEqual(api.request.call_count,4)
    def test_post_failure_is_not_retried(self):
        api=self.api();results=list(api.request.side_effect);results[-1]=TimeoutError('uncertain response');api.request.side_effect=results
        with self.assertRaises(TimeoutError):execute(api,REPO,42,apply=True)
        self.assertEqual(sum(bool(c.kwargs.get('post')) for c in api.request.call_args_list),1)
    def test_api_rejects_foreign_paths_before_contact(self):
        api=API(REPO,'unused');api.opener=Mock()
        for path in ['https://elsewhere.invalid','/secrets','/actions/jobs/99/rerun/../../bad']:
            with self.assertRaises(ValueError):api.request(path)
        api.opener.open.assert_not_called()
