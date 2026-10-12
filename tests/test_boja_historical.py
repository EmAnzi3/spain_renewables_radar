import unittest
from datetime import date
from app.collectors.boja import BOJACollector

DAY=date(2024,10,5)
def row(n,day='05/10/2024'):
 return {'id':'disposition.2024.200.'+str(n),'date':day,'summary':'Resolución de energía'}

class BOJAHistoricalCoverageTests(unittest.TestCase):
 def setup_collector(self,fn):
  collector=BOJACollector()
  collector._get_json=fn
  return collector
 def test_server_page_cap_is_not_assumed_requested_page_size(self):
  def fetch(url,params=None,allow_empty_400=False):
   page=params['page']
   results=[row(i) for i in range(1,101)] if page==0 else [row(i) for i in range(101,107)]
   return {'total_hits':106,'results':results}
  collector=self.setup_collector(fetch)
  self.assertEqual(len(list(collector._day_rows(DAY))),106)
 def test_repeated_page_cannot_fake_complete_retrieval(self):
  def fetch(url,params=None,allow_empty_400=False):
   return {'total_hits':3,'results':[row(1),row(2)]}
  with self.assertRaisesRegex(ValueError,'repeated'):
   list(self.setup_collector(fetch)._day_rows(DAY))
 def test_unverified_400_must_have_adjacent_official_evidence(self):
  def fetch(url,params=None,allow_empty_400=False):
   if params['date_from']==str(DAY):return {'_unverified_400':True}
   return {'total_hits':2,'results':[row(1,'04/10/2024'),row(2,'06/10/2024')]}
  self.assertEqual(list(self.setup_collector(fetch)._day_rows(DAY)),[])
 def test_unverified_400_contradicting_wider_search_is_error(self):
  def fetch(url,params=None,allow_empty_400=False):
   if params['date_from']==str(DAY):return {'_unverified_400':True}
   return {'total_hits':1,'results':[row(1)]}
  with self.assertRaisesRegex(ValueError,'contradicts'):
   list(self.setup_collector(fetch)._day_rows(DAY))
 def test_400_in_adjacent_check_is_not_empty(self):
  def fetch(url,params=None,allow_empty_400=False):
   return {'_unverified_400':True}
  with self.assertRaises(ValueError):list(self.setup_collector(fetch)._day_rows(DAY))
 def test_missing_row_id_date_total_or_complete_page_must_fail(self):
  variants=[
   {'total_hits':1,'results':[{'date':'05/10/2024'}]},
   {'total_hits':1,'results':[{'id':'x','date':'06/10/2024'}]},
   {'total_hits':2,'results':[row(1)]},
   {'total_hits':True,'results':[row(1)]},
  ]
  for case in variants:
   def fetch(url,params=None,allow_empty_400=False):
    return {'total_hits':2,'results':[]} if params['page'] else case
   with self.subTest(case=case),self.assertRaises(ValueError):
    list(self.setup_collector(fetch)._day_rows(DAY))
