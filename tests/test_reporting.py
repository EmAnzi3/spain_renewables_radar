import tempfile
import unittest
from pathlib import Path

from app.db import connect
from app.reporting import write_quality_issues


class ReportingQualityTests(unittest.TestCase):
    def _insert_project_and_event(self, conn, project_key, title):
        conn.execute(
            """INSERT INTO projects
            (project_key,project_name,technology,power_mw,promoter,expediente,province,ccaa,
             commercial_stage,first_seen,last_seen,latest_event_type,latest_source_code,latest_source_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                project_key,None,"PV",None,"Andramari FV S.L.",None,"Burgos","Castilla y León",
                "EARLY","2026-09-08","2026-09-08","OTHER","BOCYL","https://example.invalid/source",
            ),
        )
        conn.execute(
            """INSERT INTO events
            (source_code,external_id,publication_date,title,url,raw_text,project_key,event_type,
             commercial_stage,technology,power_mw,promoter,expediente,province,ccaa)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "BOCYL",f"E-{project_key}","2026-09-08",title,"https://example.invalid/source",
                title,project_key,"OTHER","EARLY","PV",None,"Andramari FV S.L.",None,"Burgos","Castilla y León",
            ),
        )
        conn.commit()

    def test_source_unnamed_multi_project_is_warn_not_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/"test.sqlite"))
            self._insert_project_and_event(
                conn,
                "multi",
                "CORRECCIÓN de errores relativa a la ejecución de dos parques fotovoltaicos "
                "en Miranda de Ebro (Burgos). Exptes.: 2025/3197H y 2026/6997H.",
            )
            issues,_,_=write_quality_issues(conn,out_dir=Path(tmp)/"reports")
            codes={(x["severity"],x["code"]) for x in issues}
            self.assertIn(("WARN","SOURCE_UNNAMED_MULTI_PROJECT"),codes)
            self.assertNotIn(("ERROR","MISSING_PROJECT_NAME"),codes)

    def test_ordinary_missing_project_name_remains_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/"test.sqlite"))
            self._insert_project_and_event(
                conn,
                "single",
                "Información pública de una instalación fotovoltaica de 20 MW en Burgos.",
            )
            issues,_,_=write_quality_issues(conn,out_dir=Path(tmp)/"reports")
            codes={(x["severity"],x["code"]) for x in issues}
            self.assertIn(("ERROR","MISSING_PROJECT_NAME"),codes)


if __name__=="__main__":
    unittest.main()
