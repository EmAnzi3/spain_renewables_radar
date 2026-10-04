import copy
import unittest
from datetime import date
from scripts.audit_dogc_index import (
    compare_indexes, parse_calendar, parse_search, parse_summary,
    search_parameters, source_date,
)


def month_rows():
    return {'calendar':[{'date':f'{i:02d}/10/2026','hasDOGC':i in (3,4),
            'linkDOGC':f'?selectedYear=2026&selectedMonth=10&numDOGC={9761+i}' if i in (3,4) else None}
            for i in range(1,32)]}


def summary():
    document={'title':'Resolució <i>solar</i>',
        'linkDownloadDocumentPDF':'https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?documentId=123&type=01'}
    return {'sumaris':[{'numDOGC':'9765','dateDOGC':'04/10/2026',
        'linkDownloadDOGCPDF':'https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?dogcId=9765&language=ca_ES','section':[
        {'header':[{'subheader':[{'document':[document]}]}]}]}]}


def with_annex():
    result=summary()
    annex=copy.deepcopy(result['sumaris'][0])
    annex.update(numDOGC='9765A',title='Annex A',
        linkDownloadDOGCPDF='https://portaldogc.gencat.cat/utilsEADOP/AppJava/PdfProviderServlet?dogcId=9765A&language=ca_ES')
    doc=annex['section'][0]['header'][0]['subheader'][0]['document'][0]
    doc['linkDownloadDocumentPDF']=doc['linkDownloadDocumentPDF'].replace('documentId=123','documentId=456')
    result['sumaris'].append(annex)
    return result


def search_row(number=123):
    return {'idDocument':str(number),'date':'04/10/2026','tipusDiari':'DOGC','title':'Resolució solar',
            'linkTitle':f'?action=fitxa&documentId={number}','current':False}


