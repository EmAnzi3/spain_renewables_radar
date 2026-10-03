import tempfile
import unittest
from pathlib import Path

from app.db import connect
from app.enrichment.epc_bop import (
    extract_epc_evidence,
    project_epc_summary,
    refresh_epc_evidence_from_events,
)


class EPCBoPTests(unittest.TestCase):
    def test_explicit_epc_is_confirmed(self):
        got=extract_epc_evidence(
            "El contrato EPC ha sido adjudicado a Cobra Instalaciones y Servicios, S.A."
        )
        self.assertEqual(len(got),1)
        self.assertEqual(got[0].status,"EPC_CONFIRMED")
        self.assertEqual(got[0].role,"EPC")
        self.assertIn("Cobra",got[0].contractor_name)

    def test_explicit_constructor_is_candidate(self):
        got=extract_epc_evidence(
            "Empresa constructora: Demo Engineering, S.L. Domicilio: Madrid."
        )
        self.assertEqual(len(got),1)
        self.assertEqual(got[0].status,"EPC_CANDIDATE")
        self.assertEqual(got[0].role,"CONSTRUCTION")

    def test_promoter_alone_is_not_epc(self):
        got=extract_epc_evidence(
            "Promovida por la mercantil Developer Solar, S.L. para una planta fotovoltaica."
        )
        self.assertEqual(got,[])

    def test_refresh_keeps_epc_separate_from_project_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/"test.sqlite"))
            conn.execute(
                """INSERT INTO projects
                (project_key,project_name,technology,power_mw,promoter,expediente,province,ccaa,
                 commercial_stage,first_seen,last_seen,latest_event_type,latest_source_code,latest_source_url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("p1","Demo PV","PV",50.0,"Developer Solar, S.L.",None,"Madrid","Madrid",
                 "AUTHORIZED","2026-10-01","2026-10-01","CONSTRUCTION_AUTH","BOE","https://example.invalid"),
            )
            text="Resolución del proyecto. Contratista EPC: Demo Engineering, S.L."
            conn.execute(
                """INSERT INTO events
                (source_code,external_id,publication_date,title,url,raw_text,project_key,event_type,
                 commercial_stage,technology,power_mw,promoter,expediente,province,ccaa)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("BOE","X1","2026-10-01","Resolución","https://example.invalid",text,
                 "p1","CONSTRUCTION_AUTH","AUTHORIZED","PV",50.0,"Developer Solar, S.L.",
                 None,"Madrid","Madrid"),
            )
            conn.commit()
            result=refresh_epc_evidence_from_events(conn)
            self.assertEqual(result["projects_with_evidence"],1)
            summary=project_epc_summary(conn,"p1")
            self.assertEqual(summary["status"],"EPC_CONFIRMED")
            self.assertEqual(summary["contractors"],["Demo Engineering, S.L."])
            promoter=conn.execute("SELECT promoter FROM projects WHERE project_key='p1'").fetchone()["promoter"]
            self.assertEqual(promoter,"Developer Solar, S.L.")


if __name__=="__main__":
    unittest.main()
