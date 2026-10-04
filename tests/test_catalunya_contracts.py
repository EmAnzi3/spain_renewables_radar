"""Regression cases from actual official SoQL/TLS contract diagnostics."""
import ssl
import unittest
from app.catalunya_inventory import source_selection
from scripts.probe_dogc_services import VerifiedDOGCTLSAdapter


class CatalunyaContractTests(unittest.TestCase):
    def test_live_soql_contract_uses_explicit_columns_not_trailing_star(self):
        meta = {'columns': [{'fieldName': 'nom'}, {'fieldName': 'pot_ncia_mw'}]}
        self.assertEqual(source_selection(meta), ':id AS socrata_row_id, nom, pot_ncia_mw')
        self.assertNotIn('*', source_selection(meta))

    def test_new_source_columns_are_retained_in_query(self):
        meta = {'columns': [{'fieldName': 'nom'}, {'fieldName': 'new_source_field'}]}
        self.assertIn('new_source_field', source_selection(meta))

    def test_unsafe_or_colliding_source_column_is_rejected(self):
        for fields in [['nom', 'nom'], ['socrata_row_id'], ['nom;SELECT'], []]:
            with self.assertRaises(ValueError):
                source_selection({'columns': [{'fieldName': f} for f in fields]})

    def test_dogc_tls_keeps_certificate_and_hostname_verification(self):
        context = VerifiedDOGCTLSAdapter().poolmanager.connection_pool_kw['ssl_context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertGreaterEqual(context.security_level, 2)


if __name__ == '__main__':
    unittest.main()
