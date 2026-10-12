"""Reconcile official historical source-month archives without false project merging.

This report is a review layer: it never modifies the production SQLite or
claims a project's current commercial state from an older administrative act.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import html
import json
from pathlib import Path
import re
from app.parser import ParsedEvent

from app.historical_backfill import (
    SCANNABLE, REGIONAL_GAZETTES, MISSING_GAZETTES, official_event, issues,
)

GENERIC = re.compile(r"^(?:plantas?\s+(?:solares?\s+)?fotovoltaicas?|instalaciones?\s+fotovoltaicas?|renombre|bolet[ií]n oficial)$",re.I)


def _sha(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def validate_bundle(folder:Path):
    audit=json.loads((folder/"audit.json").read_text(encoding="utf-8"))
    if audit.get("schema")!="official-source-month-observations-v1" or audit.get("source_code") not in SCANNABLE:
        raise ValueError("Foreign source-batch schema")
    start,end=date.fromisoformat(audit['from_date']),date.fromisoformat(audit['until_date'])
    if not 1<=(end-start).days+1<=31 or audit['intended_source_days']!=(end-start).days+1:
        raise ValueError("Invalid monthly source-day scope")
    daily=audit['days']
    if len(daily)!=(end-start).days+1 or {x['date'] for x in daily}!={str(start+timedelta(days=i)) for i in range((end-start).days+1)}:
        raise ValueError("Missing or repeated source-day evidence")
    complete=sum(x['status']=='COMPLETE' for x in daily)
    failed=sum(x['status']=='ERROR' for x in daily)
    unsupported=sum(x['status']=='UNSUPPORTED' for x in daily)
    if (complete!=audit['covered_days'] or failed!=audit['failed_days'] or unsupported!=audit['unsupported_days']
        or audit['complete']!=(complete==len(daily)) or audit['status']!=('COMPLETE' if complete==len(daily) else 'INCOMPLETE')):
        raise ValueError("Source batch is incorrectly certified")
    events=json.loads((folder/"events.json").read_text(encoding="utf-8"))
    if len(events)!=audit['scanned_events']:
        raise ValueError("Source candidate count differs")
    for r in events:
        day=date.fromisoformat(r['publication_date'])
        if not start<=day<=end:raise ValueError("Event from a foreign date")
        official_event(ParsedEvent(**r),audit['source_code'],day)
    for d in daily:
        own=[x for x in events if x['publication_date']==d['date']]
        if d['status']=='COMPLETE':
            if len(own)!=d['accepted'] or _sha(own)!=d['original_sha256']:
                raise ValueError("Source original day digest/identity differs")
        elif own:raise ValueError("Events cannot be certified for incomplete days")
    return audit,events


def aggregate(folders:list[Path],plan:dict|None=None):
    reports={};all_events={};collisions=[]
    for folder in folders:
        audit,events=validate_bundle(folder)
        key=(audit['source_code'],audit['from_date'],audit['until_date'])
        if key in reports:raise ValueError("Duplicate historical source-month audit")
        reports[key]=audit
        for event in events:
            key_id=(event['source_code'],event['external_id'])
            prior=all_events.get(key_id)
            if prior and (prior['publication_date'],prior['title'],prior['url'],prior['raw_text'])!=(
                event['publication_date'],event['title'],event['url'],event['raw_text']):
                collisions.append(dict(source_code=key_id[0],external_id=key_id[1],
                    error="SOURCE_ID_REUSED_WITH_DIFFERING_OFFICIAL_BYTES"))
                all_events.pop(key_id,None)
                continue
            if not any(x['source_code']==key_id[0] and x['external_id']==key_id[1] for x in collisions):
                all_events[key_id]=event
    project_groups=defaultdict(list)
    for record in all_events.values():
        key=record.get('project_key') or ''
        if key:project_groups[key].append(record)
    rows=[];identification_conflicts=[]
    for key,events in project_groups.items():
        signatures={(re.sub(r'\s+',' ',e['project_name'] or '').casefold(),e['technology'])
                    for e in events if e.get('project_name')}
        if len(signatures)>1:
            identification_conflicts.append(dict(project_key=key,
                sources=sorted({e['source_code'] for e in events}),
                titles=sorted({e['project_name'] for e in events if e.get('project_name')}),
                resolution="REVIEW_REQUIRED_IDENTITY_COLLISION_NO_AUTO_MERGE"))
            continue
        named=next((e for e in events if e.get('project_name')),None)
        if not named or GENERIC.search(named['project_name']):continue
        capacities={float(e['power_mw']) for e in events if e.get('power_mw') is not None and e['power_mw']>0}
        companies={e['promoter'] for e in events if e.get('promoter')}
        provinces={e['province'] for e in events if e.get('province')}
        rows.append(dict(project_key=key,name=named['project_name'],technology=named['technology'],
            province=next(iter(provinces)) if len(provinces)==1 else None,
            geography_review=len(provinces)!=1,
            power_mw=next(iter(capacities)) if len(capacities)==1 else None,
            power_conflict=len(capacities)>1,
            promoter=next(iter(companies)) if len(companies)==1 else None,
            promoter_conflict=len(companies)>1,
            earliest_date=min(e['publication_date'] for e in events),
            latest_date=max(e['publication_date'] for e in events),
            sources=sorted({e['source_code'] for e in events}),
            event_count=len(events),
            status_note="HISTORICAL_ACTS_NOT_CURRENT_CONSTRUCTION_CONFIRMATION"))
    rows.sort(key=lambda p:(p['latest_date'],p['name']),reverse=True)
    provincial=Counter(e.get('province') or "UNALLOCATED" for e in all_events.values())
    return dict(schema="official-national-historical-reconciliation-v1",
        scanned_bundle_count=len(reports),
        complete_batches=sum(r['complete'] for r in reports.values()),
        incomplete_batches=sum(not r['complete'] for r in reports.values()),
        source_days_covered=sum(r['covered_days'] for r in reports.values()),
        source_days_failed=sum(r['failed_days'] for r in reports.values()),
        source_days_unsupported=sum(r['unsupported_days'] for r in reports.values()),
        unique_official_event_ids=len(all_events),
        provisional_named_project_groups=len(rows),
        project_identity_conflicts=identification_conflicts,
        official_identity_conflicts=collisions,
        no_new_production_project_rows=True,all_regions_certified=False,
        known_regional_gazettes=len(REGIONAL_GAZETTES),
        regional_gazettes_without_collector=MISSING_GAZETTES,
        plan_period=(plan['period_start'],plan['period_end']) if plan else None,
        provinces_observed_events=provincial,
        scanned_batches=[dict(source_code=r['source_code'],region=r['region'],
             start=r['from_date'],end=r['until_date'],status=r['status'],
             observed_events=r['scanned_events'],days_ok=r['covered_days'],
             days_failed=r['failed_days'],days_unsupported=r['unsupported_days'])
             for r in reports.values()],
        projects=rows,
        observed_events=list(all_events.values()))


def output_reports(summary:dict,output:Path):
    output.mkdir(parents=True,exist_ok=True)
    public={k:v for k,v in summary.items() if k not in ('observed_events','projects')}
    public['provinces_observed_events']=dict(public['provinces_observed_events'])
    (output/'audit.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'projects.json').write_text(json.dumps(summary['projects'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'events.json').write_text(json.dumps(summary['observed_events'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows=[]
    for x in summary['observed_events']:
        flag="; ".join(issues(x))
        url=html.escape(x['url'],quote=True)
        rows.append('<tr><td>'+html.escape(x['publication_date'])+'</td><td>'+html.escape(x['source_code'])+
                    '</td><td>'+html.escape(x.get('province') or '')+'</td><td>'+
                    html.escape(x.get('project_name') or x['title'])+'</td><td>'+
                    html.escape(str(x.get('power_mw') if x.get('power_mw') is not None else ''))+'</td><td>'+
                    html.escape(x.get('promoter') or '')+'</td><td>'+
                    html.escape(x.get('event_type') or '')+'</td><td>'+
                    html.escape(flag)+'</td><td><a target="_blank" rel="noopener" href="'+url+'">Fonte</a></td></tr>')
    table=''.join(rows)
    source_summary=''.join('<li>'+html.escape(x['source_code'])+' '+html.escape(x['start'])+'–'+
        html.escape(x['end'])+': <b>'+html.escape(x['status'])+'</b>, '+str(x['observed_events'])+
        ' eventi, '+str(x['days_ok'])+' giornate verificate, '+str(x['days_failed'])+
        ' errori.</li>' for x in summary['scanned_batches'])
    body="""<!doctype html><html lang="it"><meta charset="utf-8"><title>Radar Spagna — storici ufficiali</title>
