import unittest
from app.dogc_projection import project_geography
from app.enrichment.ine_municipalities import Municipality

class InternalArticleTests(unittest.TestCase):
    def test_official_internal_contraction_is_matched_not_guessed(self):
        title='PS Cantallops al terme municipal de Parets del Vallès (exp. FUE-2024-03724213)'
        catalog=[Municipality('Parets del Vallès','08159','Barcelona','Cataluña')]
        geo=project_geography(title,catalog)
        self.assertEqual(geo['status'],'RESOLVED');self.assertEqual(geo['provinces'],['Barcelona'])
        self.assertEqual(geo['municipalities'][0]['name'],'Parets del Vallès')
        self.assertEqual(geo['source_quote'], 'de Parets del Vallès ')

    def test_internal_contraction_does_not_hide_multi_province(self):
        catalog=[Municipality('Cervera','25072','Lleida','Cataluña'),Municipality('Cabra del Camp','43036','Tarragona','Cataluña')]
        geo=project_geography('als termes municipals de Cervera i Cabra del Camp',catalog)
        self.assertEqual(geo['status'],'MULTI_PROVINCE');self.assertEqual(geo['provinces'],['Lleida','Tarragona'])

    def test_ambiguous_official_alias_does_not_force_a_province(self):
        catalog=[Municipality('Parets del Vallès','08159','Barcelona','Cataluña'),Municipality('Parets de el Vallès','99999','Girona','Cataluña')]
        self.assertEqual(project_geography('al terme municipal de Parets del Vallès',catalog)['status'],'UNRESOLVED')

    def test_partial_or_misspelled_name_stays_unresolved(self):
        catalog=[Municipality('Cabra del Camp','43036','Tarragona','Cataluña')]
        for title in ['al terme municipal de Cabra Camp','al terme municipal de Cabra del Cam']:
            self.assertEqual(project_geography(title,catalog)['status'],'UNRESOLVED')
