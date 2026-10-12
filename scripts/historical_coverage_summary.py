"""Coverage-only ledger for all planned source/month scans.

A report with missing results is PARTIAL; no unsupported region, year or
source-day is represented as a successful scan. No database writes.
"""
from __future__ import annotations
import argparse
from collections import Counter
import html
import json
from pathlib import Path

from app.historical_backfill import SCANNABLE


def coverage(plan:dict, audits:list[dict]):
    expected={(x['source_code'],x['start'],x['end']):x for x in plan['tasks'] if x['status']=='PENDING'}
    received={}
    for item in audits:
        key=(item.get('source_code'),item.get('from_date'),item.get('until_date'))
        if key in received:raise ValueError('Duplicate authoritative source/month audit')
        if key not in expected:raise ValueError('Foreign source/month audit')
        received[key]=item
    table=[];state=Counter()
    for key,task in sorted(expected.items()):
        audit=received.get(key)
        if not audit:
            code='NOT_RUN';success=0;failed=task['days'];events=0
        else:
            success=audit['covered_days'];failed=audit['failed_days'];events=audit['scanned_events']
            code='COMPLETE' if audit['complete'] and success==task['days'] and failed==0 else 'INCOMPLETE'
            if success+failed+audit['unsupported_days']!=task['days']:
                raise ValueError('Unaccounted historical source days')
        state[code]+=1
        table.append({**task,'result':code,'covered_days':success,
                      'failed_or_not_run_days':failed,'observed_events':events})
    for x in plan['tasks']:
        if x['status']=='UNSUPPORTED':
            table.append({**x,'result':'UNSUPPORTED','covered_days':0,
                          'failed_or_not_run_days':x['days'],'observed_events':0})
            state['UNSUPPORTED']+=1
    region_status=[]
    for region in sorted({x['region'] for x in table}):
        values=[x for x in table if x['region']==region]
        region_status.append(dict(region=region,month_windows=len(values),
            complete=sum(x['result']=='COMPLETE' for x in values),
            incomplete=sum(x['result']!='COMPLETE' for x in values)))
    for item in plan['source_gaps']:
        if item['status']=='NO_COLLECTOR_IMPLEMENTED':
            region_status.append(dict(region=item['region'],month_windows=0,
                complete=0,incomplete=plan['month_windows'],status='NO_COLLECTOR_IMPLEMENTED'))
    return dict(schema='national-historical-coverage-ledger-v1',
        intended_period=[plan['period_start'],plan['period_end']],
        intended_days=plan['period_days'],
        total_planned_months=plan['month_windows'],
        total_supported_tasks=len(expected),
        **{key.lower()+'_tasks':value for key,value in state.items()},
        all_source_months_complete=len(received)==len(expected) and all(
            x['result']=='COMPLETE' for x in table),
        all_17_ccaa_covered=False,
        observed_source_events_not_unique_projects=sum(x['observed_events'] for x in table),
        identified_mw_is_not_aggregated_as_project_mw=True,
        source_gaps=plan['source_gaps'],
        regional_status=region_status,
        tasks=table)


def write_result(summary:dict,destination:Path):
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    trs=''.join('<tr><td>'+html.escape(x['source_code'])+'</td><td>'+
                html.escape(x['region'])+'</td><td>'+html.escape(x['month'])+'</td><td>'+
                html.escape(x['result'])+'</td><td>'+str(x['covered_days'])+'</td><td>'+
                str(x['failed_or_not_run_days'])+'</td><td>'+str(x['observed_events'])+
                '</td></tr>' for x in summary['tasks'])
    text=("<!doctype html><html lang='it'><meta charset='utf-8'><title>Spain Radar — copertura storica</title>"
          "<style>body{font:15px system-ui;max-width:1180px;margin:auto;padding:24px;color:#132c40}"
          "table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #ccd7df;padding:8px;text-align:left}"
          "</style><h1>Backfill storico nazionale — copertura effettiva</h1><p>Questa pagina mostra"
          " esclusivamente l'esito dei lotti ufficiali. Le regioni prive di collector, i lotti interrotti"
          " e gli anni senza archivio non diventano COMPLETE. Nessun evento viene automaticamente"
          " inserito nel database commerciale.</p><p><b>"+str(summary.get('complete_tasks',0))+
          "</b> lotti completi su "+str(summary['total_supported_tasks'])+" eseguibili; "
          +str(summary.get('incomplete_tasks',0))+" incompleti; "
          +str(summary.get('not_run_tasks',0))+" non eseguiti; "
          +str(summary.get('unsupported_tasks',0))+" archivi non disponibili.</p>"
          "<table><thead><tr><th>Fonte</th><th>Ambito</th><th>Mese</th><th>Stato</th>"
          "<th>Giorni OK</th><th>Giorni non verificati</th><th>Eventi letti</th></tr></thead><tbody>"
          +trs+"</tbody></table></html>")
    (destination/'index.html').write_text(text,encoding='utf-8')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--plan',required=True)
    p.add_argument('--audits',required=True)
    p.add_argument('--output',default='reports/national_24m_status')
    options=p.parse_args()
    plan=json.loads(Path(options.plan).read_text(encoding='utf-8'))
    audits=[json.loads(path.read_text(encoding='utf-8')) for path in
            Path(options.audits).rglob('audit.json')]
    result=coverage(plan,audits)
    write_result(result,Path(options.output))
    print('NATIONAL_24M_COVERAGE',json.dumps({k:v for k,v in result.items()
          if k not in ('tasks','regional_status','source_gaps')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
