"""Choose a recent own-repository cache; never treat a run/artifact as live data.

Only already completed backfill runs triggered in this repository are eligible.
The existing seed reader must still verify every detail's hash, ID and original
age (<24 hours), copy no discovery index, and reparse against the live index.
An unavailable cache is a miss, not a skipped live acquisition or a failure gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

import requests

WORKFLOW = '.github/workflows/backfill-30d-validation.yml'
ARTIFACT = 'backfill-30d-output'
MAX_ARCHIVE_BYTES = 250_000_000


def timestamp(value):
    if not isinstance(value, str): raise ValueError('Missing source timestamp')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None: raise ValueError('Naive source timestamp')
    return stamp


def eligible_runs(rows, repository, current_run, now):
    selected=[]
    for row in rows:
        try:
            if (type(row['id']) is not int or row['id']==int(current_run)
                    or row.get('status')!='completed'
                    or row.get('event') not in {'push','workflow_dispatch','schedule'}
                    or row.get('path')!=WORKFLOW
                    or row.get('head_repository',{}).get('full_name','').casefold()!=repository.casefold()
                    or not re.fullmatch(r'[a-f0-9]{40}',row.get('head_sha',''))):
                continue
            at=timestamp(row['updated_at'])
            if not 0 <= (now-at).total_seconds() < 86400: continue
            selected.append(row)
        except (KeyError,ValueError,TypeError):
            continue
    return sorted(selected,key=lambda r:(timestamp(r['updated_at']),r['id']),reverse=True)


def eligible_artifacts(rows, run_id):
    found=[]
    for row in rows:
        try:
            if (row.get('name')!=ARTIFACT or row.get('expired') is not False
                    or type(row.get('id')) is not int
                    or type(row.get('size_in_bytes')) is not int
                    or not 0 < row['size_in_bytes'] <= MAX_ARCHIVE_BYTES
                    or row.get('workflow_run',{}).get('id')!=run_id): continue
            timestamp(row['created_at']);found.append(row)
        except (ValueError,TypeError): continue
    return sorted(found,key=lambda r:(timestamp(r['created_at']),r['id']),reverse=True)


def select_seed(session, repository, current_run, now):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',repository):
        raise ValueError('Invalid repository identity')
    base='https://api.github.com/repos/'+repository
    def get(path,params=None):
        # Never follow returned URLs with the token or download/extract here.
        response=session.get(base+path,params=params,timeout=(8,20),allow_redirects=False)
        try:
            response.raise_for_status()
            if response.status_code!=200:raise ValueError('Unexpected GitHub API redirect/status')
            return response.json()
        finally:response.close()
    payload=get('/actions/workflows/backfill-30d-validation.yml/runs',{'status':'completed','per_page':10})
    for run in eligible_runs(payload.get('workflow_runs',[]),repository,current_run,now)[:3]:
        payload=get('/actions/runs/'+str(run['id'])+'/artifacts',{'per_page':30})
        matches=eligible_artifacts(payload.get('artifacts',[]),run['id'])
        if matches:
            artifact=matches[0]
            return {'found':True,'run_id':str(run['id']),'run_attempt':run.get('run_attempt'),
                    'run_conclusion':run.get('conclusion'),'head_sha':run['head_sha'],
                    'artifact_id':str(artifact['id']),'artifact_name':ARTIFACT,
                    'eligibility':'own-repository completed run; individual source records still require age/hash/live-index checks'}
    return {'found':False,'run_id':'0','artifact_id':'0','artifact_name':ARTIFACT,'reason':'No eligible recent own-repository artifact'}


def main():
    result={'found':False,'run_id':'0','artifact_id':'0','artifact_name':ARTIFACT}
    try:
        with requests.Session() as session:
            session.headers['Accept']='application/vnd.github+json'
            token=os.getenv('GH_TOKEN')
            if token:session.headers['Authorization']='Bearer '+token
            result=select_seed(session,os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_RUN_ID'],datetime.now(timezone.utc))
    except Exception as exc:
        # Optional cache failure must not weaken or pre-empt the live source gate.
        result.update(reason='Cache selection unavailable; live acquisition required',error_type=type(exc).__name__)
    result['selected_at']=datetime.now(timezone.utc).isoformat()
    out=Path('reports/sabia');out.mkdir(parents=True,exist_ok=True)
    (out/'cache_seed_selection.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as stream:
        for key in ('found','run_id','artifact_id','artifact_name'):
            value=str(result[key]).lower() if isinstance(result[key],bool) else result[key]
            stream.write(key+'='+value+'\n')
    print('SABIA_CACHE_SELECTION',json.dumps(result),flush=True)


if __name__=='__main__':main()
