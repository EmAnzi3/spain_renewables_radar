import unittest
from scripts.dogc_pdf_headers import document_headers, header_check

CANDIDATE = {'publication_date':'2026-09-07','edition':'9746'}
HEADER = ('Núm. 9746 - 7 .9.20261/9 Diari Oficial de la Generalitat de Catalunya\n'
          'CVE-DOGC-A-26243001-2026')

class MastheadLayoutTests(unittest.TestCase):
    def test_observed_header_after_long_body_is_verified(self):
        result=header_check('body '*500+HEADER,CANDIDATE,expected_page=1,total_pages=9)
        self.assertEqual(result['status'],'VERIFIED')
        self.assertEqual(result['original_header'],HEADER)

    def test_spaces_and_attached_page_number_are_preserved(self):
        result=header_check(HEADER,CANDIDATE)
        self.assertEqual((result['publication_date'],result['page'],result['pages']),('2026-09-07',1,9))

    def test_historical_reference_without_journal_block_is_not_a_header(self):
        self.assertEqual(header_check('DOGC Núm. 9746 - 7.9.2026',CANDIDATE)['status'],'UNRECOGNIZED')

    def test_wrong_date_and_edition_fail(self):
        for text in [HEADER.replace('9746','9745'),HEADER.replace('7 .9.2026','8.9.2026')]:
            with self.assertRaises(ValueError):header_check(text,CANDIDATE)

    def test_masthead_requires_cve(self):
        self.assertEqual(header_check(HEADER.split('\n')[0],CANDIDATE)['status'],'UNRECOGNIZED')

    def test_duplicate_block_fails(self):
        with self.assertRaises(ValueError):header_check(HEADER+'\n'+HEADER,CANDIDATE)

    def test_printed_page_and_total_are_checked(self):
        for kwargs in [{'expected_page':2},{'total_pages':8}]:
            with self.assertRaises(ValueError):header_check(HEADER,CANDIDATE,**kwargs)

    def test_every_page_must_identify_same_document(self):
        one=HEADER.replace('1/9','1/2');two=HEADER.replace('1/9','2/2')
        pages=[{'page':1,'text':one},{'page':2,'text':two}]
        self.assertEqual(len(document_headers(pages,CANDIDATE)),2)
        pages[1]['text']=two.replace('26243001','26243002')
        with self.assertRaises(ValueError):document_headers(pages,CANDIDATE)

    def test_reordered_extracted_pages_fail(self):
        pages=[{'page':1,'text':HEADER.replace('1/9','2/2')},{'page':2,'text':HEADER.replace('1/9','1/2')}]
        with self.assertRaises(ValueError):document_headers(pages,CANDIDATE)

    def test_unrecognized_page_remains_explicit(self):
        self.assertEqual(document_headers([{'page':1,'text':'No masthead'}],CANDIDATE)[0]['status'],'UNRECOGNIZED')

    def test_invalid_calendar_date_fails(self):
        with self.assertRaises(ValueError):header_check(HEADER.replace('7 .9.2026','31.2.2026'),CANDIDATE)

    def test_future_or_out_of_scope_annex_is_not_inferred(self):
        with self.assertRaises(ValueError):header_check(HEADER.replace('9746 -','9746A -'),CANDIDATE)
