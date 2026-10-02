from __future__ import annotations
from app.lifecycle import STAGE_RANK
from app.parser import ParsedEvent

def save_event(conn,event:ParsedEvent)->tuple[bool,bool]:
    existing=conn.execute("SELECT 1 FROM events WHERE source_code=? AND external_id=?",(event.source_code,event.external_id)).fetchone()
    if existing:return False,False
    project=conn.execute("SELECT * FROM projects WHERE project_key=?",(event.project_key,)).fetchone()
    new_project=project is None
    if new_project:
        conn.execute("""INSERT INTO projects
        (project_key,project_name,technology,power_mw,province,ccaa,commercial_stage,first_seen,last_seen,latest_event_type,latest_source_code,latest_source_url)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (event.project_key,event.project_name,event.technology,event.power_mw,event.province,event.ccaa,event.commercial_stage,event.publication_date,event.publication_date,event.event_type,event.source_code,event.url))
    else:
        old_stage=project["commercial_stage"]
        if event.commercial_stage=="BLOCKED":
            chosen="BLOCKED"
        elif old_stage=="BLOCKED":
            chosen=old_stage
        else:
            chosen=max((old_stage,event.commercial_stage),key=lambda s:STAGE_RANK.get(s,0))
        conn.execute("""UPDATE projects SET
        project_name=COALESCE(?,project_name),technology=COALESCE(?,technology),
        power_mw=COALESCE(?,power_mw),province=COALESCE(?,province),ccaa=COALESCE(?,ccaa),
        commercial_stage=?,last_seen=?,latest_event_type=?,latest_source_code=?,latest_source_url=?
        WHERE project_key=?""",
        (event.project_name,event.technology,event.power_mw,event.province,event.ccaa,chosen,event.publication_date,event.event_type,event.source_code,event.url,event.project_key))
    conn.execute("""INSERT INTO events
    (source_code,external_id,publication_date,title,url,raw_text,project_key,event_type,commercial_stage,technology,power_mw,province,ccaa)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (event.source_code,event.external_id,event.publication_date,event.title,event.url,event.raw_text,event.project_key,event.event_type,event.commercial_stage,event.technology,event.power_mw,event.province,event.ccaa))
    conn.commit()
    return True,new_project
