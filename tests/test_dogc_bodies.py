import copy
import hashlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from pypdf import PdfWriter
from scripts.acquire_dogc_bodies import (BodyClient, extract_pages, header_check,
    index_generation, load_verified_index, validate_document_url)
from scripts.audit_dogc_index import parse_summary, search_parameters
from scripts.reconcile_dogc_daily import daily_parameters, semantic_index, window_days
from app.catalunya_inventory import canonical

URL = 'https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?documentId=1&type=01&language=ca_ES'
CANDIDATE = {'document_id':'1','source_url':URL,'publication_date':'2026-09-08','edition':'9747'}


def valid_index(root):
    import calendar
    generation = root / 'snapshots/test-1'; rawroot = generation / 'raw'; rawroot.mkdir(parents=True)
    manifest=[]
    def add(label,route,parameters,data):
        raw=json.dumps(data).encode(); sha=hashlib.sha256(raw).hexdigest()
        (rawroot/(sha+'.bin')).write_bytes(raw)
        manifest.append({'label':label,'sha256':sha,'bytes':len(raw),'status':200,
                         'method':'POST','url':'https://portaldogc.gencat.cat/eadop-rest/api/dogc/'+route,
                         'parameters':parameters,'retrieved_at':'2026-10-05T06:33:00+00:00'})
    end=date(2026,10,4); days=window_days(end,date(2026,10,5)); day=date(2026,9,8)
    title='Projecte fotovoltaic de prova'
    summary={'sumaris':[{'numDOGC':'9747','dateDOGC':'08/09/2026','title':'DOGC 9747',
                        'linkDownloadDOGCPDF':'https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?dogcId=9747&language=ca_ES',
                        'section':[{'document':[{'title':title,'linkDownloadDocumentPDF':URL}]}]}]}
    found={'numResultSearch':1,'resultSearch':[{'idDocument':'1','date':'08/09/2026','tipusDiari':'DOGC','title':title,'linkTitle':'?documentId=1'}]}
    for num in (1,2):
        add(f'monthly:{num}','searchDOGC',search_parameters(days[0],end,1),found)
        for year,month in ((2026,9),(2026,10)):
            rows=[]
            for n in range(1,calendar.monthrange(year,month)[1]+1):
                d=date(year,month,n); published=d==day
                rows.append({'date':d.strftime('%d/%m/%Y'),'hasDOGC':published,
                             'linkDOGC':f'?selectedYear={year}&selectedMonth={month}&numDOGC=9747' if published else None})
            add(f'calendar:{num}:{year}:{month}','calendarDOGC',{'year':year,'month':month,'language':'ca'},{'calendar':rows})
        for d in days:
            if d==day:add(f'edition:{num}:{d}','summaryDOGC',{'numDOGC':'9747','language':'ca'},summary)
            add(f'daily:{num}:{d}','searchDOGC',daily_parameters(d),found if d==day else {'numResultSearch':0})
    records=parse_summary(summary,'9747',day)
    candidates=[dict(row,review_status='UNREVIEWED_TITLE_CANDIDATE') for row in records.values()]
    audit={'run_id':'trusted-run','index_complete':True,'independent_live_passes':2,
           'original_byte_replay_verified':True,'independent_index_reconciliation':True,
           'window_start':str(days[0]),'window_end':str(end),'dispositions':1,
           'title_candidates':1,'annex_editions':[],
           'index_sha256':hashlib.sha256(canonical(semantic_index(records)).encode()).hexdigest()}
    for path,data in [(root/'latest.json',{'generation':'snapshots/test-1'}),(generation/'audit.json',audit),
                      (generation/'candidates.json',candidates),(rawroot/'acquisitions.json',manifest)]:
        path.write_text(json.dumps(data))
    return generation,manifest


def fake_response(status=200, raw=b'%PDF-1.7\nbody\n%%EOF'):
    r=Mock(); r.status_code=status; r.headers={'Content-Type':'application/pdf'}
    r.iter_content.return_value=[raw]
    if status>=400:r.raise_for_status.side_effect=requests.HTTPError('source error',response=r)
    return r


