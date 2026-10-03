"""Resume the observed SABIA snapshot without changing source dates or fabricating detail pages."""
import hashlib
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
import requests
from bs4 import BeautifulSoup

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.collectors.sabia import SEARCH_URL,parse_detail_html,PARSER_VERSION

FEATURED='https://sede.miteco.gob.es/portal/site/seMITECO/template.PAGE/navSabiaDestacados/navServicioContenido'


def form_payload(html):
    soup=BeautifulSoup(html,'html.parser')
    form=soup.find('form',id='formulario')
    if form is None:raise ValueError('Official SABIA navigation form missing')
    return {i['name']:i.get('value','') for i in form.select('input[name]') if i.get('type')=='hidden'}


def recover(code,destination):
    with requests.Session() as session:
        session.headers['User-Agent']='SpainRenewablesRadar/0.2 official-form recovery'
        page=session.get(FEATURED,timeout=(10,30));page.raise_for_status()
        payload=form_payload(page.text)
        payload.update(accion='ea_detalle',codigo_seleccionado=code,id_pagina_cargada='DESTACADOS')
        state=session.post(FEATURED,data=payload,timeout=(10,60));state.raise_for_status()
        payload=form_payload(state.text)
        if payload.get('codigo_seleccionado')!=code:raise ValueError('SABIA intermediate identity mismatch')
        payload.update(accion='proy_detalle',codigo_seleccionado=code)
        full=session.post(FEATURED,data=payload,timeout=(10,90));full.raise_for_status()
        detail=parse_detail_html(full.text)
        if detail['environmental_code']!=code:raise ValueError('SABIA detail identity mismatch')
        url=SEARCH_URL+'?'+urlencode({'accion':'proy_detalle','codigo_seleccionado':code,'id_pagina_cargada':'RESULTADOS'})
        (destination/(code+'.html')).write_text(full.text,encoding='utf-8')
        record={'detail':detail,'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),
                'retrieval_method':'OFFICIAL_FORM_POST','request_endpoint':FEATURED,
                'sha256':hashlib.sha256(full.content).hexdigest()}
        (destination/(code+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        return code


def main():
    today=datetime.now(timezone.utc).date().isoformat()
    source=Path('sabia-recovery-input/data/sabia_cache')/today/PARSER_VERSION
    if not source.exists():
        print('No same-day partial snapshot: live collector must acquire a new snapshot; old data not relabelled.')
        return
    destination=Path('data/sabia_cache')/today/PARSER_VERSION
    shutil.copytree(source,destination,dirs_exist_ok=True)
    inventory=json.loads((destination/'inventory.json').read_text(encoding='utf-8'))
    missing=[r['code'] for r in inventory if not (destination/(r['code']+'.json')).exists()]
    audit={'origin_run':37158247454,'snapshot_date':today,'inventory_count':len(inventory),
           'cached_details':len(inventory)-len(missing),'requested_missing':missing,'recovered':[],'errors':{}}
    out=Path('reports/sabia');out.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending={executor.submit(recover,code,destination):code for code in missing}
        for task in as_completed(pending):
            code=pending[task]
            try:task.result();audit['recovered'].append(code);print('SABIA_RECOVERED',code,flush=True)
            except Exception as exc:audit['errors'][code]=str(exc);print('SABIA_RECOVERY_ERROR',code,str(exc),flush=True)
            (out/'recovery.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'recovery.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SABIA_RECOVERY',json.dumps(audit,ensure_ascii=False),flush=True)
    if audit['errors']:raise SystemExit('SABIA recovery incomplete; source stays unimplemented')

if __name__=='__main__':main()
