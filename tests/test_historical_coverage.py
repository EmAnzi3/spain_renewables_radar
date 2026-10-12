import unittest
from datetime import date
from app.historical_backfill import build_plan
from scripts.historical_coverage_summary import coverage

class HistoricalCoverageTests(unittest.TestCase):
    def test_national_plan_remains_explicitly_incomplete_without_results(self):
        plan=build_plan(start=date(2026,1,1),end=date(2026,1,31))
        result=coverage(plan,[])
        self.assertEqual(result['total_supported_tasks'],10)
        self.assertEqual(result['not_run_tasks'],10)
        self.assertFalse(result['all_17_ccaa_covered'])
        self.assertFalse(result['all_source_months_complete'])
        self.assertEqual(sum(x['status']=='NO_COLLECTOR_IMPLEMENTED' for x in result['source_gaps']),8)
    def test_supported_complete_can_never_claim_missing_regions(self):
        plan=build_plan(start=date(2026,1,1),end=date(2026,1,31))
        audits=[dict(source_code=x['source_code'],from_date=x['start'],until_date=x['end'],
                     covered_days=x['days'],failed_days=0,unsupported_days=0,
                     complete=True,scanned_events=3)
                for x in plan['tasks'] if x['status']=='PENDING']
        result=coverage(plan,audits)
        self.assertTrue(result['all_source_months_complete'])
        self.assertFalse(result['all_17_ccaa_covered'])
        self.assertEqual(result['observed_source_events_not_unique_projects'],30)
    def test_unsupported_borm_is_kept_in_coverage(self):
        plan=build_plan(start=date(2025,9,1),end=date(2025,9,30))
        result=coverage(plan,[])
        self.assertEqual(result['unsupported_tasks'],1)
        self.assertEqual(result['not_run_tasks'],9)
    def test_duplicate_and_foreign_audits_rejected(self):
        plan=build_plan(start=date(2026,6,1),end=date(2026,6,30))
        e=next(x for x in plan['tasks'] if x['status']=='PENDING')
        audit=dict(source_code=e['source_code'],from_date=e['start'],until_date=e['end'],
                   covered_days=e['days'],failed_days=0,unsupported_days=0,
                   complete=True,scanned_events=0)
        with self.assertRaises(ValueError):coverage(plan,[audit,audit])
        with self.assertRaises(ValueError):coverage(plan,[dict(audit,source_code='DOGV')])
