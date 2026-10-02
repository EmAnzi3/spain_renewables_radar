import unittest
from pathlib import Path

from app.collectors.boe import BOECollector
from app.collectors.boa import BOACollector
from app.parser import parse_event

class ParserTests(unittest.TestCase):
    def test_boe_summary_filters(self):
        html=Path("tests/fixtures/boe_summary_sample.html").read_text(encoding="utf-8")
        got=BOECollector.parse_summary_html(html)
        self.assertEqual({x["external_id"] for x in got},{"BOE-A-2026-12701","BOE-B-2026-20000"})

    def test_boe_api_parser_filters_procurement(self):
        payload={"data":{"sumario":{"diario":[{"seccion":[{"departamento":[{"item":[
            {"identificador":"BOE-B-2026-31656","titulo":"Instalación Fotovoltaica «Eclipse Solar» de 99,935 MW","url_html":"https://www.boe.es/diario_boe/txt.php?id=BOE-B-2026-31656"},
            {"identificador":"BOE-B-2026-31827","titulo":"Anuncio de formalización de contratos. Objeto: Instalación de paneles fotovoltaicos","url_html":"x"},
            {"identificador":"BOE-A-2026-99999","titulo":"Universidad pública","url_html":"x"}
        ]}]}]}]}}}
        got=BOECollector.parse_api_json(payload)
        self.assertEqual([x["external_id"] for x in got],["BOE-B-2026-31656"])

    def test_pv_auth(self):
        e=parse_event(
            source_code="BOE",external_id="BOE-A-2026-12701",publication_date="2026-06-11",
            title="Resolución",url="x",
            raw_text="Se otorga autorización administrativa previa para la instalación fotovoltaica «FV Guijo», de 91 MW, en la provincia de Cáceres."
        )
        self.assertEqual(e.technology,"PV")
        self.assertEqual(e.power_mw,91.0)
        self.assertEqual(e.project_name,"FV Guijo")
        self.assertEqual(e.province,"Cáceres")
        self.assertEqual(e.ccaa,"Extremadura")
        self.assertEqual(e.event_type,"PRIOR_AUTH")
        self.assertEqual(e.commercial_stage,"PERMITTING")

    def test_wind_public_info_with_promoter_and_code(self):
        title="Anuncio por el que se somete a Información Pública la solicitud de Declaración de Impacto Ambiental y Autorización Administrativa Previa de la instalación Parque Eólico «Vientos del Cid I» de 78 MW de potencia instalada, en la provincia de Burgos; promovida por la mercantil «Ener Epsilon, S.L.». código PEol-1024."
        e=parse_event(
            source_code="BOE",external_id="BOE-B-2026-31657",publication_date="2026-09-30",
            title=title,url="x",raw_text="Texto del expediente."
        )
        self.assertEqual(e.technology,"WIND")
        self.assertAlmostEqual(e.power_mw,78.0)
        self.assertEqual(e.project_name,"Vientos del Cid I")
        self.assertEqual(e.promoter,"Ener Epsilon, S.L")
        self.assertEqual(e.expediente,"PEol-1024")
        self.assertEqual(e.province,"Burgos")
        self.assertEqual(e.event_type,"PUBLIC_INFO")

    def test_title_beats_detail_noise(self):
        title="Instalación Fotovoltaica «Eclipse Solar» de 99,935 MW de potencia instalada, en la provincia de Burgos; promovida por la mercantil «SOLARIA Promoción y Desarrollo Fotovoltaico, S.L.U.». Código PFot-1229."
        raw="Texto de la web con referencias genéricas a almacenamiento y a 500 MW en menús o anexos no relacionados."
        e=parse_event(source_code="BOE",external_id="BOE-B-2026-31656",publication_date="2026-09-30",title=title,url="x",raw_text=raw)
        self.assertEqual(e.technology,"PV")
        self.assertAlmostEqual(e.power_mw,99.935)
        self.assertEqual(e.project_name,"Eclipse Solar")
        self.assertEqual(e.province,"Burgos")
        self.assertEqual(e.expediente,"PFot-1229")

    def test_ronda_location_promoter_expediente(self):
        title='Anuncio por el que se somete a información pública la solicitud de declaración de utilidad pública del proyecto de la planta solar fotovoltaica denominada "PSF Ronda 3" en el término municipal de Cañete la Real (Málaga), formulada por Cobra Concesiones, S.L. (expediente CG-870).'
        raw="Titular: COBRA CONCESIONES, S.L. Domicilio: Madrid."
        e=parse_event(source_code="BOE",external_id="BOE-B-2026-31787",publication_date="2026-10-01",title=title,url="x",raw_text=raw)
        self.assertEqual(e.technology,"PV")
        self.assertEqual(e.project_name,"PSF Ronda 3")
        self.assertEqual(e.province,"Málaga")
        self.assertEqual(e.ccaa,"Andalucía")
        self.assertEqual(e.promoter,"Cobra Concesiones, S.L")
        self.assertEqual(e.expediente,"CG-870")
        self.assertEqual(e.event_type,"PUBLIC_INFO")
        self.assertEqual(e.commercial_stage,"EARLY")

    def test_uniprovincial_ccaa_beats_promoter_address(self):
        title="Anuncio de la Dirección General de Industria del Gobierno de Cantabria sobre el parque eólico ALSA, de 18 MW."
        raw="Peticionario con domicilio en Oviedo (Asturias)."
        e=parse_event(source_code="BOE",external_id="BOE-X-CAN",publication_date="2026-10-02",title=title,url="x",raw_text=raw)
        self.assertEqual(e.province,"Cantabria")
        self.assertEqual(e.ccaa,"Cantabria")

    def test_ccaa_or_company_name_is_not_false_province(self):
        title="Anuncio de la Delegación del Gobierno en Castilla y León relativo a una instalación renovable."
        e=parse_event(source_code="BOE",external_id="BOE-X-1",publication_date="2026-10-02",title=title,url="x",raw_text='parque eólico "PE Demo" promovido por Desarrollos Eólicos Cuenca de Barberá, S.L.')
        self.assertIsNone(e.province)

    def test_expropriation_is_preconstruction(self):
        title='Anuncio por el que se convoca para el levantamiento de actas previas a la ocupación de bienes y derechos afectados por la infraestructura de evacuación de la instalación fotovoltaica "Elawan Olmedo I", de 50,064 MW de potencia instalada, en la provincia de Valladolid.'
        e=parse_event(
            source_code="BOE",external_id="BOE-B-2026-31854",publication_date="2026-10-02",
            title=title,url="x",raw_text="Texto del expediente."
        )
        self.assertEqual(e.technology,"PV")
        self.assertAlmostEqual(e.power_mw,50.064)
        self.assertEqual(e.event_type,"EXPROPRIATION")
        self.assertEqual(e.commercial_stage,"PRECONSTRUCTION")
        self.assertEqual(e.province,"Valladolid")

    def test_boa_elin_official_row(self):
        row={
            "DOCN":"007900001",
            "Titulo":'ANUNCIO del Servicio Provincial de Zaragoza, por el que se somete a información pública, la solicitud de autorización administrativa previa y de construcción, del proyecto parque eólico "PE Elin" de 30,5 MW de la empresa Energía Inagotable de Elin, SL, así como su estudio de impacto ambiental. Expediente G-Z-2025/024.',
            "Texto":"Ubicación: Plenas y Moyuela y Azuara (Zaragoza).",
            "UrlPdf":"https://www.boa.aragon.es/test.pdf"
        }
        e=BOACollector.event_from_row(__import__("datetime").date(2026,2,27),row)
        self.assertIsNotNone(e)
        self.assertEqual(e.technology,"WIND")
        self.assertAlmostEqual(e.power_mw,30.5)
        self.assertEqual(e.project_name,"PE Elin")
        self.assertEqual(e.promoter,"Energía Inagotable de Elin, SL")
        self.assertEqual(e.expediente,"G-Z-2025/024")
        self.assertEqual(e.province,"Zaragoza")
        self.assertEqual(e.ccaa,"Aragón")
        self.assertEqual(e.event_type,"PUBLIC_INFO")

    def test_boa_henar_dedicated_energy_proceeding(self):
        row={
            "DOCN":"007961421",
            "Titulo":"ANUNCIO del Servicio Provincial de Zaragoza, por el que se somete a información pública la solicitud de declaración de utilidad pública, de la instalación de producción de energía eléctrica PE Henar III. Expediente: G-EO-Z-313-2020 // DUP-Z-2021-0044.",
            "Texto":"Empresa beneficiaria: Energía Inagotable del Proyecto Henar III, SL. Dirección: calle Coso, 33, Zaragoza. Instalación: PE Henar III. Número aerogeneradores: 7. Ubicación: Cariñena y Tosos.",
            "UrlPdf":"https://www.boa.aragon.es/henar.pdf"
        }
        e=BOACollector.event_from_row(__import__("datetime").date(2026,9,30),row)
        self.assertIsNotNone(e)
        self.assertEqual(e.technology,"WIND")
        self.assertEqual(e.project_name,"PE Henar III")
        self.assertEqual(e.promoter,"Energía Inagotable del Proyecto Henar III, SL")
        self.assertEqual(e.province,"Zaragoza")
        self.assertEqual(e.event_type,"PUBLIC_INFO")

    def test_boa_excludes_co2_storage(self):
        row={
            "DOCN":"007961451",
            "Titulo":"RESOLUCIÓN por la que se publica la solicitud del permiso de investigación Caspe Mayals, para el almacenamiento geológico de dióxido de carbono, en la provincia de Zaragoza.",
            "Texto":"Proyecto de almacenamiento geológico de dióxido de carbono.",
            "UrlPdf":"x"
        }
        self.assertIsNone(BOACollector.event_from_row(__import__("datetime").date(2026,10,1),row))

    def test_boa_excludes_autoconsumo(self):
        row={
            "DOCN":"007961450",
            "Titulo":'RESOLUCIÓN sobre la autorización administrativa previa y de construcción del proyecto de instalación de parque fotovoltaico "Autoconsumo con excedentes Frutas La Espesa" de 880 kW, en Zaidín (Huesca).',
            "Texto":"Instalación fotovoltaica de autoconsumo.",
            "UrlPdf":"x"
        }
        self.assertIsNone(BOACollector.event_from_row(__import__("datetime").date(2026,10,1),row))

    def test_boa_excludes_generic_document_with_incidental_renewable_text(self):
        row={
            "DOCN":"007961480",
            "Titulo":"ACUERDOS de la Comisión Técnica de Calificación de Zaragoza, adoptados en sesión de 15 de septiembre de 2026.",
            "Texto":"Entre muchos expedientes se menciona una instalación fotovoltaica y un sistema de almacenamiento.",
            "UrlPdf":"x"
        }
        self.assertIsNone(BOACollector.event_from_row(__import__("datetime").date(2026,10,2),row))

    def test_boa_hybrid_storage_project_name(self):
        row={
            "DOCN":"007961487",
            "Titulo":"ANUNCIO del Servicio Provincial de Zaragoza, por el que se somete a información pública, la solicitud de autorización administrativa previa y de construcción, del proyecto del módulo de almacenamiento de la instalación híbrida Elawan Villanueva I de 20 MW de la empresa Elawan Fotovoltaica Villanueva SL. (Expediente G-Z-2026/037).",
            "Texto":"Planta almacenamiento: Módulo de almacenamiento de la instalación híbrida Elawan Villanueva I. Potencia instalada: 20,0 MW.",
            "UrlPdf":"https://www.boa.aragon.es/villanueva.pdf"
        }
        e=BOACollector.event_from_row(__import__("datetime").date(2026,10,2),row)
        self.assertIsNotNone(e)
        self.assertEqual(e.technology,"HYBRID")
        self.assertEqual(e.project_name,"Elawan Villanueva I")
        self.assertAlmostEqual(e.power_mw,20.0)
        self.assertEqual(e.promoter,"Elawan Fotovoltaica Villanueva SL")
        self.assertEqual(e.expediente,"G-Z-2026/037")
        self.assertEqual(e.province,"Zaragoza")

    def test_boa_multi_project_expropriation_notice(self):
        row={
            "DOCN":"007961484",
            "Titulo":"RESOLUCIÓN de 23 de septiembre de 2026, de la Directora del Servicio Provincial de Teruel, por la que se convoca al levantamiento de actas de pago de bienes y derechos afectados por varios expedientes.",
            "Texto":'Resoluciones relativas a la instalación "Planta fotovoltaica Elawan Escatrón I" ubicada en La Puebla de Híjar (Teruel). Expediente SIAGGE TE-AT0039/20. Resoluciones relativas a la instalación "Planta fotovoltaica Elawan Escatrón II" ubicada en La Puebla de Híjar (Teruel). Expediente SIAGGE TE-AT0040/20. Resoluciones relativas a la instalación "Planta fotovoltaica Elawan Escatrón III" ubicada en La Puebla de Híjar (Teruel). Expediente SIAGGE TE-AT0041/20.',
            "UrlPdf":"https://www.boa.aragon.es/elawan.pdf"
        }
        events=BOACollector.events_from_row(__import__("datetime").date(2026,10,2),row)
        self.assertEqual(len(events),3)
        self.assertEqual([e.project_name for e in events],["Elawan Escatrón I","Elawan Escatrón II","Elawan Escatrón III"])
        self.assertEqual([e.external_id for e in events],["007961484#1","007961484#2","007961484#3"])
        self.assertTrue(all(e.technology=="PV" for e in events))
        self.assertTrue(all(e.commercial_stage=="PRECONSTRUCTION" for e in events))
        self.assertTrue(all(e.province=="Teruel" for e in events))

if __name__=="__main__":
    unittest.main()