<style>body{font:15px/1.5 system-ui;max-width:1400px;margin:auto;padding:22px;color:#193345}
table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}
td{max-width:300px;overflow-wrap:anywhere}label,input{font:inherit}input{padding:10px;width:min(500px,100%)}
.status{padding:13px;background:#fff1d9;border:1px solid #d3a95a}</style><h1>Acquisizione storica — fonti ufficiali</h1>
<p class="status">Inventario preliminare degli atti. Non è una certificazione completa delle 17 comunità autonome.
I MW qui rappresentano singoli eventi e non sono sommabili come potenza installata unica.
I progetti non sono automaticamente cantieri attivi.</p><p><b>""" + str(summary['unique_official_event_ids']) + """</b> eventi osservati su <b>""" +str(summary['source_days_covered'])+"""</b> giornate-fonte.
Gruppi provvisori con nome: <b>"""+str(summary['provisional_named_project_groups'])+"""</b>. Atti con identità da rivedere:
<b>"""+str(len(summary['project_identity_conflicts']))+"""</b>.</p><details><summary>Fonti e finestre effettivamente verificate</summary><ul>"""+source_summary+"""</ul></details>
<p><label>Cerca Huelva, un progetto, un'impresa o una provincia:
<input id="search" type="search" placeholder="Filtra gli atti"></label></p>
<div style="overflow:auto"><table id="acts"><thead><tr><th>Data</th><th>Fonte</th><th>Provincia</th>
<th>Oggetto</th><th>MW</th><th>Proponente estratto</th><th>Evento</th><th>Controlli</th><th>Documento</th>
</tr></thead><tbody>"""+table+"""</tbody></table></div>
<script>document.getElementById('search').addEventListener('input',e=>{const q=e.target.value.toLocaleLowerCase();
for(const r of document.querySelectorAll('#acts tbody tr')){r.hidden=!r.textContent.toLocaleLowerCase().includes(q)}})</script></html>"""
    (output/'index.html').write_text(body,encoding='utf-8')
    return public


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-root',required=True)
    p.add_argument('--output',default="reports/national_historical_review")
    p.add_argument('--plan')
    opts=p.parse_args()
    source=Path(opts.input_root)
    folders=sorted({f.parent for f in source.rglob('audit.json')
                    if (f.parent/'events.json').is_file()})
    if not folders:raise ValueError("No original historical source-month evidence to reconcile")
    plan=json.loads(Path(opts.plan).read_text(encoding='utf-8')) if opts.plan else None
    result=aggregate(folders,plan)
    output_reports(result,Path(opts.output))
    print('NATIONAL_HISTORICAL_RECONCILIATION',json.dumps({
        k:v for k,v in result.items() if k not in ('projects','observed_events','scanned_batches',
                            'provinces_observed_events','regional_gazettes_without_collector','project_identity_conflicts','official_identity_conflicts')
    },ensure_ascii=False),flush=True)
    if result['official_identity_conflicts']:
        raise SystemExit('Contradictory official identities detected: review original source bundles')


if __name__=="__main__": main()
