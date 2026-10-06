"""Retry once ONLY when GitHub never assigned the trusted main backfill job.

No code/data failure, partial execution, stale revision, fork or second attempt
is eligible. The original failed run remains in history. Network requests have
no automatic retry, redirects are rejected, and the token never leaves GitHub.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import urllib.request

WORKFLOW = '.github/workflows/backfill-30d-validation.yml'
MESSAGE = 'The job was not acquired by Runner of type hosted even after multiple attempts'


def decide(run, jobs, annotations, repository, main_sha):
    if (run.get('head_repository', {}).get('full_name') != repository
            or run.get('repository', {}).get('full_name') != repository
            or run.get('head_branch') != 'main'
            or run.get('path') != WORKFLOW
            or run.get('event') not in {'push', 'workflow_dispatch', 'schedule'}):
        return False, 'not_trusted_main_backfill'
    if run.get('head_sha') != main_sha or not re.fullmatch(r'[a-f0-9]{40}', str(main_sha)):
        return False, 'main_has_changed'
    if (type(run.get('run_attempt')) is not int or run['run_attempt'] != 1
            or run.get('status') != 'completed' or run.get('conclusion') != 'failure'):
        return False, 'not_failed_first_attempt'
    if not isinstance(jobs, list) or len(jobs) != 1:
        return False, 'unexpected_job_scope'
    job = jobs[0]
    if (type(job.get('id')) is not int or job['id'] <= 0 or job.get('run_id') != run.get('id')
            or job.get('head_sha') != main_sha or job.get('head_branch') != 'main'
            or job.get('run_attempt') != 1 or job.get('name') != 'backfill'):
        return False, 'job_identity_mismatch'
    if (job.get('status') != 'completed' or job.get('conclusion') != 'cancelled'
            or job.get('steps') != [] or job.get('runner_id') != 0
            or job.get('runner_name') != '' or job.get('runner_group_id') != 0):
        return False, 'job_may_have_started'
    if not isinstance(annotations, list):
        return False, 'annotations_unavailable'
    failures = [a.get('message') for a in annotations if a.get('annotation_level') == 'failure']
    if not failures or any(message != MESSAGE for message in failures):
        return False, 'not_exact_unassigned_runner_failure'
    return True, 'exact_unassigned_runner_first_attempt'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class API:
    def __init__(self, repository, token):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid repository')
        self.base = 'https://api.github.com/repos/' + repository
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, *, post=False):
        if not re.fullmatch(r'/(?:actions/runs/\d+(?:/jobs\?filter=latest&per_page=100)?|actions/jobs/\d+/rerun|check-runs/\d+/annotations\?per_page=100|git/ref/heads/main)', path):
            raise ValueError('Unexpected GitHub API path')
        req = urllib.request.Request(self.base + path, data=b'{}' if post else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json'}, method='POST' if post else 'GET')
        with self.opener.open(req, timeout=20) as response:
            if response.status != (201 if post else 200):
                raise ValueError('Unexpected GitHub response status')
            if 'rel="next"' in response.headers.get('Link', ''):
                raise ValueError('Evidence truncated by pagination')
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('Evidence exceeds limit')
            return json.loads(raw) if raw else {}


def execute(api, repository, run_id, *, apply=False):
    if type(run_id) is not int or run_id <= 0:
        raise ValueError('Invalid run ID')
    run = api.request('/actions/runs/' + str(run_id))
    main_sha = api.request('/git/ref/heads/main')['object']['sha']
    payload = api.request('/actions/runs/' + str(run_id) + '/jobs?filter=latest&per_page=100')
    jobs = payload.get('jobs')
    if payload.get('total_count') != 1 or not isinstance(jobs, list) or len(jobs) != 1:
        return {'action': 'SKIPPED', 'reason': 'unexpected_job_scope', 'run_id': run_id}
    job_id = jobs[0].get('id')
    if type(job_id) is not int or job_id <= 0:
        raise ValueError('Invalid job ID')
    annotations = api.request('/check-runs/' + str(job_id) + '/annotations?per_page=100')
    eligible, reason = decide(run, jobs, annotations, repository, main_sha)
    result = {'run_id': run_id, 'job_id': job_id, 'head_sha': run.get('head_sha'),
              'run_attempt': run.get('run_attempt'), 'eligible': eligible, 'reason': reason,
              'action': 'ELIGIBLE_DRY_RUN' if eligible else 'SKIPPED',
              'original_failure_annotations': annotations}
    if eligible and apply:
        # Re-read immediately before the sole write: manual reruns and new commits
        # make the action ineligible. Never repeat the POST after an uncertain reply.
        latest = api.request('/actions/runs/' + str(run_id))
        current = api.request('/git/ref/heads/main')['object']['sha']
        ready, why = decide(latest, jobs, annotations, repository, current)
        if not ready:
            result.update(action='SKIPPED', reason=why)
        else:
            api.request('/actions/jobs/' + str(job_id) + '/rerun', post=True)
            result['action'] = 'ONE_RETRY_REQUESTED'
    return result


def main():
    repository = os.environ['GITHUB_REPOSITORY']
    payload = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    event = payload.get('workflow_run', {})
    # A manual trigger or a pull-request-controlled payload must never acquire writes.
    if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_run' or payload.get('action') != 'completed':
        raise ValueError('Only completed workflow_run events may invoke recovery')
    if payload.get('repository', {}).get('full_name') != repository:
        raise ValueError('Unexpected event repository')
    api = API(repository, os.environ['GH_TOKEN'])
    result = execute(api, repository, event.get('id'), apply=True)
    target = Path('reports/runner_recovery.json'); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('RUNNER_RECOVERY', json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
