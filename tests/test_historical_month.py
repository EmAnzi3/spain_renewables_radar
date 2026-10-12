import csv
from datetime import date
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.historical_month import month_bounds,validate_source,coverage_summary,source_summary

class HistoricalMonthsTests(unittest.TestCase):
    def test_exact_approved_24_month_window(self):
        self.assertEqual(month_bounds('2024-10'),(date(2024,10,1),date(2024,10,31)))
        self.assertEqual(month_bounds('2026-09'),(date(2026,9,1),date(2026,9,30)))
        for value in ('2024-09','2026-10','2026-00','2026-13','202601','bad'):
            with self.subTest(value=value),self.assertRaises(ValueError):month_bounds(value)
    def test_unimplemented_region_is_not_claimed(self):
        for value in ('DOGV','BON','BOPV','BOR','BOIB','BOC-CAN','BOCANT','BOPA','COMMERCIAL'):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_source(value)
        for value in ('BOE','BOJA','BOA','DOCM','DOG','DOGC'):
            self.assertEqual(validate_source(value),value)
    def test_coverage_requires_all_dates_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'coverage.csv'
            with path.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['source_code','date','status','candidates','inserted','error'])
                w.writeheader()
                w.writerows([
                    dict(source_code='BOE',date='2026-07-01',status='OK',candidates=2,inserted=2,error=''),
                    dict(source_code='BOE',date='2026-07-02',status='ERROR',candidates=0,inserted=0,error='503'),
                ])
            result=coverage_summary(path,'BOE',date(2026,7,1),date(2026,7,2))
            self.assertEqual(result['source_days_failed'],1)
            self.assertEqual(result['source_failures'][0]['error'],'503')
            with self.assertRaises(ValueError):coverage_summary(path,'BOE',date(2026,7,1),date(2026,7,3))
    def test_independent_shard_event_provenance_and_identity(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'data.sqlite'
            from app.db import connect
            c=connect(str(db))
            c.execute("""INSERT INTO projects
                (project_key,project_name,commercial_stage,first_seen,last_seen,latest_event_type)
                VALUES('x','Demo','EARLY','2026-07-01','2026-07-01','PUBLIC_INFO')""")
            c.execute("""INSERT INTO events(source_code,external_id,publication_date,title,url,raw_text,
                project_key,event_type,commercial_stage) VALUES
                ('BOE','BOE-B-2026-1','2026-07-01','Demo','https://boe.es/','Original body',
                'x','PUBLIC_INFO','EARLY')""")
            c.commit();c.close()
            r=source_summary(db,'BOE')
            self.assertEqual((r['events'],r['source_scoped_projects']),(1,1))
            c=sqlite3.connect(db)
            c.execute("UPDATE events SET source_code='BOJA'")
            c.commit();c.close()
            with self.assertRaises(ValueError):source_summary(db,'BOE')
