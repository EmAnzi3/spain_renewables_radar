import unittest
from datetime import date

from app.collectors.borm import BORMCollector


class BORMCollectorTests(unittest.TestCase):
    def _row(self, publication_date, summary, npe="A-021026-4758", html="https://www.borm.es/#/home/anuncio/02-10-2026/4758"):
        return [
            "BOLETIN","4758","845440","228",publication_date,summary,
            "Comunidad Autónoma","I. Comunidad Autónoma","4. Anuncios",
            "Consejería de Medio Ambiente, Industria, Universidades, Investigación y Mar Menor",
            "0","2026","ANUNCIO","2026-10-02 00:00:00","2026","",
            npe,html,"https://www.borm.es/services/anuncio/845440/pdf","3",
        ]

    def test_hybrid_notice_from_official_index(self):
        row=self._row(
            "2026-10-02 00:00:00",
            "Anuncio de información pública relativa a la solicitud de autorización administrativa previa "
            "y autorización administrativa de construcción de modificación al proyecto de instalación "
            "solar fotovoltaica “FV Ópera” para su hibridación mediante instalación de almacenamiento "
            "de baterías electroquímicas. Expte. 4E22ATE31627.",
        )
        e=BORMCollector.event_from_row(row,date(2026,10,2))
        self.assertIsNotNone(e)
        self.assertEqual(e.technology,"HYBRID")
        self.assertEqual(e.project_name,"FV Ópera")
        self.assertEqual(e.expediente,"4E22ATE31627")
        self.assertEqual(e.province,"Murcia")
        self.assertEqual(e.ccaa,"Murcia")
        self.assertEqual(e.event_type,"PUBLIC_INFO")

    def test_bess_notice(self):
        row=self._row(
            "2026-09-21 00:00:00",
            "Anuncio de información pública relativo a la solicitud de autorización administrativa previa "
            "y autorización administrativa de construcción de instalación eléctrica de producción denominada "
            "proyecto técnico administrativo de la planta de almacenamiento “BESS Cerrillares”, en el término "
            "municipal de Jumilla. Expediente 4E26ATE20282.",
            npe="A-210926-4526",
        )
        e=BORMCollector.event_from_row(row,date(2026,9,21))
        self.assertIsNotNone(e)
        self.assertEqual(e.technology,"BESS")
        self.assertEqual(e.project_name,"BESS Cerrillares")
        self.assertEqual(e.expediente,"4E26ATE20282")
        self.assertEqual(e.province,"Murcia")

    def test_wrong_date_and_non_project_are_ignored(self):
        project=self._row(
            "2026-10-02 00:00:00",
            "Anuncio de información pública de instalación solar fotovoltaica FV Demo de 5 MW.",
        )
        self.assertIsNone(BORMCollector.event_from_row(project,date(2026,10,1)))

        recycling=self._row(
            "2026-10-02 00:00:00",
            "Anuncio de información pública para centro de reciclaje de paneles fotovoltaicos.",
        )
        self.assertIsNone(BORMCollector.event_from_row(recycling,date(2026,10,2)))


if __name__=="__main__":
    unittest.main()
