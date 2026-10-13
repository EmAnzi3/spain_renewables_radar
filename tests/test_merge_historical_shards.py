import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from app.db import connect
from app.parser import ParsedEvent
from app.store import save_event
from scripts.historical_month import month_bounds,source_summary,coverage_summary
from scripts.merge_historical_shards import merge,load_shard

class MergeHistoricalTests(unittest.TestCase):
 def fixture(self,root,month,ident,name='Solar Alfa',source='BOE',raw='Official original'):
  first,last=month_bounds(month)
  p=Path(root)/source/month;p.mkdir(parents=True)
  db=p/'historical.sqlite';c=connect(str(db))
  save_event(c,ParsedEvent(source,ident,str(first),
        'Autorización fotovoltaica '+name,'https://www.boe.es/boe/dias/',
        raw,'PV',20.0,name,'Solar Alfa SL',None,'Huelva','Andalucía',
        'PUBLIC_INFO','EARLY','project-alpha'))
  c.close()
  rpt=p/'workspace/reports';rpt.mkdir(parents=True)
  with (rpt/'coverage_latest.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['source_code','date','status','candidates','inserted','error'])
   w.writeheader()
   for offset in range((last-first).days+1):
    day=first.fromordinal(first.toordinal()+offset)
    w.writerow(dict(source_code=source,date=str(day),status='OK',
      candidates=int(offset==0),inserted=int(offset==0),error=''))
  manifest={'certified':True,'source':source,'month':month,'window_start':str(first),
            'window_end':str(last),'database_sha256':hashlib.sha256(db.read_bytes()).hexdigest(),
            'quality':{'ERROR':0}}
  manifest.update(source_summary(db,source))
  manifest.update(coverage_summary(rpt/'coverage_latest.csv',source,first,last))
  (p/'manifest.json').write_text(json.dumps(manifest))
  return p

 def test_two_months_one_project_two_original_events(self):
  with tempfile.TemporaryDirectory() as td:
   a=self.fixture(td,'2026-06','BOE-B-2026-1')
   b=self.fixture(td,'2026-07','BOE-B-2026-2')
   result=merge([a,b],Path(td)/'result.sqlite',Path(td)/'report')
   self.assertEqual((result['observed_project_count'],result['observed_event_count']),(1,2))
   self.assertEqual(result['source_month_shards_supplied'],2)
   self.assertFalse(result['nationwide_historical_24_months_complete'])

 def test_uncertified_month_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   a=self.fixture(td,'2026-06','BOE-1')
   p=a/'manifest.json';d=json.loads(p.read_text());d['certified']=False;p.write_text(json.dumps(d))
   with self.assertRaises(ValueError):merge([a],Path(td)/'out.sqlite',Path(td)/'report')

 def test_duplicate_source_month_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   a=self.fixture(td,'2026-06','BOE-1')
   with self.assertRaises(ValueError):merge([a,a],Path(td)/'out.sqlite',Path(td)/'report')

 def test_identity_collision_does_not_silently_merge_plant(self):
  with tempfile.TemporaryDirectory() as td:
   a=self.fixture(td,'2026-06','BOE-1')
   b=self.fixture(td,'2026-07','BOE-2',name='Solar Beta')
   with self.assertRaisesRegex(ValueError,'identity conflicts'):
    merge([a,b],Path(td)/'out.sqlite',Path(td)/'report')
   self.assertFalse((Path(td)/'out.sqlite').exists())

 def test_same_source_event_changed_text_must_fail(self):
  # Two distinct monthly scopes cannot legitimately date the same external ID
  # to different publication months. Both an exact collision and an altered
  # original are rejected instead of rewriting source provenance.
  with tempfile.TemporaryDirectory() as td:
   a=self.fixture(td,'2026-06','BOE-1',raw='original June')
   b=self.fixture(td,'2026-07','BOE-1',raw='modified July')
   with self.assertRaisesRegex(ValueError,'identity conflicts'):
    merge([a,b],Path(td)/'out.sqlite',Path(td)/'report')
