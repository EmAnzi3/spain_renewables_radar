import unittest

from app.collectors.sabia import (
    events_from_detail,
    parse_detail_html,
    parse_search_html,
)


SEARCH_HTML = """
<html><body>
<table id="tablaResultados">
<tr><th>Código</th><th>Título</th><th>Estado</th></tr>
<tr><td>20260236</td><td><a href="javascript:enviar('proy_estado_tramitacion')">
PRÓRROGA DE LA DIA DEL PROYECTO PARQUE FOTOVOLTAICO MUEL DE 200 MWP, Y SU INFRAESTRUCTURA DE EVACUACIÓN, TT.MM. DE MUEL, ZARAGOZA, LA MUELA Y MARÍA DE HUERVA (ZARAGOZA).
</a></td><td>CONSULTAS PREVIAS</td></tr>
</table>
</body></html>
"""

MUEL_DETAIL = """
<html><body>
Datos del proyecto de Evaluación Ambiental
Código de Evaluación Ambiental: 20260236
Código para el Órgano Sustantivo: PFOT-150
Título del proyecto: PRÓRROGA DE LA DIA DEL PROYECTO PARQUE FOTOVOLTAICO MUEL DE 200 MWP, Y SU INFRAESTRUCTURA DE EVACUACIÓN, TT.MM. DE MUEL, ZARAGOZA, LA MUELA Y MARÍA DE HUERVA (ZARAGOZA).
Órgano Sustantivo: D.G. DE POLITICA ENERGETICA Y MINAS MINISTERIO PARA LA TRANSICION ECOLOGICA Y EL RETO DEMOGRAFICO
Promotor: ENEL GREEN POWER ESPAÑA, S.L. NIF: B61234613
Tipo de proyecto: FOTOVOLTAICOS
Legislación aplicable: 21/2013
Legislación estatal de EIA:
Ámbito de aplicación geográfica:
Comunidad autónoma: Aragón
Provincia: Zaragoza
Municipio: Maria de Huerva
Página Web:
Medio de publicación:
Fecha autorización:
Fecha publicación autorización:
Fecha inicio ejecución proyecto:
Fechas relevantes
Estado de tramitación: CONSULTAS PREVIAS
Fecha de entrada: 25/08/2026
Fecha inicio de consultas: 18/09/2026
Fecha de resolución:
Sentido de la resolución:
Documentación
</body></html>
"""

CIUDAD_RODRIGO_DETAIL = """
<html><body>
Datos del proyecto de Evaluación Ambiental
Código de Evaluación Ambiental: 20260181
Código para el Órgano Sustantivo: PFOT-120-ALM
Título del proyecto: MÓDULO DE ALMACENAMIENTO BAT CIUDAD RODRIGO, PARA SU HIBRIDACIÓN CON EL PARQUE FOTOVOLTAICO CIUDAD RODRIGO, Y PARA UNA PARTE DE SU INFRAESTRUCTURA DE EVACUACIÓN, EN LA PROVINCIA DE SALAMANCA.
Órgano Sustantivo: D.G. DE POLITICA ENERGETICA Y MINAS
Promotor: DESARROLLOS RENOVABLES CIUDAD RODRIGO S.L.U. CIF: B19800267
Tipo de proyecto: HIBRIDOS ENERGIAS RENOVABLES
Legislación aplicable: 21/2013
Legislación estatal de EIA:
Ámbito de aplicación geográfica:
Comunidad autónoma: Castilla y León
Provincia: Salamanca
Municipio:
Página Web:
Medio de publicación:
Fecha autorización:
Fecha publicación autorización:
Fecha inicio ejecución proyecto:
Fechas relevantes
Estado de tramitación: CONSULTAS PREVIAS
Fecha de entrada: 23/06/2026
Fecha inicio de consultas: 01/10/2026
Fecha de resolución:
Fecha de publicación en el BOE:
Sentido de la resolución:
Documentación
</body></html>
"""

