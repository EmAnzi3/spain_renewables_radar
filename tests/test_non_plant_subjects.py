"""Energy-storage *topics* (agreements, grants, R&D centres, battery factories, boreholes, waste) are not plants."""
import tempfile,unittest
from pathlib import Path
from app.db import connect
from app.parser import parse_event,non_plant_subject
from app.store import save_event
from app.identity_migration import repair_legacy_identities

NOT_PLANTS=[
 'Convenios.- Resolución de 20 de diciembre de 2024, de la Secretaría General, por la que se da publicidad a la Adenda de modificación del "Convenio para la puesta en marcha del Centro Nacional de Investigación de Almacenamiento Energético"',
 'Investigación. Ayudas.- Decreto 55/2025 por el que se establecen las bases reguladoras de ayudas para actividades de I+D+i en el ámbito del almacenamiento de energía',
 'Impacto ambiental.- Resolución por la que se formula declaración de impacto ambiental del proyecto de planta de fabricación de materiales para cátodos de baterías en el término municipal de Mérida',
 'ANUNCIO del expediente de autorización ambiental integrada para una industria de fabricación de baterías, situada en el polígono 101, parcela 2 GAUSA',
 'ORDEN FOM/726/2025 por la que se aprueba inicialmente el Proyecto de Interés General de Aragón "Construcción de una gigafactoría para la fabricación de baterías"',
 'Resolución por la que se formula informe de impacto ambiental del proyecto «Ejecución de una batería de sondeos de investigación de recursos geotérmicos» en Melilla',
 'ORDEN MAV/1461/2024 por la que se concede autorización ambiental a la instalación de almacenamiento temporal de residuos peligrosos',
]
PLANTS=[
 'Anuncio por el que se somete a información pública la solicitud de autorización administrativa previa del sistema de almacenamiento de energía mediante baterías BESS Almagro I de 7,2 MW',
 'Resolución por la que se otorga autorización administrativa de construcción de la planta fotovoltaica Matacan Solar de 44,464 MW',
 'Anuncio por el que se convoca el levantamiento de actas previas a la ocupación de las fincas afectadas por el parque eólico Sierra de la Venta',
 'Anuncio de información pública del aprovechamiento hidroeléctrico reversible (central de bombeo) de 804 MW',
]

class SubjectTests(unittest.TestCase):
    def test_topics_are_not_plants(self):
        for t in NOT_PLANTS:
            with self.subTest(t=t[:60]):
                self.assertTrue(non_plant_subject(t))
                self.assertIsNone(parse_event(source_code='DOE',external_id='X',publication_date='2025-01-01',title=t,url='u',raw_text=t+' baterías').technology)
    def test_real_plants_and_expropriations_stay(self):
        for t in PLANTS:
            with self.subTest(t=t[:60]):self.assertFalse(non_plant_subject(t))
    def test_stored_topic_is_quarantined_and_its_project_removed(self):
        with tempfile.TemporaryDirectory() as td:
            c=connect(str(Path(td)/'db.sqlite'))
            from dataclasses import replace
            e=replace(parse_event(source_code='DOE',external_id='DOE-2024064168',publication_date='2024-12-27',title=NOT_PLANTS[0],url='u',raw_text=NOT_PLANTS[0]),technology='BESS')
            save_event(c,e);save_event(c,parse_event(source_code='BOE',external_id='BOE-1',publication_date='2025-01-01',title=PLANTS[1],url='u',raw_text=PLANTS[1]));c.commit()
            r=repair_legacy_identities(c,report_dir=str(Path(td)/'id'),backup_dir=str(Path(td)/'bk'))
            self.assertEqual(r['quarantined_source_events'],1)
            self.assertEqual([x[0] for x in c.execute('SELECT external_id FROM events')],['BOE-1'])
            self.assertEqual(c.execute('SELECT count(*) FROM projects').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT reason FROM quarantined_source_events').fetchone()[0],'NON_PLANT_SUBJECT_NOT_A_PROJECT');c.close()
