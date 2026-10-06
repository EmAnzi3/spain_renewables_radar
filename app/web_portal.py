"""Render a self-contained browsable portal from actual database evidence.

No external scripts, runtime APIs, credentials or synthetic project records.
"""
from __future__ import annotations
import argparse,hashlib,json,sqlite3,tempfile
from collections import defaultdict
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from app.reporting import build_commercial_rows,geography_accounting,write_quality_issues
ROOT=Path(__file__).resolve().parents[1]

def load_bopv(folder:Path|None)->list[dict]:
    if folder is None:return []
    from app.bopv_semantics import classify_document,paragraphs_from_html
    from scripts.validate_bopv_semantics import check_review
    documents=json.loads((folder/'classified_documents.json').read_text(encoding='utf-8'))
    review=json.loads((ROOT/'tests/fixtures/bopv_semantic_review.json').read_text(encoding='utf-8'))
    if {d['external_id'] for d in documents}!=set(review) or len(documents)!=len(review):
        raise ValueError('BOPV preview does not match its reviewed document set')
    for d in documents:
        raw_file=(folder/d['original_html_file']).resolve()
        if not raw_file.is_relative_to(folder.resolve()):raise ValueError('Invalid original path')
        raw=raw_file.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=d['raw_html_sha256']:raise ValueError('BOPV original digest differs')
        record={k:d[k] for k in ('external_id','source_url','publication_date')}
        record['title']=d['source_paragraphs'][0]['text']
        rebuilt=classify_document(record,paragraphs_from_html(raw,d['encoding']))
        check_review(rebuilt,raw,review[d['external_id']])
        for key,value in rebuilt.items():
            if d.get(key)!=value:raise ValueError('BOPV classification differs from its original: '+key)
    return documents

def payload(database:Path,status:dict,*,bopv:Path|None=None,alternatives:Path|None=None)->dict:
    with closing(sqlite3.connect(f'file:{database.resolve()}?mode=ro',uri=True)) as conn:
        conn.row_factory=sqlite3.Row;rows=build_commercial_rows(conn);events=defaultdict(list)
        for source in conn.execute('SELECT * FROM events ORDER BY publication_date DESC,id DESC'):
            e=dict(source);basis='SOURCE_PUBLICATION'
            if e['source_code']=='MITECO_SABIA':basis='ENTRY_DATE' if ':ENTRY' in e['external_id'] else 'CONSULTATION_START'
            events[e['project_key']].append({'source_code':e['source_code'],'external_id':e['external_id'],
                'date':e['publication_date'],'date_basis':basis,'event_type':e['event_type'],
                'title':e['title'],'url':e['url'],'raw_text':e['raw_text']})
        with tempfile.TemporaryDirectory() as temp:issues,_,_=write_quality_issues(conn,temp)
        if any(x['severity']=='ERROR' for x in issues):raise ValueError('Cannot publish structural quality errors')
        flags=defaultdict(list)
        for issue in issues:flags[issue['project_key']].append({k:issue[k] for k in ('severity','code','detail')})
        for row in rows:
            row['events']=events[row['project_key']]
            row['source_codes']=sorted({e['source_code'] for e in row['events']});row['issues']=flags[row['project_key']]
            if not row['events']:raise ValueError('Project without original event')
        sources=json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
        data={'records':rows,'status':status,'sources':sources,'bopv':load_bopv(bopv),
              'alternatives':json.loads(alternatives.read_text()) if alternatives and alternatives.exists() else [],
              'geography_accounting':geography_accounting(rows),'generated_at':datetime.now(timezone.utc).isoformat(),
              'provenance_note':status.get('provenance_note','La data di generazione della pagina non è la data degli atti né una certificazione live.')}
    return data

def write_portal(database:Path,output:Path,status:dict,**kwargs)->dict:
    data=payload(database,status,**kwargs)
    encoded=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    safe=encoded.replace('&','\u0026').replace('<','\u003c').replace('>','\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    # Use literal JSON Unicode escapes, not HTML entities inside the script.
    safe=encoded.replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    template=(ROOT/'web/portal.html').read_text(encoding='utf-8')
    if template.count('__RADAR_PAYLOAD__')!=1:raise ValueError('Invalid portal template')
    output.mkdir(parents=True,exist_ok=True)
    (output/'index.html').write_text(template.replace('__RADAR_PAYLOAD__',safe),encoding='utf-8')
    (output/'data.json').write_text(encoded,encoding='utf-8');(output/'.nojekyll').write_text('')
    receipt={'projects':len(data['records']),'events':sum(len(r['events']) for r in data['records']),
             'bopv_assets_outside_radar':sum(len(d['assets']) for d in data['bopv']),
             'alternative_channels':len(data['alternatives']),'state':status['state'],
             'full_certification':False,'generated_at':data['generated_at'],
             'index_sha256':hashlib.sha256((output/'index.html').read_bytes()).hexdigest()}
    (output/'build_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True)
    p.add_argument('--status',required=True);p.add_argument('--output',default='site');p.add_argument('--bopv');p.add_argument('--alternatives')
    args=p.parse_args();receipt=write_portal(Path(args.db),Path(args.output),json.loads(Path(args.status).read_text()),
        bopv=Path(args.bopv) if args.bopv else None,alternatives=Path(args.alternatives) if args.alternatives else None)
    print('PORTAL_BUILT',json.dumps(receipt))
if __name__=='__main__':main()
