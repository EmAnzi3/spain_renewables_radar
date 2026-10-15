import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from app.db import connect
from app.parser import ParsedEvent
from app.store import save_event
from scripts.import_certified_history import import_history


def ev(ident,raw='Texto original',date='2025-06-10',source='DOGC'):
    return ParsedEvent(source_code=source,external_id=ident,publication_date=date,title='Parc solar '+ident,url='https://dogc.gencat.cat/'+ident,
        raw_text=raw,technology='PV',power_mw=10.0,project_name='Solar '+ident,promoter=None,expediente=None,province='Lleida',
        ccaa='Cataluña',event_type='PUBLIC_INFO',commercial_stage='EARLY',project_key='k-'+ident)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.export=self.root/'export'
        self.shards=[]
    def tearDown(self):self.tmp.cleanup()
    def shard(self,source,month,events,status='CERTIFIED',**manifest):
        folder=self.export/'shards'/source/month;folder.mkdir(parents=True)
        c=connect(str(folder/'historical.sqlite'))
        for e in events:save_event(c,e)
        c.commit();c.close()
        m={'source':source,'month':month,'certified':status=='CERTIFIED','source_days_expected':30,'source_days_ok':30,
           'source_days_failed':0,'structural_errors':[],'events':len(events),'quality':{'ERROR':0},
           'database_sha256':hashlib.sha256((folder/'historical.sqlite').read_bytes()).hexdigest()}
        m.update(manifest);(folder/'manifest.json').write_text(json.dumps(m))
        self.shards.append({'source':source,'month':month,'status':status})
        (self.export/'index.json').write_text(json.dumps({'shards':self.shards}))
        return folder
    def db(self):
        return str(self.root/'state.sqlite')

    def test_additive_and_idempotent(self):
        self.shard('DOGC','2025-06',[ev('a'),ev('b')])
        c=connect(self.db());save_event(c,ev('live',date='2026-10-10'));c.commit();c.close()
        first=import_history(self.db(),str(self.export));second=import_history(self.db(),str(self.export))
        self.assertEqual((first['events_inserted'],second['events_inserted'],second['events_already_present']),(2,0,2))
        with sqlite3.connect(self.db()) as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],3)

    def test_existing_official_record_is_kept_and_conflict_reported(self):
        self.shard('DOGC','2025-06',[ev('a',raw='Texto distinto')])
        c=connect(self.db());save_event(c,ev('a'));c.commit();c.close()
        got=import_history(self.db(),str(self.export))
        self.assertEqual(len(got['conflicts']),1);self.assertEqual(got['events_inserted'],0)
        with sqlite3.connect(self.db()) as c:self.assertEqual(c.execute('SELECT raw_text FROM events').fetchone()[0],'Texto original')

    def test_record_level_flags_accepted_but_incomplete_days_and_tampering_rejected(self):
        self.shard('BOA','2025-06',[ev('f',source='BOA')],status='COMPLETE_WITH_QUALITY_FLAGS',
                   structural_errors=[{'code':'MISSING_PROJECT_NAME'}])
        self.assertEqual(import_history(self.db(),str(self.export))['events_inserted'],1)
        self.shard('BOA','2025-07',[ev('g',date='2025-07-02',source='BOA')],status='COMPLETE_WITH_QUALITY_FLAGS',source_days_failed=1,source_days_ok=29)
        with self.assertRaises(ValueError):import_history(self.db(),str(self.export))
        self.shards.pop();(self.export/'index.json').write_text(json.dumps({'shards':self.shards}))
        folder=self.shard('DOE','2025-06',[ev('h',source='DOE')])
        c=sqlite3.connect(folder/'historical.sqlite');c.execute("UPDATE events SET raw_text='x'");c.commit()
        c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close()
        with self.assertRaises(ValueError):import_history(self.db(),str(self.export))

    def test_uncovered_status_is_never_imported(self):
        self.shard('BORM','2025-06',[ev('z',source='BORM')],status='NO_USABLE_SHARD')
        self.assertEqual(import_history(self.db(),str(self.export))['shards_imported'],0)

    def test_event_outside_month_rejected(self):
        self.shard('DOGC','2025-06',[ev('late',date='2025-07-01')])
        with self.assertRaises(ValueError):import_history(self.db(),str(self.export))
