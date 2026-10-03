import tempfile
import unittest
from pathlib import Path

from app.db import connect
from app.enrichment.ine_municipalities import (
    Municipality,
    enrich_missing_project_geography,
    municipalities_in_text,
    parse_ine_municipalities,
)


class GeoEnrichmentTests(unittest.TestCase):
    def test_parse_ine_catalog_uses_official_province_code(self):
        got = parse_ine_municipalities([
            {"Nombre": "Azuara", "Codigo": "50039"},
            {"Nombre": "Tosos", "Codigo": "50264"},
        ])
        self.assertEqual([(x.name, x.province, x.ccaa) for x in got], [
            ("Azuara", "Zaragoza", "Aragón"),
            ("Tosos", "Zaragoza", "Aragón"),
        ])

    def test_location_anchor_resolves_same_province(self):
        catalog = [
            Municipality("Azuara", "50039", "Zaragoza", "Aragón"),
            Municipality("Tosos", "50264", "Zaragoza", "Aragón"),
        ]
        got = municipalities_in_text(
            "Ubicación: Azuara y Tosos. Domicilio del promotor: Madrid.",
            catalog,
            "Aragón",
        )
        self.assertEqual([x.name for x in got], ["Azuara", "Tosos"])

    def _insert(self, conn, key, ccaa, text):
        conn.execute(
            """INSERT INTO projects
            (project_key,project_name,technology,power_mw,promoter,expediente,province,ccaa,
             commercial_stage,first_seen,last_seen,latest_event_type,latest_source_code,latest_source_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key,key,"PV",20.0,None,None,None,ccaa,"EARLY","2026-10-01","2026-10-01",
             "PUBLIC_INFO","BOE","https://example.invalid"),
        )
        conn.execute(
            """INSERT INTO events
            (source_code,external_id,publication_date,title,url,raw_text,project_key,event_type,
             commercial_stage,technology,power_mw,promoter,expediente,province,ccaa)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("BOE",key,"2026-10-01","Información pública","https://example.invalid",
             text,key,"PUBLIC_INFO","EARLY","PV",20.0,None,None,None,ccaa),
        )
        conn.commit()

    def test_enrichment_updates_only_missing_project_province_and_keeps_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/"test.sqlite"))
            self._insert(conn,"p1","Aragón","Ubicación: Azuara y Tosos.")
            catalog=[
                Municipality("Azuara","50039","Zaragoza","Aragón"),
                Municipality("Tosos","50264","Zaragoza","Aragón"),
            ]
            result=enrich_missing_project_geography(conn,catalog)
            self.assertEqual(result["resolved"],1)
            row=conn.execute("SELECT province,ccaa FROM projects WHERE project_key='p1'").fetchone()
            self.assertEqual((row["province"],row["ccaa"]),("Zaragoza","Aragón"))
            audit=conn.execute("SELECT status,source_code FROM project_geo_enrichment WHERE project_key='p1'").fetchone()
            self.assertEqual((audit["status"],audit["source_code"]),("RESOLVED","INE_MUNICIPALITIES"))

    def test_multi_province_is_explicit_and_not_forced(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=connect(str(Path(tmp)/"test.sqlite"))
            self._insert(conn,"p2","Castilla y León","Términos municipales de Burgos y León.")
            catalog=[
                Municipality("Burgos","09059","Burgos","Castilla y León"),
                Municipality("León","24089","León","Castilla y León"),
            ]
            result=enrich_missing_project_geography(conn,catalog)
            self.assertEqual(result["multi_province"],1)
            self.assertIsNone(conn.execute("SELECT province FROM projects WHERE project_key='p2'").fetchone()["province"])
            audit=conn.execute("SELECT status,provinces_json FROM project_geo_enrichment WHERE project_key='p2'").fetchone()
            self.assertEqual(audit["status"],"MULTI_PROVINCE")
            self.assertIn("Burgos",audit["provinces_json"])
            self.assertIn("León",audit["provinces_json"])


if __name__=="__main__":
    unittest.main()