class BodyTests(unittest.TestCase):
    def test_valid_complete_index_is_rebuilt_before_body_download(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);valid_index(root)
            audit,candidates=load_verified_index(root,'trusted-run')
            self.assertEqual(audit['dispositions'],1);self.assertEqual(len(candidates),1)

    def test_wrong_run_and_failed_index_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);g,_=valid_index(root)
            with self.assertRaises(ValueError):load_verified_index(root,'another-run')
            audit=json.loads((g/'audit.json').read_text());audit['index_complete']=False
            (g/'audit.json').write_text(json.dumps(audit))
            with self.assertRaises(ValueError):load_verified_index(root,'trusted-run')

    def test_edited_candidates_are_not_used(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);g,_=valid_index(root)
            (g/'candidates.json').write_text('[]')
            with self.assertRaises(ValueError):load_verified_index(root,'trusted-run')

    def test_corrupted_index_bytes_are_not_trusted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);g,manifest=valid_index(root)
            (g/'raw'/(manifest[0]['sha256']+'.bin')).write_bytes(b'changed')
            with self.assertRaises(ValueError):load_verified_index(root,'trusted-run')

    def test_missing_daily_evidence_is_not_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);g,manifest=valid_index(root)
            (g/'raw/acquisitions.json').write_text(json.dumps(manifest[:-1]))
            with self.assertRaises((ValueError,KeyError)):load_verified_index(root,'trusted-run')

    def test_generation_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for path in ['../elsewhere','/tmp/elsewhere','snapshots/../../elsewhere']:
                (root/'latest.json').write_text(json.dumps({'generation':path}))
                with self.assertRaises(ValueError):index_generation(root)

    def test_original_document_url_is_accepted(self):
        validate_document_url(URL,'1')

    def test_foreign_host_credentials_port_and_identity_rejected(self):
        for url in [URL.replace('portaldogc.gencat.cat','evil.invalid'),URL.replace('https://','https://user@'),
                    URL.replace('.cat/','.cat:444/'),URL.replace('documentId=1','documentId=2'),URL+'&documentId=1']:
            with self.assertRaises(ValueError):validate_document_url(url,'1')

    def test_header_is_actual_publication_not_act_date(self):
        result=header_check('Núm. 9747 - 8.9.2026\nResolució de 31 agost',CANDIDATE)
        self.assertEqual(result['status'],'VERIFIED')

    def test_wrong_date_or_edition_fails(self):
        for text in ['Núm. 9746 - 8.9.2026','Núm. 9747 - 7.9.2026']:
            with self.assertRaises(ValueError):header_check(text,CANDIDATE)

    def test_absent_header_is_not_fabricated(self):
        self.assertEqual(header_check('No readable header',CANDIDATE)['status'],'UNRECOGNIZED')

    def test_blank_pdf_preserves_page_and_flags_no_ocr(self):
        writer=PdfWriter();writer.add_blank_page(width=595,height=842)
        stream=io.BytesIO();writer.write(stream)
        parsed=extract_pages(stream.getvalue(),CANDIDATE)
        self.assertEqual(parsed['empty_text_pages'],[1]);self.assertFalse(parsed['ocr_used'])
        self.assertFalse(parsed['project_fields_extracted'])

    def test_success_stores_exact_bytes_and_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            client=BodyClient(Path(td));r=fake_response();client.session.get=Mock(return_value=r)
            raw,meta=client.get_pdf(CANDIDATE)
            self.assertEqual((Path(td)/(meta['sha256']+'.pdf')).read_bytes(),raw)
            self.assertTrue(meta['complete']);self.assertEqual(len(client.observations),1)

    def test_denial_and_rate_limit_not_retried(self):
        for status in (401,403,429):
            with tempfile.TemporaryDirectory() as td:
                client=BodyClient(Path(td));client.session.get=Mock(return_value=fake_response(status))
                with self.assertRaises(requests.HTTPError):client.get_pdf(CANDIDATE)
                self.assertEqual(client.session.get.call_count,1)

    def test_redirect_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            client=BodyClient(Path(td));r=fake_response(302);r.headers['Location']='https://evil.invalid/file.pdf'
            client.session.get=Mock(return_value=r)
            with self.assertRaises(ValueError):client.get_pdf(CANDIDATE)
            self.assertEqual(client.session.get.call_count,1)

    def test_html_and_truncated_pdf_not_accepted(self):
        for raw in [b'<html>maintenance</html>',b'%PDF-1.7 truncated']:
            with tempfile.TemporaryDirectory() as td:
                client=BodyClient(Path(td));client.session.get=Mock(return_value=fake_response(raw=raw))
                with self.assertRaises(ValueError):client.get_pdf(CANDIDATE)

    def test_timeout_retry_budget_is_bounded(self):
        with tempfile.TemporaryDirectory() as td, patch('scripts.acquire_dogc_bodies.time.sleep'):
            client=BodyClient(Path(td));client.session.get=Mock(side_effect=requests.Timeout('timeout'))
            with self.assertRaises(requests.Timeout):client.get_pdf(CANDIDATE)
            self.assertEqual(client.session.get.call_count,2)

    def test_certificate_error_does_not_trigger_insecure_retry(self):
        with tempfile.TemporaryDirectory() as td:
            client=BodyClient(Path(td));client.session.get=Mock(side_effect=requests.exceptions.SSLError('certificate'))
            with self.assertRaises(requests.exceptions.SSLError):client.get_pdf(CANDIDATE)
            self.assertEqual(client.session.get.call_count,1)
