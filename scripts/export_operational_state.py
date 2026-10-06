"""Export a closed standalone DB and receipt, never a failed staging DB."""
import hashlib,json,os,shutil,sqlite3
from contextlib import closing
from pathlib import Path

def main():
    status=json.loads(Path('reports/operational/latest.json').read_text())
    if status.get('state') not in ('PARTIAL','COMPLETE') or not status.get('database_promoted'):raise ValueError('Only a checked operational update can become a reusable state')
    root=Path('operational-state');root.mkdir(exist_ok=True)
    with closing(sqlite3.connect('data/spain_renewables.sqlite')) as c,closing(sqlite3.connect(root/'spain_renewables.sqlite')) as dest:
        c.backup(dest);projects=c.execute('SELECT count(*) FROM projects').fetchone()[0]
    shutil.copyfile('reports/operational/latest.json',root/'latest.json')
    receipt={'run_id':os.environ['GITHUB_RUN_ID'],'head_sha':os.environ['GITHUB_SHA'],'state':status['state'],
             'projects':projects,'database_sha256':hashlib.sha256((root/'spain_renewables.sqlite').read_bytes()).hexdigest()}
    (root/'state_receipt.json').write_text(json.dumps(receipt,indent=2));print('STATE_EXPORTED',json.dumps(receipt))
if __name__=='__main__':main()
