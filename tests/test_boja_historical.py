import unittest
import calendar
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import date
from app.collectors.boja import BOJACollector

DAY=date(2024,10,5)
def row(n,day='05/10/2024'):
 return {'id':'disposition.2024.200.'+str(n),'date':day,'summary':'Resolución de energía'}

class BOJAHistoricalCoverageTests(unittest.TestCase):
 def test_actual_summary_html_and_details_parser_remain_operable(self):
  self.assertEqual(BOJACollector._plain('<p>Proyecto <b>fotovoltaico</b></p>'),
                   'Proyecto fotovoltaico')
  row={'id':'disposition.2026.128.9',
       'summary':'<p>Autorización parque <b>fotovoltaico</b> de 20 MW</p>'}
  collector=BOJACollector()
  collector._day_rows=lambda day: iter([row])
  collector._detail=lambda row: ('La instalación fotovoltaica Solar del Sur, de 20 MW',
                                  'https://www.juntadeandalucia.es/eboja.html')
  events=collector.collect_day(DAY)
  self.assertEqual(len(events),1)
  self.assertEqual(events[0].source_code,'BOJA')

 def setup_collector(self,fn):
  collector=BOJACollector()
  collector._get_json=fn
  return collector
 def test_official_unique_id_sort_and_bounded_page_size(self):
  requested=[]
  def fetch(url,params=None,allow_empty_400=False):
   requested.append(params.copy())
   return {'total_hits':1,'results':[row(1)]}
  list(self.setup_collector(fetch)._day_rows(DAY))
  self.assertEqual(requested[0]['order_by'],'id')
  self.assertEqual(requested[0]['size'],100)

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
 def test_unverified_400_requires_independent_calendar_evidence(self):
  def fetch(url,params=None,allow_empty_400=False):
   if params['date_from']==str(DAY):return {'_unverified_400':True}
   return {'total_hits':2,'results':[row(1,'04/10/2024'),row(2,'06/10/2024')]}
  collector=self.setup_collector(fetch)
  checked=[]
  collector._verified_nonpublication_day=lambda day: checked.append(day) or True
  self.assertEqual(list(collector._day_rows(DAY)),[])
  self.assertEqual(checked,[DAY])
 def test_unverified_400_on_published_edition_is_error(self):
  def fetch(url,params=None,allow_empty_400=False):
   if params['date_from']==str(DAY):return {'_unverified_400':True}
   return {'total_hits':1,'results':[row(1)]}
  collector=self.setup_collector(fetch)
  def unavailable(day):
   raise ValueError("BOJA returned HTTP 400 on a date with an official edition")
  collector._verified_nonpublication_day=unavailable
  with self.assertRaisesRegex(ValueError,'official edition'):
   list(collector._day_rows(DAY))
 def test_400_in_calendar_check_is_not_empty(self):
  def fetch(url,params=None,allow_empty_400=False):
   return {'_unverified_400':True}
  collector=self.setup_collector(fetch)
  def calendar_error(day):
   raise ValueError("Official calendar unavailable")
  collector._verified_nonpublication_day=calendar_error
  with self.assertRaisesRegex(ValueError,"calendar unavailable"):
   list(collector._day_rows(DAY))
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


 def test_official_year_calendar_links_are_independent_publication_proof(self):
  pieces=[]
  months=list(__import__('app.collectors.boja',fromlist=['MONTHS_ES']).MONTHS_ES)
  for i,name in enumerate(months,1):
   rows=''.join(f'<td class="dia-boja"><a href="/eboja/2024/{i*100+n}/index.html">{n}</a></td>'
                for n in range(4,22))
   pieces.append(f'<table class="calendario_tabla"><caption>{name}</caption>{rows}</table>')
  days=BOJACollector.parse_official_calendar(''.join(pieces),2024)
  self.assertIn(date(2024,11,4),days)
  self.assertNotIn(date(2024,11,2),days)
  self.assertEqual(len(days),216)
 def test_restricted_announcements_are_leads_not_synthetic_projects(self):
  title=('Anuncio del Servicio Territorial de Energía sobre solicitud de '
         'autorización administrativa de la instalación solar fotovoltaica en Sevilla')
  row={'id':'disposition.2024.219.42','summary':title}
  collector=BOJACollector()
  collector._day_rows=lambda day:iter([row])
  body=title+'\nTexto de acceso restringido en virtud del artículo 32 del Decreto 188/2018.'
  collector._detail=lambda record:(body,'https://www.juntadeandalucia.es/eboja/2024/219/')
  self.assertEqual(collector.collect_day(DAY),[])
  self.assertEqual(len(collector._restricted_review),1)
  self.assertFalse(collector._restricted_review[0]['added_to_projects'])
  with tempfile.TemporaryDirectory() as td:
   import os
   old=os.getcwd()
   try:
    os.chdir(td)
    collector.persist_metadata(None)
    import json
    report=json.loads(Path('reports/boja/historical_restricted_leads.json').read_text())
    self.assertEqual(report['restricted_document_count'],1)
    self.assertEqual(report['restricted_leads'][0]['raw_text'],body)
   finally:os.chdir(old)
