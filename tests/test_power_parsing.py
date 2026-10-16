"""Plant capacity extraction on wording from official acts (DOE, DOCM, BOCYL, BOE, BOA, DOGV)."""
import tempfile,unittest
from pathlib import Path
from app.db import connect
from app.parser import ParsedEvent,extract_power_mw,parse_event
from app.store import save_event
from app.power_repair import repair_power

CASES=[
 ("Instalación solar fotovoltaica de 4.990 kW de potencia instalada, compuesta por 5 inversores. Se limitará electrónicamente a 0,99 MW para impedir que la potencia activa inyectada a la red supere los 4.990 kW",4.99),
 ("instalación solar fotovoltaica de 1.000 kW de potencia instalada, compuesta por 2 inversores de 500 kW de potencia cada uno",1.0),
 ("instalación solar fotovoltaica de 4.900 kW de potencia instalada, compuesta por 14 inversores de 350 kW cada uno",4.9),
 ("Formado por 6 aerogeneradores, modelo Siemens Gamesa SG170-6,6 MW o similar, con lo que la potencia total del parque será de 39.60 MW.",39.6),
 ("Potencia unitaria de los aerogeneradores  6,5 MW. Potencia total a instalar, 19,5 MW.",19.5),
 ("Instalación de 5 de 6000 kW de potencia nominal cada uno. Potencia total instalada de 30 MW, y capacidad de acceso de 25 MW",30.0),
 ("módulo de almacenamiento Aitana, de 21,69 MW, y su hibridación con la instalación solar fotovoltaica existente «FV Aitana», de 49,11 MW de potencia instalada",21.69),
 ('parque fotovoltaico "FV Usón I" de 751,26 kWp/500 kW, promovida por Usón e Hijos',0.5),
 ("Potencia de acceso  0,499 MW Potencia instalada  0,500 MW Potencia pico módulos  1,022 MW",0.5),
 ("una potencia pico de 23.063 kWp y una potencia nominal de 17.200 KWn",17.2),
 ("potencia máxima total de los módulos fotovoltaicos (pico): 3,1752 MW, potencia nominal de los inversores: 2,5 MW y capacidad de acceso concedida de 2,5 MW",2.5),
 ("instalación solar fotovoltaica “Cruz de los Caminos” 47,554 MWinst/43,500 MW acceso",47.554),
 ("lo que totaliza una potencia pico de 1.299 MWp. Un centro de inversores (9 inversores x 125 kW/inversor) de 1,125 MWn de potencia. Por lo tanto, la potencia nominal de la planta será de 1.125 MWn",1.125),
 ("infraestructuras de evacuación de la PS Volans Solar 1, de 49,97 MWp, del término",49.97),
 ("plantación fotovoltaica con conexión a red 30 MW/39 MWp, denominada",30.0),
]
NONE=["módulos de almacenamiento Los Naipes, Naipes II y Encinar I, de 21,45 MW cada uno",
      "siendo que cada uno de ellos tiene menos de 50 MW, es la Secretaría",
      "15 Ud. Inversor tipo string de 350 kW. 1 Ud. Centro de transformación",
      "Domínguez 505 634 49149A505006340000KW Muelas del Pan",
      "lo que totaliza una potencia nominal de 15\u202f785 MW. La potencia pico de la planta será de 16 5 MWp",
      "lo que totaliza una potencia nominal de 15\x92785 MW."]

class ExtractionTests(unittest.TestCase):
    def test_plant_capacity_from_official_wording(self):
        for text,mw in CASES:
            with self.subTest(text=text[:50]):self.assertAlmostEqual(extract_power_mw(text),mw)
    def test_unit_threshold_and_inverter_values_are_not_plant_capacity(self):
        for text in NONE:
            with self.subTest(text=text[:50]):self.assertIsNone(extract_power_mw(text))

class RepairTests(unittest.TestCase):
    def test_stored_wrong_values_are_reread_audited_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            c=connect(str(Path(td)/'db.sqlite'))
            raw=CASES[0][0]
            e=ParsedEvent(source_code='DOE',external_id='DOE-2024063260',publication_date='2024-10-11',title='Energía solar.- Resolución FV El Polvorín',
                url='https://doe.juntaex.es/x',raw_text=raw,technology='PV',power_mw=0.99,project_name='El Polvorín',promoter=None,
                expediente='GE-M/06/22',province='Badajoz',ccaa='Extremadura',event_type='PRIOR_AUTH',commercial_stage='PERMITTING',project_key='k')
            save_event(c,e)
            before=c.execute('SELECT title,raw_text,url,publication_date,event_type FROM events').fetchone()[:]
            self.assertEqual(repair_power(c)['events_changed'],1)
            self.assertAlmostEqual(c.execute('SELECT power_mw FROM projects').fetchone()[0],4.99)
            self.assertEqual(c.execute('SELECT title,raw_text,url,publication_date,event_type FROM events').fetchone()[:],before)
            self.assertAlmostEqual(c.execute('SELECT previous_power_mw FROM power_reparse_repairs').fetchone()[0],0.99)
            self.assertEqual(repair_power(c)['events_changed'],0);c.close()
    def test_sources_with_their_own_rules_are_not_touched(self):
        with tempfile.TemporaryDirectory() as td:
            c=connect(str(Path(td)/'db.sqlite'))
            save_event(c,ParsedEvent(source_code='DOGC',external_id='1',publication_date='2024-10-11',title='t',url='u',raw_text=CASES[0][0],
                technology='PV',power_mw=0.99,project_name='X',promoter=None,expediente=None,province=None,ccaa=None,
                event_type='PUBLIC_INFO',commercial_stage='EARLY',project_key='d'))
            self.assertEqual(repair_power(c)['events_changed'],0);c.close()
