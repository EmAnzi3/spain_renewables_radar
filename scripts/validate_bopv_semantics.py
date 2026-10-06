"""Classify every reviewed BOPV candidate from a frozen verified source archive.

Rebuild the original dated index, verify all raw bytes, and compare extraction
with independent reviewed expectations. No source is enabled or event persisted.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import csv
from datetime import date,datetime,timedelta,timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import runpy

from app.bopv_semantics import classify_document,paragraphs_from_html

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('project_name','technology','power_mw','expediente','promoter','site_municipalities_text','province','event_type','commercial_stage')


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def load_index(root,expected_run):
    module=runpy.run_path(str(ROOT/'.github/scripts/reconcile_bopv_index.py'))
    probe=runpy.run_path(str(ROOT/'.github/scripts/probe_bopv_dates.py'))
    search_root=root/'bopv_date_probe';summary_root=root/'bopv_reconciliation'
    audit=read(summary_root/'audit.json')
    if audit.get('run_id')!=expected_run or audit.get('index_reconciled') is not True:
        raise ValueError('Expected verified source-index run is absent')
    start,end,search,labels=module['original_search'](search_root,probe)
    if (end-start).days!=29 or (str(start),str(end))!=(audit['window_start'],audit['window_end']):
        raise ValueError('Source windows do not agree')
    receipts=read(summary_root/'acquisitions.json');originals={}
    for receipt in receipts:
        sha=receipt.get('sha256','')
        if not re.fullmatch(r'[0-9a-f]{64}',sha) or receipt['label'] in originals:
            raise ValueError('Invalid or duplicated original receipt')
        raw=(summary_root/'raw'/(sha+'.html')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha or len(raw)!=receipt['bytes'] or receipt['status']!=200:
            raise ValueError('Summary/calendar source integrity failure')
        if datetime.fromisoformat(receipt['retrieved_at']).tzinfo is None:
            raise ValueError('Source receipt has no timezone')
        originals[receipt['label']]=(raw,receipt)
    days=[start+timedelta(days=n) for n in range(30)];calendars={};entries={};editions=0
    for year,month in sorted({(d.year,d.month) for d in days}):
        raw,r=originals[f'calendar-{year}-{month}']
        if r['url']!=module['HOST']+f'/bopv2/datos/{month:02d}{year}.shtml':
            raise ValueError('Calendar request scope differs')
        calendars.update(module['parse_calendar'](raw.decode(r['encoding']),year,month))
    for day in days:
        for filename in calendars.get(day,[]):
            raw,r=originals['summary-'+filename]
            if r['url']!=module['HOST']+'/bopv2/datos/'+day.strftime('%Y/%m/')+filename:
                raise ValueError('Edition request scope differs')
            rows=module['parse_summary'](raw.decode(r['encoding']),r['url'],day,filename)
            if set(rows)&set(entries):raise ValueError('Overlapping edition identities')
            entries.update(rows);editions+=1
    module['reconcile'](entries,search)
    if list(entries.values())!=read(summary_root/'dispositions.json') or len(entries)!=audit['summary_dispositions'] or editions!=audit['editions']:
        raise ValueError('Frozen generated index differs from rebuilt originals')
    candidates=read(search_root/'title_candidates.json')
    reconstructed=[row for row in search.values() if re.search(r'fotovolta|e[oó]lic|almacenamiento|bater[ií]a|hibrid',row['title'],re.I)]
    if candidates!=reconstructed:raise ValueError('Candidate selection changed from complete original index')
    checked=[]
    for candidate in candidates:
        identity=candidate['external_id'];raw,receipt=labels['candidate-'+identity.replace('/','-')]
        module['body_provenance'](raw.decode(receipt['encoding']),receipt['url'],entries[identity])
        checked.append((entries[identity],raw,receipt))
    return audit,checked


def check_review(result,raw,review):
    if hashlib.sha256(raw).hexdigest()!=review['raw_html_sha256']:
        raise ValueError('Reviewed original body changed')
    if result['classification']!=review['classification'] or result['publication_date']!=review['publication_date']:
        raise ValueError('Reviewed class/publication date changed')
    actual=[{k:a.get(k) for k in FIELDS} for a in result['assets']]
    if actual!=review['assets']:raise ValueError('Per-plant extraction differs from reviewed source: '+result['external_id'])
    if result['database_events_created']!=0 or result['collector_enabled']:
        raise ValueError('Classification cannot claim collector activation')
    for asset in result['assets']:
        if asset['epc'] is not None or asset['work_start'] is not None or asset['work_end'] is not None or asset['permit_to_build_inferred']:
            raise ValueError('Unsupported EPC, work dates or construction permit')


def render(output,documents):
    records=[]
    for doc in documents:
        for asset in doc['assets']:
            row={'classification':doc['classification'],'document':doc['external_id'],
                 'publication_date':doc['publication_date'],**{k:asset[k] for k in FIELDS},
                 'source_url':doc['source_url'],'source_html':doc['original_html_file']}
            records.append(row)
    def cell(v):
        return html.escape('—' if v is None else str(v),quote=True)
    table=''.join('<tr>'+''.join('<td>'+cell(row[k])+'</td>' for k in ('classification','document','publication_date',*FIELDS))+
        '<td><a href="'+cell(row['source_html'])+'">Originale HTML</a></td></tr>' for row in records)
    output.joinpath('index.html').write_text('<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BOPV — atti classificati</title><style>body{font:15px/1.5 system-ui;margin:24px}table{border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid;vertical-align:top;text-align:left}.scroll{overflow:auto}</style><h1>BOPV — atti classificati</h1><p>Classificazione degli originali della finestra 6 settembre–5 ottobre 2026. Le richieste rimangono tali. La dichiarazione ambientale non è un permesso di costruzione. L’autoconsumo industriale è conservato separatamente, senza sommare MW, MWh e kVA.</p><p>Riferimenti mancanti restano vuoti; identità senza expediente provvisoria. Tabelle disponibili soltanto nei PDF non sono state interpretate. Nessuna fonte abilitata e nessun evento scritto nel radar da questo controllo.</p><div class="scroll"><table><thead><tr>'+''.join('<th>'+cell(k)+'</th>' for k in ('Categoria','Atto','Pubblicazione',*FIELDS,'Fonte'))+'</tr></thead><tbody>'+table+'</tbody></table></div><p><a href="classified_documents.json">Testi, quantità ed evidenze esatte per paragrafo</a></p></html>',encoding='utf-8')
    with (output/'assets.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]) if records else []);writer.writeheader()
        for row in records:
            writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()})
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',required=True)
    parser.add_argument('--expected-run',default='37420987792')
    parser.add_argument('--output',default='reports/bopv_semantics')
    args=parser.parse_args();output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    report={'run_id':os.getenv('GITHUB_RUN_ID'),'head_sha':os.getenv('GITHUB_SHA'),
        'source_index_run':args.expected_run,'classification_validated':False,
        'collector_enabled':False,'database_events_created':0,'new_source_downloads':0}
    try:
        audit,candidates=load_index(Path(args.source_root),args.expected_run)
        review=read(ROOT/'tests/fixtures/bopv_semantic_review.json')
        if set(review)!=set(item[0]['external_id'] for item in candidates):raise ValueError('Reviewed cases differ from full candidate set')
        documents=[]
        for record,raw,receipt in candidates:
            ps=paragraphs_from_html(raw,receipt['encoding']);before=copy.deepcopy((record,ps))
            result=classify_document(record,ps)
            if (record,ps)!=before or classify_document(*copy.deepcopy(before))!=result:
                raise ValueError('Classification mutates original data or is not deterministic')
            if result['classification']=='REVIEW_REQUIRED':raise ValueError('Unresolved candidate: '+record['external_id'])
            check_review(result,raw,review[record['external_id']])
            original='originals/'+receipt['sha256']+'.html';(output/'originals').mkdir(exist_ok=True)
            (output/original).write_bytes(raw)
            result.update(original_html_file=original,raw_html_sha256=receipt['sha256'],
                          original_retrieved_at=receipt['retrieved_at'],encoding=receipt['encoding'])
            documents.append(result)
            print('BOPV_CLASSIFIED',json.dumps({'id':record['external_id'],'classification':result['classification'],
                'assets':[{k:a[k] for k in FIELDS} for a in result['assets']]},ensure_ascii=False),flush=True)
        (output/'classified_documents.json').write_text(json.dumps(documents,ensure_ascii=False,indent=2),encoding='utf-8')
        render(output,documents)
        energy=[a for d in documents if d['classification']=='ENERGY_ACT' for a in d['assets']]
        leads=[a for d in documents if d['classification']!='ENERGY_ACT' for a in d['assets']]
        report.update(classification_validated=True,window_start=audit['window_start'],window_end=audit['window_end'],
            index_dispositions=audit['summary_dispositions'],source_days=audit['source_days'],
            documents=len(documents),energy_assets=len(energy),separate_lead_assets=len(leads),
            classes=dict(Counter(d['classification'] for d in documents)),
            energy_event_types=dict(Counter(a['event_type'] for a in energy)),
            missing_own_references=sum(a['expediente'] is None for a in energy),
            exact_original_replay=True,index_rebuilt_from_originals=True,
            all_candidates_accounted_for=True,original_dates_preserved=True,
            evidence_scope='Original HTML paragraphs; PDF-only tables explicitly flagged; no OCR',
            completed_at=datetime.now(timezone.utc).isoformat())
        print('BOPV_SEMANTICS_VERIFIED',json.dumps(report),flush=True)
    except Exception as exc:
        report.update(error_type=type(exc).__name__,error=str(exc));raise
    finally:
        (output/'validation_metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