CLAVELLINAS_DETAIL = """
<html><body>
Datos del proyecto de Evaluación Ambiental
Código de Evaluación Ambiental: 20260211
Código para el Órgano Sustantivo: PFOT-ALM-224
Título del proyecto: HÍBRIDO “CLAVELLINAS”, COMPUESTO POR UNA PLANTA FOTOVOLTAICA DE 145,26 MW Y ALMACENAMIENTO POR BATERÍAS DE 10,00 MWH, Y SU INFRAESTRUCTURA DE EVACUACIÓN, UBICADO EN LAS PROVINCIAS DE ALBACETE Y CIUDAD REAL.
Órgano Sustantivo: D.G. DE POLITICA ENERGETICA Y MINAS
Promotor: ORSTED ONSHORE SPAIN II, S.L. CIF: B72487028
Tipo de proyecto: HIBRIDOS ENERGIAS RENOVABLES
Legislación aplicable: 21/2013
Legislación estatal de EIA:
Ámbito de aplicación geográfica:
Comunidad autónoma: Castilla-La Mancha
Provincia: Albacete
Municipio:
Página Web:
Medio de publicación:
Fecha autorización:
Fecha publicación autorización:
Fecha inicio ejecución proyecto:
Fechas relevantes
Estado de tramitación: CONSULTAS PREVIAS
Fecha de entrada: 21/07/2026
Fecha inicio de consultas: 28/09/2026
Fecha del documento de alcance:
Sentido de la resolución:
Documentación
</body></html>
"""


class SABIACollectorTests(unittest.TestCase):
    def test_search_results_extract_stable_code(self):
        rows=parse_search_html(SEARCH_HTML,source_type="FTV")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["code"],"20260236")
        self.assertEqual(rows[0]["state"],"CONSULTAS PREVIAS")
        self.assertEqual(rows[0]["source_type"],"FTV")

    def test_muel_detail_and_dated_events(self):
        detail=parse_detail_html(MUEL_DETAIL)
        self.assertEqual(detail["environmental_code"],"20260236")
        self.assertEqual(detail["substantive_code"],"PFOT-150")
        self.assertEqual(detail["promoter"],"ENEL GREEN POWER ESPAÑA, S.L.")
        self.assertEqual(detail["province"],"Zaragoza")
        self.assertEqual(detail["entry_date"],"2026-08-25")
        self.assertEqual(detail["consultation_start"],"2026-09-18")

        events=events_from_detail(detail,"FTV","https://example.invalid/20260236")
        self.assertEqual(len(events),2)
        by_id={e.external_id:e for e in events}
        entry=by_id["20260236:ENTRY"]
        consult=by_id["20260236:CONSULT"]
        self.assertEqual(entry.event_type,"OTHER")
        self.assertEqual(entry.commercial_stage,"EARLY")
        self.assertEqual(consult.event_type,"PUBLIC_INFO")
        self.assertEqual(consult.publication_date,"2026-09-18")
        self.assertEqual(consult.technology,"PV")
        self.assertAlmostEqual(consult.power_mw,200.0)
        self.assertEqual(consult.project_name,"MUEL")
        self.assertEqual(consult.promoter,"ENEL GREEN POWER ESPAÑA, S.L.")
        self.assertEqual(consult.expediente,"PFOT-150")
        self.assertEqual(consult.province,"Zaragoza")
        self.assertEqual(consult.ccaa,"Aragón")

    def test_storage_hybrid_official_type(self):
        detail=parse_detail_html(CIUDAD_RODRIGO_DETAIL)
        events=events_from_detail(detail,"HIB","https://example.invalid/20260181")
        consult=[e for e in events if e.external_id.endswith(":CONSULT")][0]
        self.assertEqual(consult.technology,"HYBRID")
        self.assertEqual(consult.expediente,"PFOT-120-ALM")
        self.assertEqual(consult.province,"Salamanca")
        self.assertEqual(consult.ccaa,"Castilla y León")
        self.assertEqual(consult.promoter,"DESARROLLOS RENOVABLES CIUDAD RODRIGO S.L.U.")

    def test_explicit_multi_province_is_not_forced(self):
        detail=parse_detail_html(CLAVELLINAS_DETAIL)
        events=events_from_detail(detail,"HIB","https://example.invalid/20260211")
        consult=[e for e in events if e.external_id.endswith(":CONSULT")][0]
        self.assertEqual(consult.technology,"HYBRID")
        self.assertIsNone(consult.province)
        self.assertEqual(consult.ccaa,"Castilla-La Mancha")
        self.assertEqual(consult.project_name,"CLAVELLINAS")
        self.assertAlmostEqual(consult.power_mw,145.26)

    def test_application_error_is_structural_failure(self):
        bad="<html><body>Se ha producido un error. Por favor, vuelva a acceder a la aplicación.</body></html>"
        with self.assertRaises(RuntimeError):
            parse_search_html(bad,"FTV")


if __name__=="__main__":
    unittest.main()
