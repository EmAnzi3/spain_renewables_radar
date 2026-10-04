import html
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
from app.collectors.dog import ROOT,DOGCollector,archive_links,document_identity,disposition_type,events_from_notice,extract_records,official_url,parse_calendar,parse_index,parse_notice,power_evidence,section_urls,spanish_number

FIXTURES=json.loads((Path(__file__).parent/'fixtures/dog/notices.json').read_text())

def fixture_html(row):
    day=date.fromisoformat(row['publication_date'])
    return ('<html><head><title>DOG 169 del '+day.strftime('%d/%m/%Y')+' - '+html.escape(row['title'])+'</title></head><body><main>'+''.join('<p>'+html.escape(s)+'</p>' for s in row['body_excerpt'].splitlines())+'</main></body></html>').encode()

class DOGPureTests(unittest.TestCase):
    def test_observed_multi_project_notice_has_two_distinct_scopes(self):
        got=parse_notice(fixture_html(FIXTURES[1]),FIXTURES[1])
        self.assertIsNone(got['review_reason'])
        self.assertEqual([r['project_name'] for r in got['records']],['Nesa Monte Arca Norte','Nesa Monte Arca Sur'])
        self.assertEqual([r['expediente'] for r in got['records']],['IN408A 2019/103-NT','IN408A 2019/104-NT'])
        self.assertEqual([r['promoter'] for r in got['records']],['Nesa Vento Galego 2, S.L','Nesa Vento Galego 3, S.L'])
        for row in got['records']:
            self.assertEqual((row['power_mw'],row['technology'],row['province'],row['event_type']),(20,'WIND','Pontevedra','PUBLIC_INFO'))
            self.assertEqual(row['execution_duration_months'],12)
            self.assertIsNone(row['work_start']);self.assertIsNone(row['work_end'])
    def test_expansion_does_not_use_old_capacity_or_invent_increment(self):
        got=parse_notice(fixture_html(FIXTURES[0]),FIXTURES[0])['records'][0]
        self.assertEqual((got['project_name'],got['power_mw'],got['province']),('PSFV Porto Barroso',.99,'Lugo'))
        self.assertEqual(got['power_scope'],'resulting_plant_capacity')
        self.assertEqual(got['event_type'],'CONSTRUCTION_AUTH')
        self.assertIn('EXPANSION_CAPACITY_IS_RESULTING_PLANT_NOT_INCREMENT',[f['code'] for f in got['quality_flags']])
    def test_multifile_missing_scope_is_reviewed_not_merged(self):
        rows,reason=extract_records(FIXTURES[1]['title'],'Historical background only.')
        self.assertEqual(rows,[]);self.assertIn('BODY_SECTIONS',reason)
    def test_missing_reference_is_not_invented(self):
        rows,reason=extract_records('Información pública del parque eólico Proyecto ficticio, situado en Lugo.','')
        self.assertEqual(rows,[]);self.assertIn('REFERENCE',reason)
    def test_request_does_not_become_authorization(self):
        for text in ('Se somete a información pública la solicitud de autorización administrativa de construcción.','Solicitud de autorización administrativa previa del parque eólico Proyecto ficticio.'):
            self.assertEqual(disposition_type(text),'PUBLIC_INFO')
        self.assertEqual(disposition_type('Se deniega la solicitud de autorización administrativa previa.'),'DENIED')
    def test_explicit_grant_and_closed_procedure(self):
        self.assertEqual(disposition_type('Se otorga autorización administrativa previa y de construcción.'),'CONSTRUCTION_AUTH')
        self.assertEqual(disposition_type('Se acepta la renuncia al proyecto.'),'WITHDRAWN')
        self.assertEqual(disposition_type('Se archiva el expediente del proyecto.'),'PROCEDURE_ENDED')
    def test_unclassified_candidate_is_explicit_review(self):
        rows,reason=extract_records('Subvenciones para energía eólica.','')
        self.assertEqual(rows,[]);self.assertIsNotNone(reason)
    def test_date_is_verified_not_taken_from_act_or_current_day(self):
        wrong=dict(FIXTURES[0],publication_date='2026-08-06')
        with self.assertRaises(ValueError):parse_notice(fixture_html(FIXTURES[0]),wrong)
    def test_index_detail_identity_must_agree(self):
        wrong=dict(FIXTURES[0],title='Changed identity')
        with self.assertRaises(ValueError):parse_notice(fixture_html(FIXTURES[0]),wrong)
        with self.assertRaises(ValueError):parse_notice(b'<html><title>Maintenance</title></html>',FIXTURES[0])
    def test_spanish_thousands_decimal_and_units(self):
        self.assertEqual(spanish_number('1.500'),1500)
        self.assertEqual(spanish_number('1.500,5'),1500.5)
        self.assertEqual(power_evidence('Potencia instalada: 1.500 kW.')[0]['mw'],1.5)
        self.assertEqual(power_evidence('Potencia instalada: 1,5 MW.')[0]['mw'],1.5)
        self.assertEqual(power_evidence('40 MWh de energía; 40 MVA; 20 MW de acceso.'),[])
    def test_conflicting_current_power_is_not_arbitrarily_selected(self):
        row=FIXTURES[0];got=extract_records(row['title'],row['body_excerpt'].replace('instalada: 990','instalada: 900'))[0][0]
        self.assertIsNone(got['power_mw'])
        self.assertIn('SOURCE_POWER_DISAGREEMENT',[f['code'] for f in got['quality_flags']])
    def test_calendar_must_match_month_and_have_complete_rows(self):
        payload=[dict(fecha='07/09/2026',url=ROOT+'mostrarContenido.do?paginaCompleta=Si&ruta=/dog/Publicados/2026/20260907/Indice_es.html')]
        self.assertEqual(parse_calendar(payload,2026,9)[0]['date'],'2026-09-07')
        for bad in ([],{},[{}],payload*2):
            with self.assertRaises((ValueError,KeyError)):parse_calendar(bad,2026,9)
        with self.assertRaises(ValueError):parse_calendar(payload,2026,10)
    def test_official_identity_language_variants_not_multiple_projects(self):
        url=FIXTURES[0]['url']
        self.assertEqual(document_identity(url),document_identity(url.replace('_es.html','_gl.pdf')))
        for bad in (url.replace('https:','http:'),url.replace('www.xunta.gal','www.xunta.gal.evil.test'),url.replace('www.xunta.gal','user@www.xunta.gal')):
            with self.assertRaises(ValueError):official_url(bad)
    def test_dated_sections_and_notice_indexes(self):
        day=date(2026,9,7);ruta='/dog/Publicados/2026/20260907/Secciones1_es.html'
        raw=f'<html><title>DOG 169 del 07/09/2026</title><a href="mostrarContenido.do?ruta={ruta}">Anuncios</a></html>'.encode()
        self.assertEqual(len(section_urls(raw,ROOT,day)),1)
        raw=(f'<html><title>DOG 169 del 07/09/2026</title><a href="{FIXTURES[0]["url"]}">'+html.escape(FIXTURES[0]['title'])+'</a></html>').encode()
        self.assertEqual(len(parse_index(raw,ROOT,day)),1)
        with self.assertRaises(ValueError):parse_index(raw,ROOT,date(2026,9,8))
        with self.assertRaises(ValueError):section_urls(b'<html><title>Error</title></html>',ROOT,day)
    def test_archive_link_does_not_redate_or_merge_old_inventory(self):
        notice=parse_notice(fixture_html(FIXTURES[1]),FIXTURES[1])
        row=dict(record_key='consultations:fixture',url='https://economia.xunta.gal/example',title='Parque Norte (expediente IN408A 2019/103-NT)',documents=[],web_publication_date=None)
        snapshot=dict(source='XUNTA_PUBLIC',complete=True,records=[row]);before=json.dumps(snapshot)
        link=archive_links([notice],snapshot)['matches'][0]
        self.assertEqual(link['rule'],'EXACT_ADMINISTRATIVE_REFERENCE')
        self.assertEqual(link['verified_dog_publication_date'],'2026-09-30')
        self.assertIsNone(link['archive_web_publication_date']);self.assertEqual(json.dumps(snapshot),before)
        self.assertEqual(archive_links([notice],None)['status'],'ARCHIVE_NOT_LOADED')
        with self.assertRaises(ValueError):archive_links([notice],dict(source='XUNTA_PUBLIC',complete=False))
    def test_promoter_address_does_not_create_false_madrid_location(self):
        got=extract_records(FIXTURES[1]['title'],FIXTURES[1]['body_excerpt'])[0]
        self.assertTrue(all(r['province']=='Pontevedra' for r in got))
        self.assertTrue(all('Madrid' not in r['municipalities'] for r in got))
    def test_no_edition_requires_live_official_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=DOGCollector(output_dir=tmp);c._month=Mock(return_value=[dict(date='2026-09-07',url='irrelevant')])
            self.assertEqual(c.collect_day(date(2026,9,6)),[])
            self.assertEqual(c.audit['days']['2026-09-06']['edition_status'],'NO_EDITION_IN_OFFICIAL_CALENDAR')
    def test_transport_checks_redirect_before_contacting_foreign_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=Mock();session.headers={};r=Mock(status_code=302,headers={'Location':'https://evil.test/source'})
            session.request.return_value=r;c=DOGCollector(session=session,output_dir=tmp)
            with self.assertRaises(RuntimeError):c._request(ROOT+'portalPublicoHome.do?lang=es')
            self.assertEqual(session.request.call_count,1)
    def test_persistent_network_failure_has_one_bounded_budget(self):
        import requests
        with tempfile.TemporaryDirectory() as tmp:
            session=Mock();session.headers={};session.request.side_effect=requests.Timeout('fixture timeout')
            c=DOGCollector(session=session,output_dir=tmp)
            with patch('app.collectors.dog.time.sleep'):
                for _ in range(2):
                    with self.assertRaises(RuntimeError):c._request(ROOT+'portalPublicoHome.do?lang=es')
            self.assertEqual(session.request.call_count,3)

