from __future__ import annotations
import json
from app.lifecycle import STAGE_RANK
from app.parser import ParsedEvent, normalize_text

PROJECT_FIELDS = ('project_name','technology','power_mw','promoter','expediente','province','ccaa')


def _ensure_aliases(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS project_identity_aliases (
        alias_key TEXT PRIMARY KEY, project_key TEXT NOT NULL,
        rule TEXT NOT NULL, source_code TEXT NOT NULL, external_id TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        FOREIGN KEY(project_key) REFERENCES projects(project_key))''')


def resolve_project_key(conn, event: ParsedEvent) -> str:
    """Same-day exact multi-field corroboration only; conflicting references never merge."""
    _ensure_aliases(conn)
    if conn.execute('SELECT 1 FROM projects WHERE project_key=?',(event.project_key,)).fetchone():
        return event.project_key
    alias=conn.execute('SELECT project_key FROM project_identity_aliases WHERE alias_key=?',(event.project_key,)).fetchone()
    if alias and conn.execute('SELECT 1 FROM projects WHERE project_key=?',(alias['project_key'],)).fetchone():
        return alias['project_key']
    if not event.project_name or not event.province or not event.technology:
        return event.project_key
    candidates=[]
    for project in conn.execute('SELECT * FROM projects WHERE province=? AND technology=?',(event.province,event.technology)):
        if normalize_text(project['project_name']) != normalize_text(event.project_name):continue
        if event.expediente and project['expediente'] and normalize_text(event.expediente)!=normalize_text(project['expediente']):continue
        if event.promoter and project['promoter'] and normalize_text(event.promoter)!=normalize_text(project['promoter']):continue
        if event.power_mw is not None and project['power_mw'] is not None and abs(event.power_mw-project['power_mw'])>0.001:continue
        other=conn.execute('''SELECT 1 FROM events WHERE project_key=? AND publication_date=? AND source_code<>? LIMIT 1''',
                           (project['project_key'],event.publication_date,event.source_code)).fetchone()
        if other:candidates.append(project['project_key'])
    if len(candidates)!=1:return event.project_key
    target=candidates[0]
    conn.execute('''INSERT INTO project_identity_aliases VALUES (?,?,?,?,?,?)''',
                 (event.project_key,target,'EXACT_NAME_TECH_PROVINCE_SAME_DAY_DIFFERENT_SOURCE',event.source_code,event.external_id,
                  json.dumps({'name':event.project_name,'technology':event.technology,'province':event.province,
                              'event_date':event.publication_date},ensure_ascii=False)))
    return target


def save_event(conn,event:ParsedEvent)->tuple[bool,bool]:
    existing=conn.execute('SELECT 1 FROM events WHERE source_code=? AND external_id=?',(event.source_code,event.external_id)).fetchone()
    if existing:return False,False
    event.project_key=resolve_project_key(conn,event)
    project=conn.execute('SELECT * FROM projects WHERE project_key=?',(event.project_key,)).fetchone()
    new_project=project is None
    if new_project:
        conn.execute('''INSERT INTO projects
        (project_key,project_name,technology,power_mw,promoter,expediente,province,ccaa,commercial_stage,first_seen,last_seen,latest_event_type,latest_source_code,latest_source_url)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (event.project_key,event.project_name,event.technology,event.power_mw,event.promoter,event.expediente,event.province,event.ccaa,
         event.commercial_stage,event.publication_date,event.publication_date,event.event_type,event.source_code,event.url))
    else:
        old_stage=project['commercial_stage']
        chosen='BLOCKED' if 'BLOCKED' in (old_stage,event.commercial_stage) else max((old_stage,event.commercial_stage),key=lambda s:STAGE_RANK.get(s,0))
        newer=event.publication_date>=project['last_seen']
        values=[]
        for field in PROJECT_FIELDS:
            value=getattr(event,field)
            values.append(value if value is not None and (newer or project[field] is None) else project[field])
        conn.execute('''UPDATE projects SET project_name=?,technology=?,power_mw=?,promoter=?,expediente=?,province=?,ccaa=?,
            commercial_stage=?,first_seen=?,last_seen=?,latest_event_type=?,latest_source_code=?,latest_source_url=? WHERE project_key=?''',
            (*values,chosen,min(project['first_seen'],event.publication_date),max(project['last_seen'],event.publication_date),
             event.event_type if newer else project['latest_event_type'],event.source_code if newer else project['latest_source_code'],
             event.url if newer else project['latest_source_url'],event.project_key))
    conn.execute('''INSERT INTO events
    (source_code,external_id,publication_date,title,url,raw_text,project_key,event_type,commercial_stage,technology,power_mw,promoter,expediente,province,ccaa)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
    (event.source_code,event.external_id,event.publication_date,event.title,event.url,event.raw_text,event.project_key,event.event_type,
     event.commercial_stage,event.technology,event.power_mw,event.promoter,event.expediente,event.province,event.ccaa))
    conn.commit()
    return True,new_project
