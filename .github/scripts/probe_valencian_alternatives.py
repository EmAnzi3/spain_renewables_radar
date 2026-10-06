"""Probe independent official Valencian publication channels, never create events.

Every response and link is evidence of access only. No catalogue, date-window or
project coverage is inferred from a successful homepage response.
"""
from __future__ import annotations
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import requests
from bs4 import BeautifulSoup

SOURCES = [
 ('BOP_VALENCIA','https://bop.dival.es/bop/'),
 ('BOP_ALICANTE','https://sede.diputacionalicante.es/consultas-edictos/'),
 ('BOP_CASTELLON','https://bop.dipcas.es/PortalBOP/'),
 ('MPT_VALENCIA','https://mptmd.gob.es/portal/delegaciones_gobierno/delegaciones/comunidad_valenciana/proyectos-ci/procedimientos-de-informacion-publica'),
 ('ICV_PV','https://terramapas.icv.gva.es/2601_Fotovoltaicas?service=WFS&request=GetCapabilities'),
]
HOSTS={urlsplit(u).hostname for _,u in SOURCES}|{'mpt.gob.es','www.mpt.gob.es','www.mptmd.gob.es','bop.diputacionalicante.es'}
ENERGY=re.compile(r'fotovolta|e[oòó]lic|bater[ií]|\bBESS\b|almacenamiento|energ[ií]a|energ[eé]tic',re.I)

def allowed(url):
 p=urlsplit(url)
 return p.scheme=='https' and p.hostname in HOSTS and p.port in (None,443) and not p.username and not p.password

def acquire(code,url,root):
 receipts=[]
 for attempt in (1,2):
  s=requests.Session();s.headers['User-Agent']='SpainRenewablesRadar/0.8 (public source availability probe)'
  try:
   current=url
   for hop in range(4):
    if not allowed(current):raise ValueError('Unverified redirect destination')
    item={'source_code':code,'url':current,'attempt':attempt,'started_at':datetime.now(timezone.utc).isoformat()}
    receipts.append(item)
    with s.get(current,timeout=(12,30),allow_redirects=False,stream=True) as r:
     item['status']=r.status_code
     if 300<=r.status_code<400:
      item['location']=r.headers.get('Location');current=urljoin(current,item['location'] or '')
      if not item['location']:raise ValueError('Redirect without destination')
      continue
     r.raise_for_status()
     if r.status_code!=200:raise ValueError('Unexpected response status')
     chunks=[];size=0
     for part in r.iter_content(65536):
      size+=len(part)
      if size>8000000:raise ValueError('Source response exceeds bounded size')
      chunks.append(part)
     raw=b''.join(chunks);digest=hashlib.sha256(raw).hexdigest()
     (root/'raw'/f'{digest}.bin').write_bytes(raw)
     item.update(sha256=digest,bytes=len(raw),content_type=r.headers.get('Content-Type'),encoding=r.encoding or 'utf-8',retrieved_at=datetime.now(timezone.utc).isoformat())
     soup=BeautifulSoup(raw,'html.parser')
     title=soup.title.get_text(' ',strip=True) if soup.title else None
     text=' '.join(soup.stripped_strings)
     if code=='ICV_PV':
      if b'WFS_Capabilities' not in raw:raise ValueError('Not WFS capabilities')
     elif not title or len(text)<150:raise ValueError('Missing readable official page')
     forms=[{'action':urljoin(current,f.get('action') or ''),'method':f.get('method','GET'),'controls':[{'tag':x.name,'name':x.get('name'),'type':x.get('type'),'value':x.get('value')} for x in f.select('input,select,button')][:60]} for f in soup.find_all('form')][:12]
     leads=[];seen=set()
     for a in soup.select('a[href]'):
      label=a.get_text(' ',strip=True);target=urljoin(current,a['href'])
      if not ENERGY.search(label) or urlsplit(target).scheme not in ('http','https') or target in seen:continue
      seen.add(target)
      parent=a.find_parent(['tr','li','p'])
      context=parent.get_text(' ',strip=True) if parent else label
      leads.append({'title':label,'source_url':current,'document_url':target,'context':context[:2500], 'status':'UNREVIEWED_SOURCE_LINK','publication_date':None,'project_name':None,'power_mw':None})
     links=[{'label':a.get_text(' ',strip=True)[:160],'url':urljoin(current,a['href'])} for a in soup.select('a[href]') if any(k in (a.get('href','')+' '+a.get_text(' ',strip=True)).lower() for k in ('sumario','buscar','busca','bolet','consulta','rss','atom','wfs','geopackage'))][:80]
     return {'source_code':code,'requested_url':url,'final_url':current,'access':'RESPONSE_ACQUIRED','title':title,'receipts':receipts,'forms':forms,'navigation_links':links,'lead_links':leads,'text_preview':text[:16000],'collector_implemented':False,'coverage_certified':False,'database_events_created':0}
   raise ValueError('Redirect limit exceeded')
  except Exception as e:
   if receipts:receipts[-1].update(error_type=type(e).__name__,error=str(e)[:900])
   transient=isinstance(e,(requests.ConnectionError,requests.Timeout)) and not isinstance(e,requests.exceptions.SSLError)
   if not transient or attempt==2:return {'source_code':code,'requested_url':url,'access':'FAILED','receipts':receipts,'error_type':type(e).__name__,'error':str(e)[:900],'collector_implemented':False,'coverage_certified':False,'database_events_created':0}
   time.sleep(2)
  finally:s.close()

def main():
 root=Path('reports/valencian_alternatives');(root/'raw').mkdir(parents=True,exist_ok=True)
 results=[]
 for code,url in SOURCES:
  result=acquire(code,url,root);results.append(result)
  (root/'probe.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
  print('OFFICIAL_ALTERNATIVE',json.dumps({k:v for k,v in result.items() if k not in ('receipts','text_preview','navigation_links','lead_links','forms')},ensure_ascii=False),flush=True)
  print('SOURCE_CONTRACT',json.dumps({'source_code':code,'forms':result.get('forms'),'navigation_links':result.get('navigation_links'),'lead_links':result.get('lead_links')},ensure_ascii=False),flush=True)
 rows=''.join('<tr><td>'+html.escape(x['source_code'])+'</td><td>'+html.escape(x['access'])+'</td><td><a href="'+html.escape(x['requested_url'],quote=True)+'">Fonte ufficiale</a></td><td>'+str(len(x.get('lead_links',[])))+'</td></tr>' for x in results)
 (root/'index.html').write_text('<!doctype html><html lang="it"><meta charset="utf-8"><title>Fonti alternative Valencia</title><h1>Accessi ufficiali alternativi</h1><p>Verifica di accesso, non collector attivati o copertura integrale. I link sono avvisi da revisionare, non progetti validati.</p><table><tr><th>Canale</th><th>Esito</th><th>Link</th><th>Link candidati</th></tr>'+rows+'</table></html>',encoding='utf-8')
 print('PROBE_COMPLETE',json.dumps({'sources':len(results),'responses':sum(x['access']=='RESPONSE_ACQUIRED' for x in results),'collectors_enabled':0,'events_created':0}))
 if not any(x['access']=='RESPONSE_ACQUIRED' for x in results):raise SystemExit('No official alternative responded')

if __name__=='__main__':main()
