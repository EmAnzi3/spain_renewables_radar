import csv,json,sqlite3,tempfile,unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from app.db import connect
from app.parser import ParsedEvent
from app.store import save_event
from app.operational import assess_coverage,event_fingerprints,run_update,read_state,save_state
DAY=date(2026,10,5)

def event(code='BOE',ident='A1'):
    return ParsedEvent(source_code=code,external_id=ident,publication_date=str(DAY),title='Proyecto Demo',url='https://www.boe.es/test',
        raw_text='Fuente original inmutable',technology='PV',power_mw=4.0,project_name='Demo',promoter='Promotor S.L.',
        expediente='DEMO-1',province='Madrid',ccaa='Madrid',event_type='PUBLIC_INFO',commercial_stage='EARLY',project_key='demo')

def coverage(codes,failed=()):
    return [{'source_code':c,'date':str(DAY),'status':'ERROR' if c in failed else 'OK','error':'timeout' if c in failed else ''} for c in codes]

class CoverageTests(unittest.TestCase):
    def test_failure_is_partial_not_certified_and_last_good_date_is_preserved(self):
        old={'GVA_PUBLIC':{'last_complete_window_end':'2026-10-01','last_complete_run_id':'old'}}
        got=assess_coverage(coverage(['BOE','GVA_PUBLIC'],['GVA_PUBLIC']),['BOE','GVA_PUBLIC'],['BOE','GVA_PUBLIC'],DAY,DAY,old)
        self.assertEqual(got['state'],'PARTIAL');self.assertFalse(got['full_certification'])
        self.assertEqual(got['sources']['GVA_PUBLIC']['status'],'UNAVAILABLE')
        self.assertEqual(got['sources']['GVA_PUBLIC']['last_complete_window_end'],'2026-10-01')
        self.assertEqual(got['sources']['BOE']['last_complete_window_end'],str(DAY))
    def test_all_failed_cannot_be_success(self):
        self.assertEqual(assess_coverage(coverage(['BOE'],['BOE']),['BOE'],['BOE'],DAY,DAY)['state'],'FAILED')
    def test_selected_subset_is_never_complete_national_coverage(self):
        got=assess_coverage(coverage(['BOE']),['BOE'],['BOE','GVA_PUBLIC'],DAY,DAY)
        self.assertEqual(got['state'],'PARTIAL');self.assertEqual(got['sources']['GVA_PUBLIC']['status'],'NOT_REQUESTED')
    def test_missing_repeated_wrong_or_unrecognized_day_fails(self):
        valid=coverage(['BOE'])
        for rows in [[],valid+valid,[dict(valid[0],date='2026-10-04')],[dict(valid[0],status='SKIPPED')]]:
            with self.assertRaises(ValueError):assess_coverage(rows,['BOE'],['BOE'],DAY,DAY)
    def test_complete_operational_is_not_strict_certification(self):
        got=assess_coverage(coverage(['BOE']),['BOE'],['BOE'],DAY,DAY)
        self.assertEqual(got['state'],'COMPLETE');self.assertFalse(got['full_certification'])
    def test_enrichment_failure_remains_visible(self):
        got=assess_coverage(coverage(['BOE'])+[{'source_code':'REE','status':'ERROR','error':'network'}],['BOE'],['BOE'],DAY,DAY)
        self.assertEqual(got['state'],'PARTIAL');self.assertEqual(len(got['enrichment_failures']),1)

class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=self.root/'radar.sqlite'
        c=connect(str(self.db));save_event(c,event('GVA_PUBLIC','old'))
        save_state(c,{'run_key':'old','sources':{'GVA_PUBLIC':{'last_complete_window_end':'2026-10-01','status':'HISTORICAL'}}})
        self.original=event_fingerprints(c);c.close()
    def tearDown(self):self.temp.cleanup()
    def fake(self,*,structural=False,mutate=False,all_failed=False):
        def runner(cmd,**kwargs):
            self.assertNotIn('--strict-coverage',cmd);codes=cmd[cmd.index('--sources')+1].split(',');self.assertIn('GVA_PUBLIC',codes)
            staged=Path(cmd[cmd.index('--db')+1]);c=connect(str(staged))
            if mutate:c.execute("UPDATE events SET raw_text='changed'");c.commit()
            else:save_event(c,event('BOE','new'))
            c.close();reports=kwargs['cwd']/'reports';reports.mkdir();rows=coverage(codes,codes if all_failed else ['GVA_PUBLIC'])
            with (reports/'coverage_latest.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['source_code','date','status','error']);w.writeheader();w.writerows(rows)
            (reports/'quality_issues_latest.csv').write_text('severity,project_key,code,detail\n'+('ERROR,demo,BAD,invalid\n' if structural else ''))
            return SimpleNamespace(returncode=0)
        return runner
    def test_partial_publish_preserves_existing_source_and_status(self):
        got=run_update(self.db,self.root/'reports',days=1,until=DAY,pipeline_runner=self.fake())
        self.assertEqual(got['state'],'PARTIAL');self.assertTrue(got['database_promoted'])
        c=connect(str(self.db));self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0],2)
        after=event_fingerprints(c);self.assertTrue(all(after[k]==v for k,v in self.original.items()))
        self.assertEqual(read_state(c)['GVA_PUBLIC']['last_complete_window_end'],'2026-10-01');c.close()
        self.assertTrue(list((self.root/'reports/runs').glob('*/before.sqlite')))
        self.assertFalse(self.db.with_suffix('.sqlite.operational.lock').exists())
    def test_source_mutation_or_structural_error_leaves_original_db(self):
        for options in ({'mutate':True},{'structural':True},{'all_failed':True}):
            with self.subTest(options=options),self.assertRaises((ValueError,RuntimeError)):
                run_update(self.db,self.root/'reports',days=1,until=DAY,pipeline_runner=self.fake(**options))
            c=connect(str(self.db));self.assertEqual(event_fingerprints(c),self.original);c.close()
            state=json.loads((self.root/'reports/latest.json').read_text());self.assertEqual(state['state'],'FAILED');self.assertFalse(state['database_promoted'])
    def test_nonzero_process_preserves_previous_database(self):
        with self.assertRaises(RuntimeError):
            run_update(self.db,self.root/'reports',days=1,until=DAY,pipeline_runner=lambda *a,**kw:SimpleNamespace(returncode=1))
        c=connect(str(self.db));self.assertEqual(event_fingerprints(c),self.original);c.close()
    def test_concurrent_lock_is_not_overwritten(self):
        lock=self.db.with_suffix('.sqlite.operational.lock');lock.touch()
        with self.assertRaises(FileExistsError):run_update(self.db,self.root/'reports',days=1,until=DAY,pipeline_runner=self.fake())
        self.assertTrue(lock.exists())