class DOGIntegrationTests(unittest.TestCase):
    def test_dated_events_keep_full_original_text_and_replay_idempotently(self):
        from app.db import connect
        from app.store import save_event
        from app.identifiers import valid_expediente
        from app.reporting import write_quality_issues
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/'test.sqlite'));collector=DOGCollector(output_dir=str(Path(tmp)/'dog'))
            for fixture in FIXTURES:
                notice=parse_notice(fixture_html(fixture),fixture)
                for event,row in zip(events_from_notice(notice),notice['records']):
                    self.assertTrue(valid_expediente(event.expediente));self.assertEqual(event.raw_text,notice['raw_text'])
                    self.assertEqual(save_event(conn,event),(True,True));self.assertEqual(save_event(conn,event),(False,False))
                    collector.metadata[event.external_id]=(notice,row)
            collector.persist_metadata(conn)
            self.assertEqual(conn.execute('SELECT count(*) FROM projects').fetchone()[0],3)
            self.assertEqual(conn.execute('SELECT count(*) FROM regional_public_metadata').fetchone()[0],3)
            issues,_,_=write_quality_issues(conn,out_dir=tmp)
            self.assertFalse(any(i['severity']=='ERROR' for i in issues));conn.close()
    def test_component_identity_does_not_depend_on_display_order(self):
        notice=parse_notice(fixture_html(FIXTURES[1]),FIXTURES[1])
        before={e.expediente:(e.external_id,e.project_key) for e in events_from_notice(notice)}
        notice['records'].reverse();after={e.expediente:(e.external_id,e.project_key) for e in events_from_notice(notice)}
        self.assertEqual(before,after);self.assertEqual(len({k[1] for k in after.values()}),2)

if __name__=='__main__':unittest.main()
