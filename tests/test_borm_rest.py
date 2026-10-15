import json
import unittest
from datetime import date
from unittest import mock

from app.collectors.borm import BORMCollector

SUMARIO = """<SumarioBoletinDTO><id>109856</id><numero>99</numero><ano>2025</ano><fechaPublicacion>02-05-2025</fechaPublicacion>
<anunciosBoletin><anunciosBoletin><id>835950</id><sumario>Extracto de la Orden por la que se aprueba la convocatoria de subvencion.</sumario><numero>1969</numero><ano>2025</ano><anunciante>Consejeria</anunciante><apartado>I. Comunidad Autonoma</apartado><categoriaCompleta>Ayudas</categoriaCompleta><fechaPublicacion>02-05-2025</fechaPublicacion></anunciosBoletin>
<anunciosBoletin><id>835990</id><sumario>Anuncio de informacion publica relativo a la solicitud de autorizacion administrativa previa de la instalacion solar fotovoltaica Ejemplo de 20 MW en el termino municipal de Lorca.</sumario><numero>2001</numero><ano>2025</ano><anunciante>Direccion General de Energia</anunciante><apartado>I. Comunidad Autonoma</apartado><categoriaCompleta>Energia</categoriaCompleta><fechaPublicacion>02-05-2025</fechaPublicacion></anunciosBoletin></anunciosBoletin></SumarioBoletinDTO>"""
# Shape verified live on 2026-10-15 (probe run 38716928046); texts here are abridged/test-only.

class Resp:
    def __init__(self, status, body, ctype):
        self.status_code, self.content, self.text, self.headers = status, body.encode(), body, {"content-type": ctype}
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)

class BORMRestTests(unittest.TestCase):
    def collector(self, responses):
        c = BORMCollector()
        c._rows = mock.Mock(return_value=[])
        c.audit.update(min_publication_date="2026-01-01", max_publication_date="2026-10-14")
        c.session.get = mock.Mock(side_effect=responses)
        c._write_audit = mock.Mock()
        return c

    def test_parse_summary_rejects_other_dates(self):
        items = BORMCollector.parse_rest_sumario(SUMARIO.encode(), date(2025, 5, 2))
        self.assertEqual([i["numero"] for i in items], ["1969", "2001"])
        with self.assertRaises(ValueError):
            BORMCollector.parse_rest_sumario(SUMARIO.encode(), date(2025, 5, 3))

    def test_historical_day_uses_rest_and_npe_identity(self):
        c = self.collector([Resp(200, SUMARIO, "application/xml;charset=UTF-8"),
                            Resp(200, "Texto integro: instalacion solar fotovoltaica Ejemplo de 20 MW en Lorca.", "text/plain")])
        events = c.collect_day(date(2025, 5, 2))
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual((e.external_id, e.url, e.technology), ("A-020525-2001", "https://www.borm.es/#/home/anuncio/02-05-2025/2001", "PV"))
        self.assertEqual(c.audit["daily_rest"][0]["announcements"], 2)

    def test_day_without_bulletin_is_recorded(self):
        c = self.collector([Resp(404, "boletin.alerts.danger.errorBusqueda", "text/plain")])
        self.assertEqual(c.collect_day(date(2025, 5, 4)), [])
        self.assertIs(c.audit["daily_rest"][0]["bulletin"], False)

    def test_other_http_failure_fails_closed(self):
        c = self.collector([Resp(500, "", "text/plain")])
        with self.assertRaises(RuntimeError):
            c.collect_day(date(2025, 5, 5))

if __name__ == "__main__":
    unittest.main()


class BORMRestScopeTests(unittest.TestCase):
    def test_rest_window_must_cover_every_day(self):
        from scripts.historical_month import validate_annual_index_scope
        full = {"min_publication_date": "2026-01-01", "max_publication_date": "2026-10-14",
                "daily_rest": [{"date": f"2025-02-{d:02d}", "http_status": 200} for d in range(1, 29)]}
        self.assertEqual(validate_annual_index_scope(full, date(2025, 2, 1), date(2025, 2, 28))["mode"], "DAILY_REST")
        gap = dict(full, daily_rest=full["daily_rest"][:-1])
        with self.assertRaises(ValueError):
            validate_annual_index_scope(gap, date(2025, 2, 1), date(2025, 2, 28))