class DOGCIndexTests(unittest.TestCase):
    def setUp(self):
        self.start=date(2026,9,5);self.end=date(2026,10,4)

    def test_official_sunday_edition_is_not_skipped(self):
        days=parse_calendar(month_rows(),2026,10)
        self.assertEqual(days[date(2026,10,4)],'9765')

    def test_all_days_not_only_business_days_required(self):
        data=month_rows();data['calendar'].pop()
        with self.assertRaises(ValueError):parse_calendar(data,2026,10)

    def test_wrong_month_is_not_a_valid_empty_calendar(self):
        with self.assertRaises(ValueError):parse_calendar(month_rows(),2026,9)

    def test_duplicate_calendar_date_rejected(self):
        data=month_rows();data['calendar'].append(data['calendar'][0])
        with self.assertRaises(ValueError):parse_calendar(data,2026,10)

    def test_publication_requires_consistent_source_link(self):
        data=month_rows();data['calendar'][3]['linkDOGC']=None
        with self.assertRaises(ValueError):parse_calendar(data,2026,10)

    def test_calendar_link_wrong_month_rejected(self):
        data=month_rows();data['calendar'][3]['linkDOGC']='?selectedYear=2026&selectedMonth=9&numDOGC=9765'
        with self.assertRaises(ValueError):parse_calendar(data,2026,10)

    def test_nested_summary_and_publication_not_act_date(self):
        result=parse_summary(summary(),'9765',self.end)
        self.assertEqual(result[('123','2026-10-04')]['title'],'Resolució solar')
        self.assertFalse(result[('123','2026-10-04')]['body_acquired'])

    def test_wrong_edition_or_date_fails(self):
        for edition,day in [('9999',self.end),('9765',self.start)]:
            with self.assertRaises(ValueError):parse_summary(summary(),edition,day)

    def test_missing_documents_fail_even_with_http_success_structure(self):
        data=summary();data['sumaris'][0]['section']=[{'title':'Maintenance'}]
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)

    def test_ambiguous_document_identity_fails(self):
        data=summary();doc=data['sumaris'][0]['section'][0]['header'][0]['subheader'][0]['document'][0]
        doc['linkDownloadDocumentPDF']+='&documentId=456'
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)

    def test_closed_or_noncurrent_dispositions_not_filtered(self):
        p=search_parameters(self.start,self.end,2)
        self.assertIs(p['current'],False);self.assertEqual(p['value'],'')
        total,rows=parse_search({'numResultSearch':1,'resultSearch':[search_row()]},self.start,self.end,1)
        self.assertEqual(total,1);self.assertEqual(len(rows),1)

    def test_truncated_search_page_fails(self):
        with self.assertRaises(ValueError):parse_search({'numResultSearch':51,'resultSearch':[search_row()]},self.start,self.end,1)

    def test_last_page_exact_count(self):
        total,rows=parse_search({'numResultSearch':51,'resultSearch':[search_row()]},self.start,self.end,2)
        self.assertEqual(total,51);self.assertEqual(len(rows),1)

    def test_out_of_window_search_disposition_fails(self):
        row=search_row();row['date']='05/10/2026'
        with self.assertRaises(ValueError):parse_search({'numResultSearch':1,'resultSearch':[row]},self.start,self.end,1)

    def test_result_link_and_id_must_agree(self):
        row=search_row();row['linkTitle']='?documentId=456'
        with self.assertRaises(ValueError):parse_search({'numResultSearch':1,'resultSearch':[row]},self.start,self.end,1)

    def test_two_routes_disagreement_is_not_hidden(self):
        a=parse_summary(summary(),'9765',self.end)
        _,b=parse_search({'numResultSearch':1,'resultSearch':[search_row(456)]},self.start,self.end,1)
        differences=compare_indexes(a,b)
        self.assertEqual(len(differences['only_in_search']),1)
        self.assertEqual(len(differences['only_in_edition_summaries']),1)

    def test_title_drift_detected(self):
        a=parse_summary(summary(),'9765',self.end)
        row=search_row();row['title']='Another disposition'
        _,b=parse_search({'numResultSearch':1,'resultSearch':[row]},self.start,self.end,1)
        self.assertEqual(len(compare_indexes(a,b)['title_conflicts']),1)

    def test_source_date_format_not_guessed(self):
        for value in ['2026-10-04','04/10/26',None,'31/02/2026']:
            with self.assertRaises(ValueError):source_date(value)

    def test_same_day_official_annex_keeps_distinct_source_scope(self):
        records=parse_summary(with_annex(),'9765',self.end)
        self.assertEqual(len(records),2)
        annex=records[('456','2026-10-04')]
        self.assertEqual(annex['edition'],'9765A')
        self.assertEqual(annex['base_edition'],'9765')
        self.assertEqual(annex['edition_kind'],'ANNEX')

    def test_annex_with_different_publication_date_fails(self):
        data=with_annex();data['sumaris'][1]['dateDOGC']='03/10/2026'
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)

    def test_annex_download_link_must_identify_same_annex(self):
        data=with_annex();data['sumaris'][1]['linkDownloadDOGCPDF']=data['sumaris'][0]['linkDownloadDOGCPDF']
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)

    def test_unrelated_edition_cannot_be_disguised_as_annex(self):
        data=with_annex();data['sumaris'][1]['numDOGC']='9766A'
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)

    def test_annex_title_must_agree_with_scope(self):
        data=with_annex();data['sumaris'][1]['title']='Annex B'
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)

    def test_annex_without_principal_is_not_complete_edition(self):
        data=with_annex();data['sumaris'].pop(0)
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)

    def test_duplicate_edition_header_is_not_silently_accepted(self):
        data=summary();data['sumaris'].append(copy.deepcopy(data['sumaris'][0]))
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)

    def test_markup_without_readable_title_is_not_a_disposition(self):
        data=summary();data['sumaris'][0]['section'][0]['header'][0]['subheader'][0]['document'][0]['title']='<span></span>'
        with self.assertRaises(ValueError):parse_summary(data,'9765',self.end)


if __name__=='__main__':unittest.main()
