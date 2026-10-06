"""Official source inventories, not substitutes for the complete GVA portal.

MPT sections may contain several plants. Missing web dates and scalar MW remain
unset; navigation menus are excluded and no project event is created.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
ENERGY=re.compile(r'fotovolta|e[oòó]lic|\bBESS\b|bater[ií]|almacenamiento|h[ií]brid',re.I)
PROVINCES={'ALICANTE','CASTELLÓN','CASTELLON','VALENCIA'}

def mpt_inventory(raw:bytes,url:str)->list[dict]:
    if urlsplit(url).hostname not in {'mptmd.gob.es','mpt.gob.es'}:raise ValueError('Unexpected MPT host')
    soup=BeautifulSoup(raw,'html.parser');sections=soup.select('section.dnt-vertical-menu-content')
    if len(sections)!=1:raise ValueError('MPT project content scope is ambiguous')
    scope=sections[0];h1=scope.find('h1')
    if not h1 or 'Procedimientos de información pública' not in h1.get_text(' ',strip=True):raise ValueError('Wrong MPT page')
    province=None;current=None;rows=[]
    for node in scope.select('h2.cmp-title__text, div.cmp-text'):
        if node.name=='h2':
            title=' '.join(node.get_text(' ',strip=True).split());current=None
            if title.upper() in PROVINCES:province=title;continue
            if province and ENERGY.search(title):
                identity=node.parent.get('id')
                if not identity or not re.fullmatch(r'title-[a-zA-Z0-9_-]+',identity):raise ValueError('Missing stable MPT section identity')
                current={'title':title,'section_id':identity,'province_section':province,'context':'',
                         'source_url':url,'document_url':url+'#'+identity,'document_links':[],
                         'status':'OFFICIAL_FILE_TO_REVIEW','publication_date':None,'project_name':None,
                         'power_mw':None,'event_type':None,'database_events_created':0}
                rows.append(current)
        elif current is not None:
            current['context']+='\n'+node.get_text('\n',strip=True)
            for a in node.select('a[href]'):
                target=urljoin(url,a['href'])
                if urlsplit(target).scheme not in ('http','https'):continue
                link={'label':a.get_text(' ',strip=True),'url':target}
                if link not in current['document_links']:current['document_links'].append(link)
    if not rows or len(rows)>1000 or len({r['section_id'] for r in rows})!=len(rows):raise ValueError('Empty, repeated or excessive MPT inventory')
    for row in rows:
        row['context']=row['context'].strip();row['context_sha256']=hashlib.sha256(row['context'].encode()).hexdigest()
        if row['document_links']:row['document_url']=row['document_links'][0]['url']
    return rows

def from_probe(root:Path)->list[dict]:
    original=json.loads((root/'probe.json').read_text(encoding='utf-8'));result=[]
    for item in original:
        out={k:item.get(k) for k in ('source_code','requested_url','final_url','access','title','error_type','error')}
        out.update(collector_implemented=False,coverage_certified=False,lead_links=[])
        completed=[r for r in item.get('receipts',[]) if 'sha256' in r]
        if item['access']=='RESPONSE_ACQUIRED':
            if not completed:raise ValueError('No original evidence for a successful probe')
            receipt=completed[-1];sha=receipt['sha256']
            if not re.fullmatch(r'[0-9a-f]{64}',sha):raise ValueError('Invalid source digest')
            raw=(root/'raw'/(sha+'.bin')).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=sha or len(raw)!=receipt['bytes'] or receipt['status']!=200:raise ValueError('Source probe original bytes differ')
            out.update(original_sha256=sha,original_retrieved_at=receipt['retrieved_at'])
            if item['source_code']=='MPT_VALENCIA':
                out['lead_links']=mpt_inventory(raw,item['final_url'])
                out['inventory_scope']='Renewable-labelled administrative sections under three provincial headings; not unique plants or dated events'
            elif item['source_code']=='ICV_PV':
                if b'<!DOCTYPE' in raw.upper():raise ValueError('Unexpected XML doctype')
                tree=ET.fromstring(raw)
                if not tree.tag.endswith('WFS_Capabilities'):raise ValueError('Wrong ICV XML response')
                ns={'wfs':'http://www.opengis.net/wfs/2.0'}
                out['feature_types']=[{'name':x.findtext('wfs:Name',namespaces=ns),'title':x.findtext('wfs:Title',namespaces=ns)} for x in tree.findall('.//wfs:FeatureType',ns)]
                out['title']='ICV — cartografia fotovoltaica: metadati WFS'
        result.append(out)
    return result

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--probe-root',required=True)
    p.add_argument('--output',default='reports/valencian_alternatives_inventory.json');args=p.parse_args()
    out=from_probe(Path(args.probe_root));path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ALTERNATIVE_INVENTORIES',json.dumps({'channels':len(out),'mpt_administrative_files':sum(len(x['lead_links']) for x in out),'new_collectors':0,'new_events':0}))
if __name__=='__main__':main()
