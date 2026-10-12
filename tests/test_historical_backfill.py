"""Historical backfill never makes missing gazette coverage look complete."""
from datetime import date,timedelta
from pathlib import Path
import tempfile
import unittest

from app.historical_backfill import (
    NATIONAL_START,SCANNABLE,REGIONAL_GAZETTES,MISSING_GAZETTES,
    build_plan,months,scan_source,official_event,issues,
)
from app.parser import ParsedEvent


def make_event(day:date,identity='BOE-A-2026-TEST',title='Autorización planta solar'):
    return ParsedEvent(source_code='BOE',external_id=identity,
        publication_date=day.isoformat(),title=title,
        url='https://www.boe.es/diario_boe/txt.php?id='+identity,
        raw_text='Texto original publicado para '+identity,
        technology='PV',power_mw=50.0,project_name='Proyecto Solar A',
        promoter=None,expediente=None,province='Huelva',ccaa='Andalucía',
        event_type='PUBLIC_INFO',commercial_stage='EARLY',
        project_key='test-project-key')

class Stub:
    def __init__(self,scenario):
        self.scenario=scenario
        self.calls=[];self.closed=False
    def collect_day(self,day):
        self.calls.append(day)
        outcome=self.scenario(day)
        if isinstance(outcome,Exception):raise outcome
        return outcome
    def close(self):
        self.closed=True

class HistoricalTests(unittest.TestCase):
    def test_complete_two_years_are_partitioned_without_gaps(self):
        end=date(2026,10,11);start=date(2024,10,12)
        plan=build_plan(start=start,end=end)
        self.assertEqual(plan['period_days'],730)
        self.assertEqual(plan['month_windows'],25)
        self.assertEqual(plan['regional_gazettes_implemented'],9)
        self.assertEqual(plan['regional_gazettes_total'],17)
        self.assertEqual(plan['regional_gazettes_missing'],8)
        self.assertEqual({x['source_code'] for x in plan['source_gaps'] if x['status']=='NO_COLLECTOR_IMPLEMENTED'},
                         set(MISSING_GAZETTES))
        self.assertEqual(len(plan['tasks']),len(SCANNABLE)*25)
        self.assertEqual(plan['months'][0]['start'],'2024-10-12')
        self.assertEqual(plan['months'][-1]['end'],'2026-10-11')
        self.assertTrue(any(x['source_code']=='BORM' and x['status']=='UNSUPPORTED' for x in plan['tasks']))
        self.assertEqual({x['status'] for x in plan['tasks']},{'PENDING','UNSUPPORTED'})
        prev=None
        for month in plan['months']:
            first=date.fromisoformat(month['start']);last=date.fromisoformat(month['end'])
            if prev is not None:self.assertEqual(first,prev+timedelta(days=1))
            prev=last

    def test_known_official_date_and_url_are_required(self):
        day=date(2026,6,21)
        event=make_event(day)
        self.assertEqual(official_event(event,'BOE',day)['external_id'],event.external_id)
        event.publication_date='2026-06-20'
        with self.assertRaisesRegex(ValueError,'date'):official_event(event,'BOE',day)
        event.publication_date=day.isoformat()
        event.url='https://example.invalid/false-gazette'
        with self.assertRaisesRegex(ValueError,'official'):official_event(event,'BOE',day)

    def test_scan_is_complete_without_inserting_into_db(self):
        day=date(2026,6,21);end=day+timedelta(days=2)
        fake=Stub(lambda d:[make_event(d,identity='BOE-A-'+d.strftime('%Y%m%d'))])
        with tempfile.TemporaryDirectory() as td:
            outcome=scan_source(source='BOE',start=day,end=end,out=Path(td),
                                collector=fake,clock=date(2026,10,12))
            self.assertTrue(outcome['complete'])
            self.assertEqual(outcome['covered_days'],3)
            self.assertEqual(outcome['scanned_events'],3)
            self.assertEqual(outcome['events_inserted_into_production_db'],0)
            self.assertTrue(fake.closed)
            folder=Path(td)/'BOE_2026-06-21_2026-06-23'
            self.assertTrue((folder/'events.json').exists())
            self.assertTrue((folder/'index.html').exists())

    def test_partial_is_always_marked_incomplete_and_preserved(self):
        day=date(2026,6,21)
        fake=Stub(lambda d:RuntimeError('503 upstream') if d.day==22 else [make_event(d,identity=str(d))])
        with tempfile.TemporaryDirectory() as td:
            outcome=scan_source(source='BOE',start=day,end=day+timedelta(days=2),
                    out=Path(td),collector=fake,clock=date(2026,10,12))
            self.assertFalse(outcome['complete'])
            self.assertEqual(outcome['failed_days'],1)
            self.assertEqual(outcome['covered_days'],2)
            self.assertEqual(outcome['scanned_events'],2)
            self.assertEqual(outcome['days'][1]['status'],'ERROR')
            self.assertTrue((Path(td)/'BOE_2026-06-21_2026-06-23/audit.json').exists())

    def test_missing_projects_and_mw_are_quality_flags_not_synthetic_values(self):
        fields={'project_name':None,'power_mw':None,'promoter':None,'province':None,'expediente':None}
        flags=issues(fields)
        self.assertIn('NO_UNAMBIGUOUS_PROJECT_NAME',flags)
        self.assertIn('MW_MISSING',flags)
        self.assertIn('PROMOTER_NOT_EXTRACTED',flags)
        self.assertIn('PROVINCE_MISSING_OR_MULTIPROVINCE',flags)

    def test_duplicate_source_id_in_one_day_fails_and_no_event_is_certified(self):
        day=date(2026,6,21)
        event=make_event(day)
        fake=Stub(lambda d:[event,event])
        with tempfile.TemporaryDirectory() as td:
            outcome=scan_source(source='BOE',start=day,end=day,out=Path(td),
                                collector=fake,clock=date(2026,10,12))
            self.assertEqual(outcome['scanned_events'],0)
            self.assertEqual(outcome['failed_days'],1)
            self.assertFalse(outcome['complete'])

    def test_unsupported_regional_year_is_not_counted_as_zero_publications(self):
        day=date(2025,6,21)
        fake=Stub(lambda d:[])
        with tempfile.TemporaryDirectory() as td:
            outcome=scan_source(source='BORM',start=day,end=day,out=Path(td),
                                collector=fake,clock=date(2026,10,12))
            self.assertEqual(outcome['unsupported_days'],1)
            self.assertFalse(outcome['complete'])
            self.assertEqual(fake.calls,[])

    def test_future_and_oversized_batches_rejected(self):
        fake=Stub(lambda d:[])
        with tempfile.TemporaryDirectory() as td:
            for first,last in [(date(2026,10,10),date(2026,10,12)),
                               (date(2026,1,1),date(2026,2,15))]:
                with self.assertRaises(ValueError):
                    scan_source(source='BOE',start=first,end=last,out=Path(td),
                                collector=fake,clock=date(2026,10,12))

    def test_missing_collector_cannot_be_mislabeled_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                scan_source(source='DOGV',start=date(2026,6,21),end=date(2026,6,21),
                            out=Path(td),collector=Stub(lambda _:[]),clock=date(2026,10,12))
