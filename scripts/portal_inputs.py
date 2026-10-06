"""Fetch pinned own-repository evidence and resume a validated main state.

Artifact hashes are checked before extraction. Original source dates are kept.
"""
from __future__ import annotations
import hashlib,json,os,shutil,sqlite3,zipfile
from pathlib import Path
from urllib.parse import urlsplit
import requests
REPO='EmAnzi3/spain_renewables_radar';API='https://api.github.com/repos/'+REPO
FIXED={
 'baseline':(11388095924,91685094,'fae2b7a9b3a15d502bc04ab1b81110b74d6fafceac70c4de5802e61e632f08d6'),
 'bopv':(11396013105,177904,'8dc9a0133c708c6cf3bfca39f065790683f05069b54e3556197d798a09999e52'),
 'alternatives':(11398269989,217777,'02626d31dea71f0275f089f8fcadedf6288dab7a675dc29daf877b78cd66a791')}

def api(path):
    token=os.environ.get('GH_TOKEN')
    if not token:raise ValueError('GitHub workflow read token is required')
    return requests.get(API+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},timeout=(15,60),allow_redirects=False)

def extract_checked(archive:Path,destination:Path):
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        if sum(x.file_size for x in z.infolist())>700_000_000:raise ValueError('Artifact expanded size exceeds limit')
        for entry in z.infolist():
            p=(destination/entry.filename).resolve()
            if not p.is_relative_to(destination.resolve()) or (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe artifact path')
        z.extractall(destination)

def download(identity:int,size:int,digest:str,name:str,root:Path):
    if not 0<size<150_000_000 or len(digest)!=64:raise ValueError('Artifact size/digest not valid')
    root.mkdir(parents=True,exist_ok=True);archive=root/(name+'.zip')
    if archive.exists() and (archive.stat().st_size!=size or hashlib.sha256(archive.read_bytes()).hexdigest()!=digest):raise ValueError('Existing evidence ZIP does not match the pinned receipt')
    if not archive.exists():
        response=api('/actions/artifacts/'+str(identity)+'/zip')
        try:
            if response.status_code!=302:response.raise_for_status();raise ValueError('Artifact download did not return its signed location')
            location=response.headers['Location'];u=urlsplit(location)
            if u.scheme!='https' or u.username or u.password:raise ValueError('Unsafe signed artifact location')
        finally:response.close()
        # Anonymous request: never send the GitHub token to blob storage.
        with requests.get(location,timeout=(15,180),stream=True) as body,archive.open('wb') as f:
            body.raise_for_status();count=0
            for chunk in body.iter_content(1048576):
                count+=len(chunk)
                if count>size:raise ValueError('Artifact is larger than the pinned receipt')
                f.write(chunk)
    if archive.stat().st_size!=size or hashlib.sha256(archive.read_bytes()).hexdigest()!=digest:raise ValueError('Artifact transport integrity mismatch: '+name)
    extract_checked(archive,root/name)
    print('ARTIFACT_VERIFIED',json.dumps({'name':name,'id':identity,'bytes':size,'sha256':digest}),flush=True)

def latest_state():
    if os.getenv('GITHUB_REF')!='refs/heads/main':return None
    r=api('/actions/workflows/radar-operational-web.yml/runs?branch=main&status=completed&per_page=20')
    if r.status_code==404:return None
    r.raise_for_status();runs=r.json()['workflow_runs'];r.close()
    for run in runs:
        if (str(run['id'])==os.getenv('GITHUB_RUN_ID') or run.get('conclusion')!='success' or run.get('head_branch')!='main'
                or run.get('head_repository',{}).get('full_name')!=REPO or run.get('event') not in ('push','workflow_dispatch','schedule')):continue
        r=api('/actions/runs/'+str(run['id'])+'/artifacts');r.raise_for_status();items=r.json()['artifacts'];r.close()
        candidates=[x for x in items if x['name']=='radar-operational-state' and not x['expired']]
        if len(candidates)!=1:continue
        item=candidates[0];digest=item.get('digest','')
        if not digest.startswith('sha256:'):continue
        return {'artifact':item,'sha256':digest[7:],'run_id':str(run['id']),'head_sha':run['head_sha']}
    return None

def restore(root:Path,expected:dict):
    if Path('data/spain_renewables.sqlite').exists():raise ValueError('State restore never overwrites an existing local database')
    manifest=json.loads((root/'state_receipt.json').read_text())
    if manifest['run_id']!=expected['run_id'] or manifest['head_sha']!=expected['head_sha']:raise ValueError('Saved state differs from its own main workflow')
    src=root/'spain_renewables.sqlite'
    if hashlib.sha256(src.read_bytes()).hexdigest()!=manifest['database_sha256']:raise ValueError('Saved DB digest failed')
    status=json.loads((root/'latest.json').read_text())
    if status.get('state') not in ('PARTIAL','COMPLETE') or not status.get('database_promoted'):raise ValueError('Saved state was not a successfully checked operational update')
    with sqlite3.connect(f'file:{src.resolve()}?mode=ro',uri=True) as conn:
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Saved SQLite integrity failed')
        if conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]!=manifest['projects']:raise ValueError('Saved count differs')
    Path('data').mkdir(exist_ok=True);Path('reports/operational').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,'data/spain_renewables.sqlite');shutil.copyfile(root/'latest.json','reports/operational/latest.json')
    print('OPERATIONAL_STATE_RESTORED',expected['run_id'])

def main():
    root=Path('inputs')
    for name,(identity,size,digest) in FIXED.items():download(identity,size,digest,name,root)
    state=latest_state()
    if state:
        item=state['artifact'];download(item['id'],item['size_in_bytes'],state['sha256'],'state',root);restore(root/'state',state)
if __name__=='__main__':main()
