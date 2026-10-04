import copy,json,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch

from app.collectors.sabia import events_from_detail,parse_detail_html,SABIACollector
from app.collectors.sabia_assets import parse_assets,source_provinces,write_event_metadata
from app.db import connect
from app.reporting import write_quality_issues
from app.store import save_event
from scripts.recover_sabia_snapshot import seed_details
from test_sabia import MUEL_DETAIL

FIXTURE=json.loads(Path('tests/fixtures/sabia_assets_20261003.json').read_text(encoding='utf-8'))
BY_CODE={r['environmental_code']:r for r in FIXTURE}

class SABIAAssetTests(unittest.TestCase):
    def test_named_plants_have_individual_capacity_not_first_group_capacity(self):
        got=parse_assets(BY_CODE['20260259']['title'])
        self.assertEqual([(x.name,x.power_mw) for x in got],[('CEREZO SOLAR',60.91),('ABETO SOLAR',61.6),('GOLETA SOLAR',134.76),('NOGUERA SOLAR',60.91),('GRILLETE SOLAR',256.63)])

    def test_two_power_units_do_not_create_two_assets(self):
        got=parse_assets(BY_CODE['20260220']['title'])
        self.assertEqual([(x.name,x.power_mw) for x in got],[('MAURICIO SOLAR',100),('MARTIÁNEZ SOLAR',50.5)])

    def test_only_explicit_each_capacity_is_repeated(self):
        for code,names,mw in [('20260243',['RODA','QUISPE'],52),('20260116',['FUENTE ÁLAMO HÍBRIDA','DERRAMADOR HÍBRIDA'],20)]:
            got=parse_assets(BY_CODE[code]['title'])
            self.assertEqual([x.name for x in got],names)
            self.assertEqual([x.power_mw for x in got],[mw,mw])
        shared=parse_assets(BY_CODE['20260224']['title'])
        self.assertEqual(len(shared),2)
        self.assertTrue(all(x.power_mw is None and x.group_power_mw==30 for x in shared))

    def test_storage_not_replaced_with_existing_generation_plant(self):
        expected={'20260181':'BAT CIUDAD RODRIGO','20260178':'BAT CAPARACENA','20260252':'ANDÉVALO',
                  '20260244':'BAT FUENTES','20260245':'BAT VALBUENA'}
        for code,name in expected.items():
            got=parse_assets(BY_CODE[code]['title']);self.assertEqual(got[0].name,name)
            self.assertIsNone(got[0].power_mw)

    def test_multi_geography_retains_all_source_provinces(self):
        self.assertEqual(source_provinces(BY_CODE['20260261']),['Guadalajara','Madrid'])
        self.assertEqual(source_provinces(BY_CODE['20260256']),['Burgos','Palencia'])
        self.assertEqual(source_provinces(BY_CODE['20260211']),['Albacete','Ciudad Real'])

    def test_scope_specific_unnamed_pv_not_named_after_electrolyser(self):
        got=parse_assets(BY_CODE['20260233']['title'])
        self.assertIsNone(got[0].name);self.assertEqual(got[0].power_mw,110)
        self.assertEqual(got[0].reason,'UNNAMED_RENEWABLE_COMPONENT_OF_HYDROGEN_PROJECT')

    def test_reference_is_verbatim_components_stable_and_events_idempotent(self):
        d=dict(BY_CODE['20260259'],entry_date='2026-09-22',consultation_start='2026-10-01',raw_text='Exact raw source',promoter='Developer S.L.')
        events=events_from_detail(d,'FTV',d['source_url'])
        self.assertEqual(len(events),10);self.assertEqual(len({e.project_key for e in events}),5)
        self.assertEqual({e.expediente for e in events},{d['substantive_code']})
        self.assertEqual({e.raw_text for e in events},{'Exact raw source'})
        self.assertEqual({e.title for e in events},{d['title']})
        self.assertEqual({e.commercial_stage for e in events},{'EARLY'})
        with tempfile.TemporaryDirectory() as tmp:
            con=connect(str(Path(tmp)/'test.sqlite'))
            for e in events:save_event(con,e)
            for e in events:self.assertEqual(save_event(con,e),(False,False))
            self.assertEqual(con.execute('select count(*) from projects').fetchone()[0],5)
            self.assertEqual(con.execute('select count(*) from events').fetchone()[0],10)
            con.close()

    def test_all_audited_source_titles_pass_without_waiving_real_missing_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            con=connect(str(Path(tmp)/'test.sqlite'));details={};candidates={}
            for row in FIXTURE:
                code=row['environmental_code'];d=dict(row,entry_date='2026-09-20',raw_text=row['title'],state='CONSULTAS PREVIAS')
                details[code]=(d,row['source_url']);candidates[code]={'source_type':row['source_type']}
                for ev in events_from_detail(d,row['source_type'],row['source_url']):save_event(con,ev)
            write_event_metadata(con,details,candidates,events_from_detail)
            issues,_,_=write_quality_issues(con,Path(tmp)/'reports')
            self.assertEqual([i for i in issues if i['severity']=='ERROR'],[])
            self.assertEqual([i['code'] for i in issues if i['severity']=='WARN'],['SOURCE_UNNAMED_RENEWABLE_COMPONENT'])
            self.assertEqual(con.execute('select count(*) from projects').fetchone()[0],53)
            self.assertEqual(con.execute('select count(*) from event_source_metadata').fetchone()[0],53)
            con.close()

    def test_cache_seed_preserves_dates_and_never_copies_old_indexes(self):
        import hashlib
        now=datetime.now(timezone.utc);at=(now-timedelta(hours=2)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();dest=Path(tmp)/'dest'
            (source/'FTV-index.html').write_text('old index')
            (source/'20260236.html').write_text(MUEL_DETAIL,encoding='utf-8')
            record={'detail':parse_detail_html(MUEL_DETAIL),'retrieved_at':at,'url':'https://sede.miteco.gob.es/example',
                    'sha256':hashlib.sha256(MUEL_DETAIL.encode()).hexdigest()}
            (source/'20260236.json').write_text(json.dumps(record))
            self.assertEqual(seed_details(source,dest,now)['seeded'],1)
            self.assertFalse((dest/'FTV-index.html').exists())
            self.assertEqual(json.loads((dest/'20260236.json').read_text())['retrieved_at'],at)
            stale=seed_details(source,Path(tmp)/'later',now+timedelta(days=2))
            self.assertEqual(stale['seeded'],0)
            self.assertEqual(stale['expired_or_invalid'],1)

    def test_cached_details_are_reparsed_from_raw_not_old_parsed_names(self):
        import hashlib,os
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'SABIA_CACHE_DIR':tmp}):
            collector=SABIACollector();code='20260236';raw=collector.cache_dir/(code+'.html')
            raw.write_text(MUEL_DETAIL,encoding='utf-8')
            record={'detail':{'environmental_code':code,'title':'WRONG OLD PARSE'},
                    'retrieved_at':datetime.now(timezone.utc).isoformat(),'url':'https://sede.miteco.gob.es/example',
                    'sha256':hashlib.sha256(MUEL_DETAIL.encode()).hexdigest()}
            (collector.cache_dir/(code+'.json')).write_text(json.dumps(record))
            with patch.object(collector,'_session') as network:
                d,_=collector._detail(code)
                self.assertNotEqual(d['title'],'WRONG OLD PARSE');network.assert_not_called()

if __name__=='__main__':unittest.main()
