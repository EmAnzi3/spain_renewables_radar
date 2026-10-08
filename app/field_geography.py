"""INE-verified municipal mentions with separate plant and grid-route scope.

This does not geocode exact construction footprints or invent municipalities.
Conflicting site locations and projects already flagged multi-province are left
untouched; evidence and dates are retained.
"""
from __future__ import annotations

import hashlib
import json
import re
from app.enrichment.ine_municipalities import _aliases
from app.field_integrity import norm

LOCATION = re.compile(
    r'(?:(?:en|incluyendo|ubicad[oa]\s+en)\s+)?(?:los?\s+)?'
    r't[eé]rminos?\s+municipal(?:es)?\s+de\s+([^.;:\n]{3,200})', re.I)
PAREN = re.compile(r'\ben\s+([A-ZÁÉÍÓÚÑÜ][\wÀ-ÿ\s,\-]+?)\s*\(([A-ZÁÉÍÓÚÑÜ][\wÀ-ÿ\s]+)\)',re.I)
ASSET = re.compile(
    r'(?:instalaci[oó]n|planta|parque|m[oó]dulo|sistema)\s+'
    r'(?:solar\s+)?(?:fotovoltaic[ao]|e[oó]lic[ao]|de\s+almacenamiento|h[ií]brid[ao])',re.I)
LINE = re.compile(r'(?:l[ií]nea\s+(?:el[eé]ctrica|de\s+evacuaci[oó]n)|'
                  r'infraestructuras?\s+de\s+evacuaci[oó]n)',re.I)

def _municipal_lookup(catalog):
    index={}
    for municipality in catalog:
        for alias in _aliases(municipality.name):
            index.setdefault(alias,[]).append(municipality)
    return index

def municipalities_in_clause(clause,index,ccaa,province):
    tokens=norm(clause).split()
    result={}
    for i in range(len(tokens)):
        for size in range(1,min(7,len(tokens)-i+1)):
            for entry in index.get(' '.join(tokens[i:i+size]),[]):
                if ccaa and norm(entry.ccaa)!=norm(ccaa):continue
                if province and norm(entry.province)!=norm(province):continue
                if len(norm(entry.name))>2:result[entry.code]=entry
    return list(result.values())

def site_clauses(project,event,index):
    name=(project.get('project_name') or '').strip(' «»"“”')
    if len(name)<3:return []
    text=event.get('raw_text') or ''
    result=[]
    for mention in re.finditer(re.escape(name),text,re.I):
        before=text[max(0,mention.start()-125):mention.start()]
        if not ASSET.search(before):continue
        after=text[mention.end():mention.end()+235]
        chunks=[(x.group(1),x.end(1)) for x in LOCATION.finditer(after)]
        chunks += [(x.group(1),x.end(1)) for x in PAREN.finditer(after)]
        for chunk,end in chunks:
            # Parenthetical province labels are not plant municipalities.
            chunk=re.sub(r'\s*\([^)]{2,65}\)','',chunk)
            chunk=re.split(r'\b(?:en\s+la\s+provincia|con\s+una\s+potencia|y\s+sus\s+infraestructuras)\b',chunk,1,flags=re.I)[0]
            towns=municipalities_in_clause(chunk,index,project.get('ccaa'),project.get('province'))
            if not towns:continue
            prev=text[max(0,mention.start()-220):mention.start()]
            if event.get('event_type')=='EXPROPRIATION' and LINE.search(prev):
                continue  # route-specific expropriation != plant footprint
            result.append({'names':sorted({m.name for m in towns}),
                'codes':sorted({m.code for m in towns}),
                'provinces':sorted({m.province for m in towns}),
                'source_code':event['source_code'],'external_id':event['external_id'],
                'source_url':event['url'],'publication_date':event['publication_date'],
                'source_event_type':event['event_type'],
                'source_original_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'source_clause':text[mention.start():mention.end()+end]})
    return list({tuple(e['codes']):e for e in result}.values())

def audit_site(project,events,index):
    rows=[x for event in events for x in site_clauses(project,event,index)]
    # A granted plant-scope clause takes precedence over an evacuation notice.
    preferred=[x for x in rows if x['source_event_type'] in
               {'CONSTRUCTION_AUTH','PRIOR_AUTH','DIA'}]
    trusted=preferred or rows
    if not trusted:return {'status':'UNVERIFIED','municipalities':[],'evidence':[]}
    site_sets=[set(x['codes']) for x in trusted]
    largest=max(site_sets,key=len)
    if not all(s.issubset(largest) for s in site_sets):
        return {'status':'CONFLICT','municipalities':[],'evidence':trusted}
    best=next(x for x in trusted if set(x['codes'])==largest)
    return {'status':'DOCUMENTED_MUNICIPAL_CONTEXT','municipalities':best['names'],
            'provinces':best['provinces'],'evidence':[best]}

def enrich_municipal_context(conn,catalog):
    """Only add evidence when no other validated geography exists.
    It is explicitly municipal context, not a polygon/site address.
    """
    index=_municipal_lookup(catalog)
    results={'documented':0,'conflicts':0,'unverified':0,'existing_preserved':0}
    for row in conn.execute('SELECT * FROM projects'):
        project=dict(row)
        prior=conn.execute('SELECT status FROM project_geo_enrichment WHERE project_key=?',
                           (project['project_key'],)).fetchone()
        if prior:
            results['existing_preserved']+=1
            continue
        events=[dict(e) for e in conn.execute('SELECT * FROM events WHERE project_key=?',
                                             (project['project_key'],))]
        review=audit_site(project,events,index)
        if review['status']=='UNVERIFIED':
            results['unverified']+=1
            continue
        if review['status']=='CONFLICT':
            results['conflicts']+=1
            continue
        evidence=review['evidence'][0]
        provinces=evidence['provinces']
        if (len(provinces)!=1 or not project.get('province')
            or norm(provinces[0])!=norm(project['province'])):
            results['conflicts']+=1
            continue
        conn.execute('''INSERT INTO project_geo_enrichment
            (project_key,municipalities_json,provinces_json,province,ccaa,status,
             source_code,source_url,reference_date)
            VALUES (?,?,?,?,?,?,?,?,?)''',(
            project['project_key'],json.dumps(review['municipalities'],ensure_ascii=False),
            json.dumps(provinces,ensure_ascii=False),project['province'],project['ccaa'],
            'DOCUMENTED_MUNICIPAL_CONTEXT',evidence['source_code'],
            evidence['source_url'],evidence['publication_date']))
        results['documented']+=1
    conn.commit()
    return results
