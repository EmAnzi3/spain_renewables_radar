import tempfile
import unittest
from pathlib import Path

from app.db import connect
from app.enrichment.miteco_registry import (
    canonical_ccaa,
    normalize_name,
    save_registry_snapshot,
    exact_project_matches,
)

class MitecoRegistryTests(unittest.TestCase):
    def test_ccaa_normalization(self):
        self.assertEqual(canonical_ccaa("Castilla y Leon"),"Castilla y León")
        self.assertEqual(canonical_ccaa("Region de Murcia"),"Murcia")
        self.assertEqual(canonical_ccaa("Cataluna"),"Catalunya")

    def test_exact_name_and_ccaa_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/"test.sqlite"))
            conn.execute(
                """INSERT INTO projects
                (project_key,project_name,technology,power_mw,promoter,expediente,province,ccaa,
                 commercial_stage,first_seen,last_seen,latest_event_type,latest_source_code,latest_source_url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "p1","Parque Eólico Ábrego","WIND",49.5,None,None,"Burgos","Castilla y León",
                    "AUTHORIZED","2026-01-01","2026-01-01","CONSTRUCTION_AUTH","BOE","x"
                ),
            )
            conn.commit()
            records=[{
                "autoid":"123",
                "installation_id":"456",
                "regime":"ESPECIAL",
                "installation_name":"Parque Eólico Ábrego",
                "normalized_name":normalize_name("Parque Eólico Ábrego"),
                "ccaa":"Castilla y León",
            }]
            save_registry_snapshot(conn,"2026-10-03","source",records)
            matches=exact_project_matches(conn,"2026-10-03")
            self.assertEqual(len(matches),1)
            self.assertEqual(matches[0]["project_key"],"p1")
            self.assertEqual(matches[0]["autoid"],"123")

    def test_same_name_wrong_ccaa_does_not_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/"test.sqlite"))
            conn.execute(
                """INSERT INTO projects
                (project_key,project_name,technology,power_mw,province,ccaa,
                 commercial_stage,first_seen,last_seen,latest_event_type)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                ("p1","Sol Uno","PV",20.0,"Toledo","Castilla-La Mancha","EARLY","2026-01-01","2026-01-01","PUBLIC_INFO"),
            )
            conn.commit()
            records=[{
                "autoid":"1","installation_id":None,"regime":"ESPECIAL",
                "installation_name":"Sol Uno","normalized_name":normalize_name("Sol Uno"),"ccaa":"Andalucía",
            }]
            save_registry_snapshot(conn,"2026-10-03","source",records)
            self.assertEqual(exact_project_matches(conn,"2026-10-03"),[])

if __name__=="__main__":
    unittest.main()
