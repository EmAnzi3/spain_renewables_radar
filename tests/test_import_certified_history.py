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


class SupersessionTests(unittest.TestCase):
    """A re-classified certified month removes acts it no longer projects (quarantined, project rebuilt)."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.export=self.root/'export';self.shards=[]
        self.helper=ImportTests('test_additive_and_idempotent');self.helper.tmp=self.tmp;self.helper.root=self.root
        self.helper.export=self.export;self.helper.shards=self.shards
    def tearDown(self):self.tmp.cleanup()
    def state(self,*events):
        c=connect(str(self.root/'state.sqlite'))
        for e in events:save_event(c,e)
        c.commit();return c
    def test_act_dropped_by_reclassification_is_quarantined_and_project_rebuilt(self):
        from dataclasses import replace
        keep=ev('a');wrong=replace(ev('b'),project_key=keep.project_key,event_type='CONSTRUCTION_AUTH',commercial_stage='AUTHORIZED',publication_date='2025-06-20')
        c=self.state(keep,wrong);self.assertEqual(c.execute('SELECT commercial_stage FROM projects').fetchone()[0],'AUTHORIZED');c.close()
        self.helper.shard('DOGC','2025-06',[ev('a')])
        got=import_history(str(self.root/'state.sqlite'),str(self.export),supersede_sources=('DOGC',))
        self.assertEqual(len(got['superseded']),1);self.assertIn('AUTHORIZED_TO_EARLY',got['superseded'][0]['outcome'])
        with sqlite3.connect(self.root/'state.sqlite') as c:
            self.assertEqual(c.execute("SELECT external_id FROM events").fetchall(),[('a',)])
            self.assertEqual(c.execute('SELECT commercial_stage FROM projects').fetchone()[0],'EARLY')
            q=c.execute('SELECT reason,payload_json FROM quarantined_source_events').fetchone()
            self.assertEqual(q[0],'SUPERSEDED_BY_CERTIFIED_RECLASSIFICATION');self.assertEqual(json.loads(q[1])['external_id'],'b')
    def test_project_without_remaining_acts_is_removed(self):
        self.state(ev('a'),ev('gone')).close();self.helper.shard('DOGC','2025-06',[ev('a')])
        got=import_history(str(self.root/'state.sqlite'),str(self.export),supersede_sources=('DOGC',))
        self.assertEqual(got['superseded'][0]['outcome'],'REMOVED_NO_REMAINING_EVENT')
        with sqlite3.connect(self.root/'state.sqlite') as c:self.assertEqual(c.execute('SELECT count(*) FROM projects').fetchone()[0],1)
    def test_without_opt_in_nothing_is_removed(self):
        self.state(ev('a'),ev('gone')).close();self.helper.shard('DOGC','2025-06',[ev('a')])
        self.assertEqual(import_history(str(self.root/'state.sqlite'),str(self.export))['superseded'],[])
        with sqlite3.connect(self.root/'state.sqlite') as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],2)
    def test_mass_removal_is_refused(self):
        self.state(*[ev('x%d'%i) for i in range(12)]).close();self.helper.shard('DOGC','2025-06',[ev('x0')])
        with self.assertRaises(ValueError):import_history(str(self.root/'state.sqlite'),str(self.export),supersede_sources=('DOGC',))


class ProvenanceKeyTests(unittest.TestCase):
    """Run 38916278000: a DOGC act attached to an existing project kept the shard's key in its provenance row."""
    def test_provenance_row_follows_the_stored_event_project(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name);export=root/'export'
        helper=ImportTests('test_additive_and_idempotent');helper.root=root;helper.export=export;helper.shards=[]
        folder=helper.shard('DOGC','2025-06',[ev('new')])
        with sqlite3.connect(folder/'historical.sqlite') as s:
            s.execute('''CREATE TABLE regional_public_metadata (source_code TEXT NOT NULL,external_id TEXT NOT NULL,project_key TEXT NOT NULL,
                web_publication_date TEXT NOT NULL,source_url TEXT NOT NULL,evidence_json TEXT NOT NULL,PRIMARY KEY(source_code,external_id))''')
            s.execute("INSERT INTO regional_public_metadata VALUES ('DOGC','new','k-new','2025-06-10','https://dogc.gencat.cat/new','{\"quality_flags\":[]}')")
        s=sqlite3.connect(folder/'historical.sqlite');s.execute('PRAGMA wal_checkpoint(TRUNCATE)');s.close()
        import hashlib;m=json.loads((folder/'manifest.json').read_text());m['database_sha256']=hashlib.sha256((folder/'historical.sqlite').read_bytes()).hexdigest()
        (folder/'manifest.json').write_text(json.dumps(m))
        c=connect(str(root/'state.sqlite'));save_event(c,ev('old'))
        c.execute('''CREATE TABLE regional_public_metadata (source_code TEXT NOT NULL,external_id TEXT NOT NULL,project_key TEXT NOT NULL,
            web_publication_date TEXT NOT NULL,source_url TEXT NOT NULL,evidence_json TEXT NOT NULL,PRIMARY KEY(source_code,external_id),
            FOREIGN KEY(project_key) REFERENCES projects(project_key))''')
        from app.store import _ensure_aliases
        _ensure_aliases(c);c.execute("INSERT INTO project_identity_aliases VALUES ('k-new','k-old','TEST','DOGC','old','{}')");c.commit();c.close()
        import_history(str(root/'state.sqlite'),str(export))
        with sqlite3.connect(root/'state.sqlite') as c:
            ek=c.execute("SELECT project_key FROM events WHERE external_id='new'").fetchone()[0]
            mk=c.execute("SELECT project_key FROM regional_public_metadata WHERE external_id='new'").fetchone()[0]
            self.assertEqual((ek,mk),('k-old','k-old'));self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
