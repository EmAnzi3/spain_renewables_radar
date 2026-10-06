"""Observe the official Alicante edict service linked in its public page.
No dated collector or event is enabled by this bounded source-contract probe.
"""
import hashlib,json,re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

URL='https://sede.diputacionalicante.es/consultas-edictos/'
ENERGY=re.compile(r'fotovolta|e[oó]lic|\bBESS\b|bater[ií]|almacenamiento|energ[ií]a',re.I)

def main():
 root=Path('reports/alicante_edicts_probe');root.mkdir(parents=True,exist_ok=True)
 end=datetime.now(ZoneInfo('Europe/Madrid')).date()-timedelta(days=1);start=end-timedelta(days=29)
 session=requests.Session();session.headers['User-Agent']='SpainRenewablesRadar/0.8 official publication probe'
 receipts=[];result={'collector_enabled':False,'events_created':0,'coverage_certified':False,'window_start':str(start),'window_end':str(end)}
 def get(label,url,params=None):
  if urlsplit(url).scheme!='https' or urlsplit(url).hostname!='sede.diputacionalicante.es':raise ValueError('Unverified host')
  with session.get(url,params=params,timeout=(15,60),allow_redirects=False,stream=True) as r:
   r.raise_for_status()
   if r.status_code!=200:raise ValueError('Unexpected redirect or status')
   raw=bytearray()
   for part in r.iter_content(65536):
    raw.extend(part)
    if len(raw)>20000000:raise ValueError('Oversized response')
   raw=bytes(raw);sha=hashlib.sha256(raw).hexdigest();(root/(sha+'.bin')).write_bytes(raw)
   receipts.append({'label':label,'url':r.url,'status':200,'bytes':len(raw),'sha256':sha,'retrieved_at':datetime.now(timezone.utc).isoformat()})
   return raw
 try:
  page=get('source-contract',URL);soup=BeautifulSoup(page,'html.parser')
  scripts='\n'.join(x.get_text() for x in soup.find_all('script'))
  endpoints=set(re.findall(r"var\s+urlServicio\s*=\s*'([^']+)'",scripts))
  if len(endpoints)!=1 or not re.search(r'nemo\s*=\s*"BOP_EDI"',scripts):raise ValueError('Unrecognized official query contract')
  endpoint=endpoints.pop()
  xml='<raiz><entrada><registro><desde>'+start.strftime('%d/%m/%Y')+'</desde><hasta>'+end.strftime('%d/%m/%Y')+'</hasta><texto></texto><tipoorganismo></tipoorganismo><publicante></publicante></registro></entrada></raiz>'
  raw=get('window-unfiltered',endpoint,{'nemo':'BOP_EDI','param':xml,'usuario':'-'})
  data=json.loads(raw);rows=data.get('bop',{}).get('registro')
  if not isinstance(rows,list):raise ValueError('Source did not provide edict records: '+str(list(data)))
  required={'fechaPublica','nBop','edicto','extracto','ubicacion','denominacion'}
  if any(not isinstance(x,dict) or not required<=set(x) for x in rows):raise ValueError('Incomplete edict schema')
  candidates=[x for x in rows if ENERGY.search(str(x.get('extracto','')))];(root/'candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2))
  result.update(response_acquired=True,returned_edicts=len(rows),candidate_edicts=len(candidates),observed_fields=sorted(set().union(*(set(x) for x in rows))),independent_calendar_reconciliation=False)
  print('ALICANTE_CANDIDATES',json.dumps(candidates,ensure_ascii=False),flush=True)
 except Exception as exc:result.update(error_type=type(exc).__name__,error=str(exc));raise
 finally:
  session.close();(root/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2));(root/'probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
  print('ALICANTE_PROBE',json.dumps(result),flush=True)
if __name__=='__main__':main()
