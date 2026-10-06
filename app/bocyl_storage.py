"""Scoped BOCYL battery projection and a separately reviewed legacy repair.
An existing photovoltaic plant and a network point are not the new battery or
its applicant. Original event identity, dates, text and lifecycle never change.
"""
from __future__ import annotations
import argparse,hashlib,json,re,sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

NAME=re.compile(r'bater[ií]as\s+de\s+almacenamiento\s+con\s+denominaci[oó]n\s+[«“"]([^»”"\n]+)[»”"]',re.I)
APPLICANT=re.compile(r'^\s*Peticionario\s*:?\s+(.+?)(?=,\s+con\s+domicilio|$)',re.I|re.M)
INSTALLED=re.compile(r'^\s*Potencia instalada[^\n]*?\s(\d[\d.,]*)\s*(kW|MW)\s*$',re.I|re.M)
LEGACY_ID='BOCYL-D-05102026-193-39'
LEGACY_HASH='58ce9daccc2c40010b58f17502d50aff7efcd56e878dd8401b69e14a7337ef0b'
LEGACY_KEY='3cd885d540216fbe3d2f'
OLD={'project_name':'SII La Cistérniga II','technology':'HYBRID','power_mw':2.1,
     'promoter':'distribuidora «CS Marcos Sandonis- CT Polígono La Mora-1'}

def installed_number(value:str,unit:str)->float|None:
    if ',' in value:
        if not re.fullmatch(r'\d+(?:\.\d{3})*,\d+',value):return None
        number=Decimal(value.replace('.','').replace(',','.'))
    elif '.' in value:
        if re.fullmatch(r'\d{1,3}(?:\.\d{3})+',value):number=Decimal(value.replace('.',''))
        elif re.fullmatch(r'\d+\.\d{1,2}',value):number=Decimal(value)
        else:return None
    elif re.fullmatch(r'\d+',value):number=Decimal(value)
    else:return None
    return float(number/1000 if unit.casefold()=='kw' else number)

def battery_projection(title:str,raw_text:str)->dict|None:
    names=NAME.findall(title or '')
    if len(names)!=1:return None
    applicants=[m.group(1).strip() for m in APPLICANT.finditer(raw_text or '')]
    powers=[installed_number(m[1],m[2]) for m in INSTALLED.finditer(raw_text or '')]
    # Do not replace absent/ambiguous scope with generic MW, MWh or MVA.
    return {'project_name':names[0].strip(),'technology':'BESS',
            'promoter':applicants[0] if len(applicants)==1 else None,
            'power_mw':powers[0] if len(powers)==1 else None}

def project_event(event):
    if event.source_code!='BOCYL':return event
    result=battery_projection(event.title,event.raw_text)
    return replace(event,**result) if result else event

def source_fingerprint(conn)->str:
    rows=[tuple(r) for r in conn.execute('SELECT source_code,external_id,publication_date,title,url,raw_text,project_key,event_type,commercial_stage FROM events ORDER BY source_code,external_id')]
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def repair_database(conn,out_dir:Path)->dict:
    """Change only one reviewed old projection, with original-hash safeguards."""
    conn.row_factory=sqlite3.Row
    row=conn.execute("SELECT * FROM events WHERE source_code='BOCYL' AND external_id=?",(LEGACY_ID,)).fetchone()
    result={'source_code':'BOCYL','external_id':LEGACY_ID,'changed_projects':0,'new_source_downloads':0}
    if row is None:return result
    event=dict(row)
    if hashlib.sha256(event['raw_text'].encode()).hexdigest()!=LEGACY_HASH or event['project_key']!=LEGACY_KEY:
        raise ValueError('Unreviewed BOCYL original or identity; automatic repair rejected')
    current=battery_projection(event['title'],event['raw_text'])
    if not current or current['promoter']!='Soluciones de Ingeniería Industrial II, S.L.' or current['power_mw']!=2.1:
        raise ValueError('Reviewed BOCYL projection no longer matches its evidence')
    project=dict(conn.execute('SELECT * FROM projects WHERE project_key=?',(LEGACY_KEY,)).fetchone())
    expected_event={k:v for k,v in current.items() if k!='project_name'}
    if all(project[k]==v for k,v in current.items()) and all(event[k]==v for k,v in expected_event.items()):return result
    if conn.execute('SELECT COUNT(*) FROM events WHERE project_key=?',(LEGACY_KEY,)).fetchone()[0]!=1:
        raise ValueError('Shared BOCYL project requires an explicit multi-event review')
    if any(project[k]!=v for k,v in OLD.items()) or any(event[k]!=v for k,v in OLD.items() if k!='project_name'):
        raise ValueError('Unexpected pre-repair BOCYL projection; no field overwritten')
    if event['event_type']!='PUBLIC_INFO' or event['commercial_stage']!='EARLY' or project['commercial_stage']!='EARLY':
        raise ValueError('Unreviewed BOCYL lifecycle; automatic repair rejected')
    out_dir.mkdir(parents=True,exist_ok=True);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=out_dir/('bocyl-cisterniga-before-'+stamp+'.sqlite');conn.commit()
    with closing(sqlite3.connect(backup)) as c:conn.backup(c)
    original=source_fingerprint(conn)
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('UPDATE projects SET project_name=?,technology=?,promoter=?,power_mw=? WHERE project_key=?',
                     (current['project_name'],current['technology'],current['promoter'],current['power_mw'],LEGACY_KEY))
        conn.execute('UPDATE events SET technology=?,promoter=?,power_mw=? WHERE source_code=? AND external_id=?',
                     (current['technology'],current['promoter'],current['power_mw'],'BOCYL',LEGACY_ID))
        if source_fingerprint(conn)!=original:raise ValueError('BOCYL repair changed immutable source evidence or lifecycle')
        conn.commit()
    except Exception:conn.rollback();raise
    result.update(changed_projects=1,backup_path=str(backup),original_raw_text_sha256=LEGACY_HASH,
                  immutable_source_fingerprint=original,before=OLD,after=current,identity_dates_text_lifecycle_preserved=True)
    (out_dir/('repair-'+stamp+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--output',default='reports/bocyl_storage')
    a=p.parse_args()
    with closing(sqlite3.connect(a.db)) as c:result=repair_database(c,Path(a.output))
    print('BOCYL_STORAGE_REPAIR',json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
