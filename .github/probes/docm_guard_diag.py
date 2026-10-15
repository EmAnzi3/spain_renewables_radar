import json, sqlite3, sys
from app.docm_storage import storage_evidence, project_storage, digest, REVIEWED_ID
from app.parser import parse_event
conn = sqlite3.connect(sys.argv[1]); conn.row_factory = sqlite3.Row
out = []
for source in conn.execute("SELECT * FROM events WHERE source_code='DOCM'"):
    row = dict(source)
    ev = storage_evidence(row['title'], row['raw_text'] or '')
    if ev is None: continue
    orig = parse_event(**{k: row[k] for k in ('source_code','external_id','publication_date','title','url','raw_text')})
    proj = project_storage(orig)
    project = dict(conn.execute('SELECT * FROM projects WHERE project_key=?', (row['project_key'],)).fetchone())
    one = conn.execute('SELECT COUNT(*) FROM events WHERE project_key=?', (row['project_key'],)).fetchone()[0] == 1
    exp = {'project_name': proj.project_name, 'technology': proj.technology, 'power_mw': proj.power_mw}
    out.append({'external_id': row['external_id'], 'date': row['publication_date'], 'title': row['title'][:220],
                'key_matches': proj.project_key == row['project_key'], 'single_event_project': one,
                'event': {k: row[k] for k in ('technology', 'power_mw')},
                'project': {k: project[k] for k in ('project_name', 'technology', 'power_mw')},
                'expected': exp, 'reviewed_id': row['external_id'] == REVIEWED_ID})
json.dump(out, open(sys.argv[2], 'w'), ensure_ascii=False, indent=1)
print(len(out), 'DOCM battery events')
