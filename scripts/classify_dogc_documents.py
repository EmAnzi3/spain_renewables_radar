"""Classify a frozen DOGC evidence bundle after strict index/PDF replay.

This is a semantic validation/report command, NOT a production collector. The
review fixture locks all input identities and expected decisions independently
of the parser. Unknown wording remains a failed gate, not a dropped document.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone

from app.dogc_semantics import VERSION, classify_document, verify_evidence

LABELS = {
 'ENERGY_PROJECT':'Procedimenti energetici', 'MUNICIPAL_PROJECT':'Progetti comunali / locali',
 'CORRECTION':'Rettifica di un atto precedente', 'OUT_OF_SCOPE':'Non pertinente',
 'REVIEW_REQUIRED':'Da classificare',
 'ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA':'Screening ambientale: VIA ordinaria non richiesta',
 'ENVIRONMENTAL_DIA_COMPATIBLE':'Giudizio di compatibilità ambientale',
 'PUBLIC_INFO_AUTHORIZATION_REQUEST':'Consultazione su richiesta di autorizzazione',
 'PUBLIC_INFO_PUBLIC_UTILITY':'Consultazione sulla pubblica utilità',
 'PUBLIC_INFO_LAND_USE':'Consultazione urbanistica',
 'PRIOR_AND_CONSTRUCTION_AUTH':'Autorizzazione preventiva e alla costruzione concesse',
 'PUBLIC_UTILITY_GRANTED':'Pubblica utilità dichiarata',
 'MUNICIPAL_FINAL_PROJECT_APPROVAL':'Approvazione definitiva del progetto locale',
 'MUNICIPAL_INITIAL_PROJECT_APPROVAL':'Approvazione iniziale del progetto locale',
 'MATERIAL_STORAGE_NOT_ENERGY_STORAGE':'Stoccaggio di metalli, non accumulo elettrico',
 'DATA_CENTRE_NOT_RENEWABLE_PLANT':'Data center, non progetto rinnovabile',
 'MOBILITY_INCENTIVE_RULES_NOT_PLANT':'Regole di incentivo alla mobilità, non impianto',
 'ORDINARY_EIA_REQUIRED':'VIA ordinaria richiesta, non diniego',
 'PV':'Fotovoltaico','WIND':'Eolico','BESS':'Accumulo','UNALLOCATED':'Non attribuito a una componente',
 'PEAK_DC':'Potenza di picco DC','NOMINAL_AC':'Potenza nominale AC',
 'INSTALLED_POWER':'Potenza installata','GRID_ACCESS':'Potenza di accesso alla rete',
 'REGULATED_POWER':'Potenza regolata','INVERTER_POWER':'Potenza degli inverter',
 'CHARGE_DISCHARGE_POWER':'Potenza di carica/scarica','STORAGE_ENERGY':'Energia accumulabile',
 'SOURCE_HYBRID_TOTAL':'Totale ibrido dichiarato dalla fonte, non ripartito',
 'ANNUAL_GENERATION':'Produzione annua, non capacità di accumulo',
 'DEVICE_UNIT_POWER':'Potenza di un dispositivo, non totale impianto',
 'DEVICE_UNIT_ENERGY':'Energia di un dispositivo, non totale impianto',
 'EXISTING_CAPACITY_NOT_INCREMENT':'Potenza esistente, non potenza aggiunta',
 'UNSPECIFIED_POWER':'Potenza con base non specificata',
 'INDEX_TITLE':'Titolo della fonte','CURRENT_TECHNICAL_BODY':'Descrizione tecnica corrente',
}


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def check_review_fixture(records: list[dict], fixture: dict) -> dict:
    """Reject missing/extra cases, wrong decisions, unsafe merges and numeric drift."""
    actual={r['document_id']:r for r in records}
    expected={r['document_id']:r for r in fixture['documents']}
    if len(actual)!=len(records) or len(expected)!=len(fixture['documents']) or set(actual)!=set(expected):
        raise ValueError('Reviewed identities differ from classified document identities')
    for identity, case in expected.items():
        row=actual[identity]
        for field in ('event','category','pdf_sha256','page_count'):
            if row.get(field)!=case[field]:
                raise ValueError(f'Reviewed {field} differs for {identity}: {row.get(field)} != {case[field]}')
        if not row.get('document_classified') or not row.get('decision'):
            raise ValueError('A reviewed act lacks an operative decision: '+identity)
        for field in fixture['unchanged_empty_fields']:
            if row.get(field) is not None:
                raise ValueError('An unsupported field was populated: '+field)
        for field in ('production_enabled','automatic_project_merge','live_collector_validated','field_completeness_certified'):
            if row.get(field) is not False:
                raise ValueError('Development boundary changed: '+field)
        if row.get('database_writes')!=0 or any(c.get('capacity_mw') is not None for c in row['components']):
            raise ValueError('Unreviewed scalar capacity or database write')
        if any(q.get('aggregation_allowed') is not False for q in row['capacity_observations']):
            raise ValueError('Mixed capacities were made summable')
    conflict_ids=sorted(r['document_id'] for r in records if r['capacity_conflicts'])
    if conflict_ids!=sorted(fixture['capacity_conflict_document_ids']):
        raise ValueError('Capacity conflict set differs from the reviewed originals')
    for case in fixture['quantity_cases']:
        identity=case['id']; wanted={k:v for k,v in case.items() if k!='id'}
        candidates=actual[identity]['capacity_observations']
        found=[]
        for quantity in candidates:
            equal=True
            for key,value in wanted.items():
                observed=quantity.get(key)
                if key=='normalized_value':
                    equal=equal and observed is not None and Decimal(observed)==Decimal(value)
                else:
                    equal=equal and observed==value
            if equal: found.append(quantity)
        if not found:
            raise ValueError('Reviewed typed quantity is absent: '+identity+' '+str(wanted))
    for identity, refs in fixture['primary_reference_cases'].items():
        if sorted(v['value'] for v in actual[identity]['primary_references'])!=sorted(refs):
            raise ValueError('Current and historical/shared references were mixed: '+identity)
    correction=actual['1054540']['correction']
    if (not correction or correction['automatic_lifecycle_change'] is not False
            or correction['corrected_interpretation']!='ENVIRONMENTAL_SCREENING_NO_ORDINARY_EIA'):
        raise ValueError('Reviewed environmental correction lost its meaning/boundary')
    for identity in ('1054484','1054443'):
        if 'EXISTING_PV_AUTHORIZATION_DOES_NOT_AUTHORIZE_NEW_STORAGE' not in actual[identity]['flags']:
            raise ValueError('Hybrid expansion lost its existing/new distinction')
    if 'EXISTING_CAPACITY_IS_NOT_ADDED_CAPACITY' not in actual['1054455']['flags']:
        raise ValueError('Bordils existing capacity was presented as the expansion')
    if 'SHARED_EVACUATION_DOES_NOT_CREATE_ADDITIONAL_PLANTS' not in actual['1055360']['flags']:
        raise ValueError('Shared grid works were presented as extra plants')
    return {'reviewed_document_cases':len(expected),'reviewed_quantity_cases':len(fixture['quantity_cases']),
            'reviewed_reference_cases':len(fixture['primary_reference_cases']),
            'reviewed_capacity_conflict_ids':conflict_ids,'review_fixture_passed':True}


def unique_evidence_count(records: list[dict]) -> int:
    found=set()
    def walk(value, identity):
        if isinstance(value,dict):
            if {'page','start','end','page_text_sha256','quote'}<=value.keys():
                found.add((identity,value['page'],value['start'],value['end'],value['page_text_sha256']))
            for v in value.values():walk(v,identity)
        elif isinstance(value,list):
            for v in value:walk(v,identity)
    for record in records:walk(record,record['document_id'])
    return len(found)


def render_report(output: Path, records: list[dict], result: dict) -> None:
    """Self-contained offline HTML. PDF originals are copied, never rewritten."""
    esc=lambda value:html.escape(str(value),quote=True)
    label=lambda value:esc(LABELS.get(value,value))
    def spans(record, values):
        return ''.join('<blockquote><a href="pdf/'+esc(record['document_id'])+'.pdf#page='+str(v['page'])+'">Pagina '+str(v['page'])+'</a><pre>'+esc(v['quote'])+'</pre></blockquote>' for v in values)
    cards=[]
    for record in records:
        identity=record['document_id']
        name=record['project_name']['value'] if record['project_name'] else record['source_title']
        refs=' · '.join(v['value'] for v in record['primary_references']) or 'Non determinato dal campo corrente'
        proponent=record['proponent']['value'] if record['proponent'] else 'Non estratto'
        location=record['location_text']['value'] if record['location_text'] else 'Consultare la localizzazione nel testo originale'
        evidence=spans(record,record['decision']['evidence']) if record['decision'] else '<p>Decisione da verificare.</p>'
        rows=''
        for q in record['capacity_observations']:
            rows+='<tr><td>'+label(q['component'])+'</td><td>'+label(q['basis'])+'</td><td>'+esc(q['source_number']+' '+q['source_unit'])+'</td><td>'+esc(q['normalized_value']+' '+q['normalized_unit'])+'</td><td>'+label(q['scope'])+'<details><summary>Passaggio originale</summary>'+spans(record,q['evidence'])+'</details></td></tr>'
        quantities=('<div class="scroll"><table><thead><tr><th>Componente</th><th>Significato</th><th>Dato originale</th><th>Conversione letterale</th><th>Origine</th></tr></thead><tbody>'+rows+'</tbody></table></div>' if rows else '<p>Nessuna potenza estratta con evidenza sufficiente.</p>')
        conflicts=('<p class="warning"><strong>Discordanza nella fonte:</strong> potenze o unità del titolo e della descrizione tecnica non coincidono. Nessuna correzione automatica; nessun totale utilizzabile.</p>' if record['capacity_conflicts'] else '')
        note=''
        if 'EXISTING_CAPACITY_IS_NOT_ADDED_CAPACITY' in record['flags']:
            note+='<p class="warning">La potenza indicata è quella dell’impianto esistente. La potenza aggiuntiva dell’ampliamento non è determinata.</p>'
        if 'EXISTING_PV_AUTHORIZATION_DOES_NOT_AUTHORIZE_NEW_STORAGE' in record['flags']:
            note+='<p>Il fotovoltaico preesistente e il nuovo accumulo richiesto restano distinti. Il vecchio permesso non autorizza la nuova batteria.</p>'
        if record['correction']:
            note+='<h4>Testo precedente</h4>'+spans(record,record['correction']['previous_wording']['evidence'])+'<h4>Testo rettificato</h4>'+spans(record,record['correction']['replacement_wording']['evidence'])+'<p>Rettifica di un atto precedente, non nuovo progetto o nuovo permesso. Nessuna modifica automatica al lifecycle.</p>'
        if record['time_terms']:
            note+='<h4>Termini amministrativi</h4>'+''.join(spans(record,t['evidence']) for t in record['time_terms'])+'<p>Il termine di messa in servizio non determina inizio e fine dei lavori.</p>'
        flags='<details><summary>Avvertenze e provenienza</summary><p>'+esc(' · '.join(record['flags']))+'</p><p>PDF SHA-256: <code>'+esc(record['pdf_sha256'])+'</code></p><p>Acquisito originariamente: '+esc(record['source_retrieved_at'])+'</p></details>'
        search=(name+' '+record['source_title']+' '+refs+' '+proponent+' '+location).casefold()
        cards.append('<article data-category="'+esc(record['category'])+'" data-event="'+esc(record['event'])+'" data-search="'+esc(search)+'"><p class="eyebrow">'+esc(record['publication_date'])+' · DOGC '+esc(record['edition'])+' · ID '+identity+'</p><h2>'+esc(name)+'</h2><p><strong>'+label(record['event'])+'</strong></p>'+conflicts+note+'<p>'+label(record['category'])+' · '+esc(', '.join(LABELS.get(t,t) for t in record['technologies']))+'</p><p><b>Riferimenti:</b> '+esc(refs)+'<br><b>Proponente:</b> '+esc(proponent)+'<br><b>Localizzazione riportata:</b> '+esc(location)+'</p><p><a href="pdf/'+identity+'.pdf">PDF originale, '+str(record['page_count'])+' pagine</a> · <a href="'+esc(record['source_url'])+'" rel="noreferrer">Fonte DOGC</a> · <a href="records/'+identity+'.json">Dati con evidenze</a></p><details><summary>Decisione: verifica il passaggio originale</summary>'+evidence+'</details><details><summary>Potenze ed energia: osservazioni distinte, non sommabili</summary>'+quantities+'</details><p class="muted">Inizio/fine lavori: non determinati. EPC/BoP: non accertati. Campi anagrafici non certificati come completi.</p>'+flags+'</article>')
    options=''.join('<option value="'+esc(k)+'">'+label(k)+' ('+str(v)+')</option>' for k,v in result['categories'].items())
    events=''.join('<option value="'+esc(k)+'">'+label(k)+' ('+str(v)+')</option>' for k,v in result['events'].items())
    text='''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DOGC — atti classificati</title><style>
    :root{font:16px/1.55 system-ui,sans-serif;color:#172b40;background:#edf2f6}body{margin:0}main{max-width:1240px;margin:auto;padding:24px}header,article,.filters{background:white;padding:24px;margin:0 0 18px;border-radius:10px;border:1px solid #d2dce5}h1{font-size:2rem;margin:0 0 12px}h2{font-size:1.3rem;line-height:1.4;margin:0 0 12px}h4{margin-bottom:4px}a{color:#075b91}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;margin:6px 0}.eyebrow,.muted{color:#526777;font-size:.9rem}.warning{background:#fff5df;border-left:4px solid #9b6500;padding:14px}details{padding:10px 0}summary{cursor:pointer;font-weight:600}blockquote{margin:12px 0;padding:12px 16px;background:#f2f5f7;border-left:3px solid #728a9b}select,input{font:inherit;padding:10px;max-width:100%;border:1px solid #aebdca;background:white;color:#172b40;border-radius:4px;box-sizing:border-box}input{width:100%}.filters{display:grid;gap:12px}.scroll{overflow:auto}table{border-collapse:collapse;min-width:800px;width:100%}th,td{vertical-align:top;text-align:left;padding:10px;border-bottom:1px solid #d2dce5}td pre{max-width:480px}code{overflow-wrap:anywhere}[hidden]{display:none!important}@media(max-width:600px){main{padding:12px}header,article,.filters{padding:16px}h1{font-size:1.65rem}}
    </style><main><header><p class="eyebrow">SPAIN RENEWABLES RADAR · VERIFICA DOCUMENTALE DOGC</p><h1>48 atti, non 48 opportunità</h1><p>Pubblicazioni dal 5 settembre al 4 ottobre 2026. Classificazione del dispositivo con evidenze di pagina: 33 procedimenti energetici, 11 progetti locali, una rettifica e tre atti non pertinenti.</p><p><strong>Otto atti concedono autorizzazioni preventive e alla costruzione.</strong> Questo non dimostra che i cantieri siano iniziati. Le approvazioni comunali e i giudizi ambientali non diventano permessi energetici.</p><p>Le sei discord anze di potenza/unità sono mantenute irrisolte. Fotovoltaico, batterie, potenze di rete, componenti preesistenti, singoli dispositivi e produzione annua restano distinti.</p><p>Il report è separato dalla produzione: nessun evento scritto nel radar, nessun totale MW aggregato, nessun abbinamento automatico tra atti e progetti. Gli originali PDF sono conservati senza modifiche.</p><p><a href="audit.json">Esito dei controlli</a> · <a href="classifications.json">Tutte le classificazioni JSON</a></p></header>'''.replace('discord anze','discordanze')
    text+='<section class="filters"><label>Ricerca nei nomi, riferimenti e testi del titolo<input id="search" type="search" placeholder="Esempio: Vic, Folgueroles, FUE-2025…"></label><label>Tipo di documento <select id="category"><option value="">Tutte le categorie</option>'+options+'</select></label><label>Decisione <select id="event"><option value="">Tutte le decisioni</option>'+events+'</select></label><p id="count"></p></section>'+''.join(cards)
    text+='''<script>const cards=[...document.querySelectorAll('article')],s=document.getElementById('search'),c=document.getElementById('category'),e=document.getElementById('event');function filter(){const q=s.value.toLocaleLowerCase().trim();let n=0;for(const card of cards){const yes=(!q||card.dataset.search.includes(q))&&(!c.value||card.dataset.category===c.value)&&(!e.value||card.dataset.event===e.value);card.hidden=!yes;if(yes)n++;}document.getElementById('count').textContent=n+' atti visualizzati su '+cards.length;}for(const x of [s,c,e])x.addEventListener('input',filter);filter();</script></main></html>'''
    (output/'index.html').write_text(text,encoding='utf-8')


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-root',required=True);parser.add_argument('--body-root',required=True)
    parser.add_argument('--expected-index-run',required=True);parser.add_argument('--expected-body-run',required=True)
    parser.add_argument('--fixture',default='tests/fixtures/dogc_review_20261004.json')
    parser.add_argument('--output',default='reports/dogc_semantics')
    args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    status={'schema_version':VERSION,'head_sha':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID'),
            'verified_at':datetime.now(timezone.utc).isoformat(),'semantic_gate_passed':False,
            'database_writes':0,'project_events_created':0,'production_enabled':False,
            'live_collector_validated':False,'field_completeness_certified':False,'new_source_downloads':0}
    try:
        # Import here so synthetic parser/review tests do not require PDF/network libraries.
        from scripts.acquire_dogc_bodies import load_verified_index
        from scripts.recheck_dogc_bodies import verify_bundle, safe_file
        fixture_path=Path(args.fixture);fixture=json.loads(fixture_path.read_text(encoding='utf-8'))
        if fixture['index_run_id']!=args.expected_index_run or fixture['body_run_id']!=args.expected_body_run:
            raise ValueError('Review fixture belongs to another frozen source acquisition')
        audit,candidates=load_verified_index(Path(args.index_root),args.expected_index_run)
        if audit['index_sha256']!=fixture['index_sha256']:raise ValueError('Reviewed index digest changed')
        bodyroot=Path(args.body_root)
        replay=verify_bundle(bodyroot,candidates,args.expected_body_run,require_exact_text=True)
        write_json(output/'original_replay.json',replay)
        generation=bodyroot/replay['original_generation']
        documents=json.loads(safe_file(generation,'documents.json').read_text(encoding='utf-8'))
        records=[]
        (output/'pdf').mkdir(exist_ok=True);(output/'records').mkdir(exist_ok=True)
        for document in documents:
            if not re.fullmatch(r'\d+',document['document_id']):raise ValueError('Unsafe document identity')
            pages=json.loads(safe_file(generation,document['pages_file']).read_text(encoding='utf-8'))['pages']
            record=classify_document(document,pages)
            if classify_document(document,pages)!=record:raise ValueError('Semantic replay is not deterministic')
            verify_evidence(record,pages)
            records.append(record)
            write_json(output/'records'/(record['document_id']+'.json'),record)
            shutil.copyfile(safe_file(generation,document['pdf_file']),output/'pdf'/(record['document_id']+'.pdf'))
            if hashlib.sha256((output/'pdf'/(record['document_id']+'.pdf')).read_bytes()).hexdigest()!=record['pdf_sha256']:
                raise ValueError('Published original PDF copy differs')
        records.sort(key=lambda r:(r['publication_date'],r['document_id']))
        write_json(output/'classifications.json',records)
        checked=check_review_fixture(records,fixture)
        status.update(checked,semantic_gate_passed=True,documents=len(records),pdf_pages=sum(r['page_count'] for r in records),
                      window_start=audit['window_start'],window_end=audit['window_end'],
                      index_run_id=args.expected_index_run,body_run_id=args.expected_body_run,index_sha256=audit['index_sha256'],
                      original_index_replayed=True,original_pdf_replayed=True,exact_page_text_replayed=True,
                      semantic_replay_identical=True,unique_evidence_spans=unique_evidence_count(records),
                      categories=dict(sorted(Counter(r['category'] for r in records).items())),
                      events=dict(sorted(Counter(r['event'] for r in records).items())),
                      unresolved_classifications=[r['document_id'] for r in records if not r['document_classified']],
                      capacity_conflict_documents=sorted(r['document_id'] for r in records if r['capacity_conflicts']),
                      missing_explicit_names=sum(r['project_name'] is None for r in records if r['category']!='OUT_OF_SCOPE'),
                      missing_extracted_proponents=sum(r['proponent'] is None for r in records if r['category']!='OUT_OF_SCOPE'),
                      review_fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                      classifications_sha256=hashlib.sha256((output/'classifications.json').read_bytes()).hexdigest(),
                      validated_scope='Only the 48 frozen document classifications and specified adversarial contracts; not all project fields or future live source coverage')
        render_report(output,records,status)
        print('DOGC_SEMANTIC_GATE',json.dumps(status,ensure_ascii=False),flush=True)
    except Exception as exc:
        status.update(semantic_gate_passed=False,error_type=type(exc).__name__,error=str(exc))
        print('DOGC_SEMANTIC_FAILURE',json.dumps(status,ensure_ascii=False),flush=True)
        raise
    finally:
        write_json(output/'audit.json',status)


if __name__=='__main__':main()
