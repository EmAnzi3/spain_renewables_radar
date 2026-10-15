import json
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from app.collectors.dogv import DOGVCollector

FIX = Path(__file__).parent / "fixtures" / "dogv"
def load(name): return json.loads((FIX / name).read_text(encoding="utf-8"))


class DOGVTests(unittest.TestCase):
    def test_summary_keeps_only_same_day_energy_and_excludes_grants(self):
        items = DOGVCollector.summary_candidates(load("summary_2025_10_01.json"), date(2025, 10, 1))
        self.assertEqual([i["id"] for i in items], ["900001"])
        self.assertEqual(items[0]["url_pdf"], "https://dogv.gva.es/datos/2025/10/01/pdf/2025_99001_es.pdf")

    def test_malformed_summary_fails_closed(self):
        with self.assertRaises(ValueError):
            DOGVCollector.summary_candidates({"cabecera": {}}, date(2025, 10, 1))

    def test_external_id_prefers_official_cve(self):
        self.assertEqual(DOGVCollector.external_id({"id": "1", "codigo": "2025/99001"}, {"cve": "DOGV-2025-99001"}), "DOGV-2025-99001")
        self.assertEqual(DOGVCollector.external_id({"id": "1", "codigo": "2025/99001"}, {"cve": "None"}), "DOGV-2025-99001")

    def _collector(self):
        c = DOGVCollector()
        def fake(path, params):
            if path == "/dogv/calendar": return load("calendar_2025_10.json")
            if path == "/dogv": return load("summary_2025_10_01.json")
            if path == "/disposicion/900001": return load("detail_900001.json")
            raise AssertionError(path)
        c._json = mock.Mock(side_effect=fake)
        return c

    def test_collect_day_parses_event_with_valencian_scope(self):
        events = self._collector().collect_day(date(2025, 10, 1))
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual((e.source_code, e.external_id, e.technology, e.power_mw), ("DOGV", "DOGV-2025-99001", "PV", 49.9))
        self.assertEqual((e.province, e.ccaa), ("Valencia", "Comunitat Valenciana"))
        self.assertTrue(e.promoter.startswith("Ejemplo Solar, SL"))

    def test_day_without_bulletin_is_empty_not_error(self):
        c = self._collector()
        self.assertEqual(c.collect_day(date(2025, 10, 4)), [])
        self.assertEqual([call.args[0] for call in c._json.call_args_list], ["/dogv/calendar"])


if __name__ == "__main__":
    unittest.main()


class DOGVIdentityTests(unittest.TestCase):
    """Titles verbatim from DOGV-2026-31952, DOGV-2026-29807, DOGV-2026-31305 (summaries 13-14/10/2026)."""
    def ev(self, title, body=""):
        from app.parser import parse_event
        e = parse_event(source_code="DOGV", external_id="X", publication_date="2026-10-13", title=title, url="u", raw_text=body + "\nComunitat Valenciana")
        return DOGVCollector.refine_identity(e, title, body)

    def test_named_plant_and_atalfe_from_title(self):
        e = self.ev("CORRECCIÓN DE ERRORES de la Resolución de 25 de noviembre de 2025, del Servicio Territorial de Industria, Energía y Minas de Alicante, por la que se otorga a Fotovoltaica El Glaciar, SL, autorización administrativa previa, autorización administrativa de construcción y aprobación del plan de desmantelamiento y restauración del terreno y el entorno afectado para una central fotovoltaica, ubicada en Elche (Alicante), de potencia instalada 9,9 MW, denominada FV Asprillas I, incluida su infraestructura de evacuación. ATALFE/2021/24.")
        self.assertEqual((e.project_name, e.expediente, e.power_mw), ("FV Asprillas I", "ATALFE/2021/24", 9.9))

    def test_title_name_replaces_body_fragment(self):
        e = self.ev("RESOLUCIÓN de 1 de septiembre de 2026, del Servicio Territorial de Industria, Energía y Minas de Valencia, por la que se deniega a Energía, Innovación y Desarrollo Fotovoltaico, SA, la autorización administrativa previa y autorización administrativa de construcción correspondientes a la central solar generadora fotovoltaica denominada FV Andilla y su infraestructura de evacuación, situada en Andilla. Expediente ATALFE/2022/3/46.",
                    "siguiente:\n– Solicitante: Energía, Innovación y Desarrollo Fotovoltaico, SA")
        self.assertEqual(e.project_name, "FV Andilla")
        self.assertEqual(e.expediente.upper(), "ATALFE/2022/3/46")

    def test_title_without_denominada_keeps_parser_name(self):
        t = "ANUNCIO por el que se someten a información pública las solicitudes de autorización administrativa previa, autorización administrativa de construcción y ocupación de vías pecuarias, correspondientes a central fotovoltaica hibridada Instalación Fotovoltaica Espioca Solar y BESS Espioca Power, y su infraestructura de evacuación, a ubicar en el término municipal Picassent. ATALFE/2023/63/46."
        e = self.ev(t)
        self.assertTrue(e.project_name)
        self.assertEqual(e.expediente, "ATALFE/2023/63/46")
