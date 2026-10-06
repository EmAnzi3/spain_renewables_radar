"""Synthetic contract regressions; live coverage is verified separately."""
from datetime import date
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('bopv_index',Path(__file__).parents[1]/'scripts/reconcile_bopv_index.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
DAY=date(2026,10,5);FILE='s26_0190.shtml';URL=m.HOST+'/bopv2/datos/2026/10/'+FILE
TITLE='ANUNCIO de información pública del proyecto fotovoltaico de prueba.'
HTML='''<h2 class="tituGeneral">Sumario n.º <span>190</span>, lunes 5 de octubre de 2026</h2>
<ul class="listaFormatos"><li class="formatoPdf"><a href="s26_0190.pdf">PDF</a></li></ul>
<div class="txtBloque"><p class="BOPVSumarioTitulo"><a href="2604093a.shtml">'''+TITLE+'''</a></p><span class="BOPVSumarioOrden">4093</span></div>'''
CAL="var bopvIdioma = 'es'; var year=2026;var month=9;var diasHabilitados=['20261005'];var enlaces=[['s26_0190.shtml']];"
BODY='''<h2 class="tituGeneral">N.º <span>190</span>, lunes 5 de octubre de 2026</h2><input id="bopvNumOrden" value="2026004093"><p class="BOPVTitulo">'''+TITLE+'''</p>'''


class BOPVReconciliationTests(unittest.TestCase):
    def test_declared_calendar_day_and_multiple_editions_are_retained(self):
        self.assertEqual(m.parse_calendar(CAL,2026,10),{DAY:[FILE]})
        self.assertEqual(len(m.parse_calendar(CAL.replace("'s26_0190.shtml'","'s26_0190.shtml','s26_0191.shtml'"),2026,10)[DAY]),2)
    def test_explicit_empty_calendar_is_not_a_network_failure(self):
        self.assertEqual(m.parse_calendar(CAL.replace("['20261005']","[]").replace("[['s26_0190.shtml']]","[]"),2026,10),{})
    def test_wrong_calendar_scope_fails_even_when_empty(self):
        with self.assertRaises(ValueError):m.parse_calendar(CAL,2026,9)
    def test_calendar_array_length_mismatch_fails(self):
        with self.assertRaises(ValueError):m.parse_calendar(CAL.replace("['20261005']","['20261005','20261006']"),2026,10)
    def test_duplicate_day_and_edition_fail(self):
        for c in [CAL.replace("['20261005']","['20261005','20261005']").replace("[['s26_0190.shtml']]","[['s26_0190.shtml'],['s26_0191.shtml']]"),CAL.replace("'s26_0190.shtml'","'s26_0190.shtml','s26_0190.shtml'")]:
            with self.assertRaises(ValueError):m.parse_calendar(c,2026,10)
    def test_calendar_does_not_execute_javascript(self):
        with self.assertRaises((ValueError,SyntaxError)):m.parse_calendar(CAL.replace("['20261005']","[__import__('os').getcwd()]"),2026,10)
    def test_summary_date_title_and_identity(self):
        rows=m.parse_summary(HTML,URL,DAY,FILE)
        self.assertEqual(len(rows),1);row=rows['2026/04093']
        self.assertEqual((row['publication_date'],row['edition'],row['title']),('2026-10-05',190,TITLE))
    def test_summary_wrong_date_or_number_fails(self):
        for h in [HTML.replace('lunes 5','martes 6'),HTML.replace('<span>190</span>','<span>191</span>')]:
            with self.assertRaises(ValueError):m.parse_summary(h,URL,DAY,FILE)
    def test_date_weekday_conflict_is_not_accepted(self):
        with self.assertRaises(ValueError):m.parse_summary(HTML.replace('lunes','martes'),URL,DAY,FILE)
    def test_original_pdf_must_confirm_the_summary_edition(self):
        with self.assertRaises(ValueError):m.parse_summary(HTML.replace('s26_0190.pdf','s26_0191.pdf'),URL,DAY,FILE)
    def test_missing_summary_items_not_empty_success(self):
        with self.assertRaises(ValueError):m.parse_summary(HTML.split('<div')[0],URL,DAY,FILE)
    def test_duplicate_disposition_fails(self):
        with self.assertRaises(ValueError):m.parse_summary(HTML+HTML[HTML.index('<div'):],URL,DAY,FILE)
    def test_alias_url_prefix_has_same_identity(self):
        plain=m.HOST+'/bopv2/datos/2026/10/2604093a.shtml'
        alias=plain.replace('/bopv2/','/web01-bopv/es/bopv2/')
        self.assertEqual(m.article_id(plain),m.article_id(alias))
    def test_foreign_or_wrong_language_article_not_accepted(self):
        for url in [m.HOST+'/web01-bopv/eu/bopv2/datos/2026/10/2604093a.shtml','https://other.invalid/bopv2/datos/2026/10/2604093a.shtml',m.HOST+'/bopv2/datos/2026/10/2504093a.shtml']:
            with self.assertRaises(ValueError):m.article_id(url)
    def test_reconciliation_rejects_missing_or_added_records(self):
        rows=m.parse_summary(HTML,URL,DAY,FILE)
        with self.assertRaises(ValueError):m.reconcile(rows,{})
        with self.assertRaises(ValueError):m.reconcile({},rows)
    def test_titles_cannot_be_changed_to_force_a_match(self):
        rows=m.parse_summary(HTML,URL,DAY,FILE);other={k:dict(v,title='Different') for k,v in rows.items()}
        with self.assertRaises(ValueError):m.reconcile(rows,other)
    def test_body_matches_its_own_dated_summary(self):
        row=m.parse_summary(HTML,URL,DAY,FILE)['2026/04093']
        result=m.body_provenance(BODY,row['source_url'],row)
        self.assertTrue(result['body_header_verified']);self.assertEqual(result['semantic_classification'],'NOT_VALIDATED')
    def test_old_decision_date_does_not_replace_publication(self):
        row=m.parse_summary(HTML,URL,DAY,FILE)['2026/04093']
        result=m.body_provenance(BODY+'<p>Resolución de 22 de septiembre de 2026</p>',row['source_url'],row)
        self.assertEqual(result['publication_date'],'2026-10-05')
    def test_body_wrong_identity_date_title_fails(self):
        row=m.parse_summary(HTML,URL,DAY,FILE)['2026/04093']
        for body in [BODY.replace('2026004093','2026004094'),BODY.replace('lunes 5','martes 6'),BODY.replace(TITLE,'Other title')]:
            with self.assertRaises(ValueError):m.body_provenance(body,row['source_url'],row)


if __name__=='__main__':unittest.main()
