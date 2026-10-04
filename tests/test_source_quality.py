"""No reporting/enrichment step may resolve source conflicts silently."""
import json
import tempfile
import unittest
from pathlib import Path
from app.collectors.gva_public import GVAPublicCollector,event_from_record
from app.db import connect
from app.lifecycle import commercial_stage
from app.reporting import write_quality_issues,build_commercial_rows
from app.source_quality import regional_evidence_by_project
from app.store import save_event

class RegionalQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.conn=connect(str(Path(self.tmp.name)/'test.sqlite'));self.addCleanup(self.conn.close)
        self.record={'external_id':'415584926','publication_date':'2026-09-29',
            'url':'https://mediambient.gva.es/es/web/energia/informacion-publica?_pub_assetEntryId=415584926',
            'title':'Resolución por la que se acepta el desistimiento de central fotovoltaica denominada "PSFV PICASSENT", de 4 MW de potencia. Expediente ATALFE/2023/3/46.',
            'categories':['Valencia'],
            'legal_documents':[{'url':'https://mediambient.gva.es/Resolucion.pdf','text':'Resolución central fotovoltaica denominada "PSFV PICASSENT", de 4,824 MW de potencia instalada. ANTECEDENTES','sha256':'fixture'}]}
        event=event_from_record(self.record);save_event(self.conn,event)
        self.collector=GVAPublicCollector(out_dir=Path(self.tmp.name)/'source')
        self.collector.records[self.record['external_id']]=self.record

    def fingerprint(self):
        return {table:[tuple(r) for r in self.conn.execute('SELECT * FROM '+table)] for table in ('projects','events')}

    def test_conflict_flows_to_main_quality_report_and_dashboard_without_mutation(self):
        before=self.fingerprint();self.collector.persist_metadata(self.conn)
        issues,csv_path,html_path=write_quality_issues(self.conn,Path(self.tmp.name)/'reports')
        conflict=[i for i in issues if i['code']=='SOURCE_POWER_DISAGREEMENT']
        self.assertEqual(len(conflict),1);self.assertEqual(conflict[0]['severity'],'WARN')
        self.assertEqual(conflict[0]['source_url'],self.record['url'])
        self.assertIn('4.824',csv_path.read_text(encoding='utf-8-sig'))
        self.assertIn('SOURCE_POWER_DISAGREEMENT',html_path.read_text())
        project=build_commercial_rows(self.conn)[0]
        self.assertIsNone(project['power_mw']);self.assertEqual(project['commercial_stage'],'BLOCKED')
        self.assertEqual(project['commercial_score'],0)
        self.assertEqual(project['regional_source_evidence'][0]['external_id'],self.record['external_id'])
        self.assertEqual(self.fingerprint(),before)

    def test_metadata_replay_is_idempotent(self):
        self.collector.persist_metadata(self.conn);self.collector.persist_metadata(self.conn)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM regional_public_metadata').fetchone()[0],1)
        self.assertEqual(len(regional_evidence_by_project(self.conn)),1)

    def test_provenance_mismatch_is_not_silently_exported(self):
        self.collector.persist_metadata(self.conn)
        self.conn.execute("UPDATE regional_public_metadata SET web_publication_date='2000-01-01'")
        with self.assertRaises(ValueError):regional_evidence_by_project(self.conn)

    def test_metadata_cannot_be_attached_to_another_project(self):
        self.collector.persist_metadata(self.conn)
        self.conn.execute("UPDATE regional_public_metadata SET project_key='wrong-project'")
        with self.assertRaises(ValueError):regional_evidence_by_project(self.conn)

    def test_metadata_without_its_event_is_not_silently_ignored(self):
        self.collector.persist_metadata(self.conn)
        self.conn.execute("UPDATE regional_public_metadata SET external_id='unknown-event'")
        with self.assertRaises(ValueError):regional_evidence_by_project(self.conn)

    def test_old_databases_without_regional_table_stay_supported(self):
        self.assertEqual(regional_evidence_by_project(self.conn),{})
        self.assertNotIn('regional_source_evidence',build_commercial_rows(self.conn)[0])

    def test_closed_procedure_does_not_become_an_early_opportunity(self):
        self.assertEqual(commercial_stage('PROCEDURE_ENDED'),'BLOCKED')

if __name__=='__main__':unittest.main()
