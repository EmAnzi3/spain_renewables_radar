"""Acquire missing official bodies; never modify source events or guess company roles."""
from __future__ import annotations
import hashlib,io,json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,urljoin
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'reports/field_supplements';OUT.mkdir(parents=True,exist_ok=True)
MANIFEST=[]
LIMIT=15000000

def get(url,hosts):
    original=url
    for attempt in range(2):
        receipt={'url':original,'attempt':attempt+1,'retrieved_at':datetime.now(timezone.utc).isoformat(),'complete':False,'redirects':[]}
        response=None
        try:
            url=original
            for redirect in range(4):
                p=urlsplit(url)
                if p.scheme!='https' or p.hostname not in hosts or p.username or p.password or p.port not in (None,443):raise ValueError('Unapproved source URL')
                response=requests.get(url,timeout=(15,45),stream=True,allow_redirects=False,headers={'User-Agent':'SpainRenewablesRadar/1.0 (official document field review)'})
                receipt['status']=response.status_code
                if response.status_code in (301,302,303,307,308):
                    location=response.headers.get('Location')
                    receipt['redirects'].append({'from':url,'location':location,'status':response.status_code})
                    response.close()
                    if not location or redirect==3:raise ValueError('Missing destination or excessive redirects')
                    url=urljoin(url,location)
                    continue
                response.raise_for_status()
                if response.status_code!=200:raise ValueError('Unexpected source response')
                chunks=[];size=0
                for part in response.iter_content(65536):
                    size+=len(part)
                    if size>LIMIT:raise ValueError('Source size limit exceeded')
                    chunks.append(part)
                raw=b''.join(chunks)
                receipt.update(complete=True,final_url=url,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),content_type=response.headers.get('Content-Type'))
                return raw,receipt
        except Exception as exc:
            receipt.update(error_type=type(exc).__name__,error=str(exc))
            transient=isinstance(exc,(requests.ConnectionError,requests.Timeout)) and not isinstance(exc,requests.exceptions.SSLError)
            if not transient or attempt==1:raise
            time.sleep(2)
        finally:
            if response is not None:response.close()
            MANIFEST.append(receipt.copy());(OUT/'requests.json').write_text(json.dumps(MANIFEST,indent=2))
    raise RuntimeError('Unreachable transport state')

def main():
    records=[];errors=[]
    from scripts.portal_inputs import download
    inputs=Path('field-supplement-input')
    download(11402510121,39205152,'bec88d91aebf8ba6c12c63e0d03a543692d64fefb2f44749ba57e681ffabaf2a','verified',inputs)
    candidates=list((inputs/'verified').rglob('borm/index_raw.json'))
    if len(candidates)!=1:raise ValueError('Missing or ambiguous original BORM index')
    rows_all=json.loads(candidates[0].read_text())
    portal=json.loads((inputs/'verified/site/data.json').read_text())
    expected={e['external_id'] for p in portal['records'] for e in p['events'] if e['source_code']=='BORM'}
    rows=[r for r in rows_all if r[16] in expected]
    if len(rows)!=len(expected) or {r[16] for r in rows}!=expected:raise ValueError('Original index does not account for every stored BORM notice')
    for row in rows:
        npe,url,day=row[16],row[18],row[4][:10]
        try:
            if not re.fullmatch(r'https://www\.borm\.es/services/anuncio/\d+/pdf',url):raise ValueError('Unexpected official indexed PDF path')
            raw,receipt=get(url,{'www.borm.es'})
            if not raw.startswith(b'%PDF-') or b'%%EOF' not in raw[-4096:]:raise ValueError('Incomplete PDF response')
            pdf=PdfReader(io.BytesIO(raw),strict=True)
            if pdf.is_encrypted or len(pdf.pages)!=int(row[19]):raise ValueError('PDF page count differs from official index')
            pages=[{'page':i+1,'text':p.extract_text() or ''} for i,p in enumerate(pdf.pages)]
            if any(not p['text'].strip() for p in pages):raise ValueError('PDF contains a page without extracted text')
            if any(npe not in p['text'] for p in pages):raise ValueError('PDF does not carry the indexed NPE on each page')
            sha=receipt['sha256'];(OUT/(sha+'.pdf')).write_bytes(raw)
            item={'source_code':'BORM','external_id':npe,'publication_date':day,'url':url,'index_row':row,'index_row_sha256':hashlib.sha256(json.dumps(row,ensure_ascii=False).encode()).hexdigest(),'receipt':receipt,'original_file':sha+'.pdf','title':row[5],'pages':pages,'raw_text':'\n\n'.join(p['text'] for p in pages),'new_event_created':False}
            records.append(item);print('BODY_OK',npe,len(pages),sha,flush=True)
        except Exception as exc:
            errors.append({'external_id':npe,'url':url,'error_type':type(exc).__name__,'error':str(exc)});print('BODY_FAILED',npe,str(exc),flush=True)
        time.sleep(.75)
    url='https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?BASE=BOLE&CMD=VERDOC&DOCN=007953164&SEC=BUSQUEDA_AVANZADA'
    try:
        raw,receipt=get(url,{'www.boa.aragon.es'})
        soup=BeautifulSoup(raw,'html.parser');text=soup.get_text(' ',strip=True)
        for exact in ('PEJ/1432/2025','G-Z-2022-203','DUP-Z-2022-0062','Albortón'):
            if exact not in text:raise ValueError('Historical document does not match the exact related dossier: '+exact)
        sha=receipt['sha256'];(OUT/(sha+'.html')).write_bytes(raw)
        records.append({'source_code':'BOA','external_id':'007953164','related_external_id':'007961025','required_related_references':['G-Z-2022-203','DUP-Z-2022-0062'],'url':url,'publication_date':'2025-10-31','receipt':receipt,'original_file':sha+'.html','title':soup.title.get_text(' ',strip=True) if soup.title else '', 'raw_text':text,'historical_date_requires_header_review':True,'new_event_created':False})
        print('HISTORICAL_BODY_OK',sha,flush=True)
    except Exception as exc:errors.append({'external_id':'007953164','url':url,'error_type':type(exc).__name__,'error':str(exc)})
    (OUT/'documents.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    result={'documents_acquired':len(records),'expected_documents':len(expected)+1,'errors':errors,'new_events_created':0,'project_fields_changed':0,'semantic_review_complete':False,'acquisition_complete':not errors}
    (OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('SUPPLEMENT_ACQUISITION',json.dumps(result,ensure_ascii=False),flush=True)
    if errors:raise SystemExit('Some original bodies could not be acquired; no full completeness claim')
if __name__=='__main__':main()
