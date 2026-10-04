import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests
from app.catalunya_inventory import (
    API, ORIGIN, SOURCE, DATASETS, REQUIRED, InventoryClient, atomic_json,
    build_groups, canonical, content_signature, numeric, official_url,
    reconcile, state_lock, validate_snapshot, verify_evidence, write_report,
)


def row(**extra):
    result = {'socrata_row_id': 'row-1', 'sol_licitud': 'FUE-2020-01814439',
              'nom': 'Parc eòlic Conca de Barberà III', 'municipi': 'Talavera',
              'codi_municipi': '252167', 'pot_ncia_mw': '35',
              'sol_licitant': 'Desarrollos Eólicos Cuenca de Barberá, SL',
              'estat': 'Autoritzat', 'n_m_aerogeneradors': '7',
              'aerogeneradors_al_municipi': '4', 'data_pon_ncia': '2022-12-01T00:00:00.000'}
    result.update(extra)
    return result


def snapshot(wind=None, pv=None):
    s = {'source': SOURCE, 'schema_version': 1, 'complete': True,
         'retrieved_at': '2026-10-04T10:00:00+00:00', 'datasets': {}}
    for tech, records in [('WIND', wind if wind is not None else [row()]),
                          ('PV', pv if pv is not None else [row(nom='PSFV La Serra', pot_ncia_mw='2.31', superf_cie_ha='3.45')])]:
        s['datasets'][tech] = {'dataset_id': DATASETS[tech], 'source_count': len(records), 'rows': records,
                              'groups': build_groups(tech, records), 'metadata': {'rows_updated_at': 1790585233}}
    s['content_sha256'] = content_signature(s)
    return s


class Response:
    def __init__(self, payload, status=200):
        self.raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.status_code = status
        self.closed = False
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))
    def iter_content(self, size):
        yield self.raw
    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, *, duplicate=False, truncated=False, drift=False, failure=None):
        self.calls = []; self.reads = {}; self.duplicate = duplicate
        self.truncated = truncated; self.drift = drift; self.failure = failure
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.failure:
            if isinstance(self.failure, Exception):
                raise self.failure
            return Response(b'forbidden', self.failure)
        if url == ORIGIN:
            return Response((''.join(f'<a href="{API}/Medi-Ambient/x/{d}/about_data">x</a>' for d in DATASETS.values())).encode())
        path = urlsplit(url).path; dataset = Path(path).stem
        self.reads[path] = self.reads.get(path, 0) + 1
        if '/api/views/' in path:
            return Response({'id': dataset, 'rowsUpdatedAt': 1790585233 + int(self.drift and self.reads[path] > 1),
                             'columns': [{'fieldName': k, 'dataTypeName': 'number' if k == 'pot_ncia_mw' else 'text'} for k in REQUIRED]})
        q = parse_qs(urlsplit(url).query)
        if q['$select'] == ['count(*)']:
            return Response([{'count': '2'}])
        offset = int(q['$offset'][0])
        if self.truncated and offset:
            return Response([])
        return Response([row(socrata_row_id='row-1' if self.duplicate else 'row-' + str(offset),
                             codi_municipi='252167' if not offset else '251410',
                             municipi='Talavera' if not offset else 'Montoliu de Segarra')])


class CatalunyaInventoryTests(unittest.TestCase):
    def test_multi_municipal_zero_is_not_new_project_or_zero_capacity(self):
        g = build_groups('WIND', [row(), row(socrata_row_id='row-2', pot_ncia_mw='0', municipi='Montoliu de Segarra', codi_municipi='251410', n_m_aerogeneradors='0', aerogeneradors_al_municipi='3')])
        self.assertEqual(len(g), 1); self.assertEqual(g[0]['reported_nominal_mw'], 35)
        self.assertEqual(g[0]['reported_total_turbines'], 7); self.assertEqual(len(g[0]['municipalities']), 2)
    def test_repeated_positive_capacity_not_summed(self):
        g = build_groups('WIND', [row(), row(socrata_row_id='row-2', municipi='Other')])[0]
        self.assertEqual(g['reported_nominal_mw'], 35)
    def test_conflicting_capacity_stays_unknown(self):
        g = build_groups('WIND', [row(), row(pot_ncia_mw='40')])[0]
        self.assertIsNone(g['reported_nominal_mw']); self.assertIn('POT_NCIA_MW_CONFLICT_NOT_RESOLVED', g['quality_flags'])
    def test_total_area_not_summed_across_municipalities(self):
        g = build_groups('PV', [row(superf_cie_ha='20'), row(superf_cie_ha='20', municipi='Other')])[0]
        self.assertEqual(g['reported_total_area_ha'], 20)
    def test_references_with_different_names_not_merged(self):
        gs = build_groups('PV', [row(nom='Solar A'), row(nom='Solar B')])
        self.assertEqual(len(gs), 2)
        self.assertTrue(all('REFERENCE_SHARED_BY_DIFFERENT_NAMES_NOT_MERGED' in g['quality_flags'] for g in gs))
    def test_missing_reference_rows_not_merged(self):
        gs = build_groups('WIND', [row(sol_licitud=None), row(sol_licitud=None, municipi='Other')])
        self.assertEqual(len(gs), 2)
    def test_exact_duplicate_unidentified_rows_are_preserved(self):
        gs = build_groups('WIND', [row(sol_licitud=None), row(sol_licitud=None)])
        self.assertEqual(len(gs), 2); self.assertNotEqual(gs[0]['group_key'], gs[1]['group_key'])
    def test_province_is_from_official_municipal_code_not_applicant(self):
        g = build_groups('WIND', [row(sol_licitant='Madrid SL')])[0]
        self.assertEqual(g['provinces'], ['Lleida'])
    def test_invalid_code_does_not_invent_province(self):
        g = build_groups('WIND', [row(codi_municipi='999999')])[0]
        self.assertEqual(g['provinces'], []); self.assertIn('MUNICIPALITY_CODE_UNRESOLVED', g['quality_flags'])
    def test_zero_and_missing_power_are_not_positive_capacity(self):
        for value in [None, '0', '']:
            self.assertIsNone(build_groups('WIND', [row(pot_ncia_mw=value)])[0]['reported_nominal_mw'])
    def test_invalid_numeric_source_stops_instead_of_guessing(self):
        for value in ['NaN', 'Infinity', '-1', '2,5', True, '1e9999']:
            with self.assertRaises(ValueError): numeric(value)
    def test_source_state_and_meeting_date_do_not_become_event_dates(self):
        g = build_groups('WIND', [row()])[0]
        self.assertEqual(g['environmental_meeting_dates'], ['2022-12-01'])
        for key in ['web_publication_date','authorization_date','construction_start','construction_end','epc_contractor']:
            self.assertIsNone(g[key])
    def test_initial_baseline_is_not_new_opportunities(self):
        result = reconcile(None, snapshot())
        self.assertEqual(result['mode'], 'BASELINE'); self.assertEqual(result['newly_observed'], [])
        self.assertEqual(result['dated_events_created'], 0)
    def test_semantic_replay_ignores_system_ids_and_fetch_dates(self):
        a = snapshot(); b = snapshot(wind=[row(socrata_row_id='replacement-id')]); b['retrieved_at'] = '2026-10-05T10:00:00+00:00'
        self.assertEqual(a['content_sha256'], b['content_sha256']); self.assertEqual(reconcile(a,b)['changed'], [])
    def test_source_state_change_detected_without_lifecycle_inference(self):
        result = reconcile(snapshot(), snapshot(wind=[row(estat='No autoritzat')]))
        self.assertEqual(len(result['changed']), 1); self.assertEqual(result['dated_events_created'], 0)
    def test_absence_is_not_seen_not_withdrawn(self):
        a = snapshot(wind=[row(), row(nom='Other')]); b = snapshot()
        result = reconcile(a,b); self.assertEqual(len(result['not_seen']), 1); self.assertNotIn('withdrawn', result)
    def test_incomplete_snapshot_cannot_replace_baseline(self):
        s = snapshot(); s['complete'] = False
        with self.assertRaises(ValueError): reconcile(None, s)
    def test_corrupted_projection_is_rejected(self):
        s = snapshot(); s['datasets']['WIND']['groups'][0]['reported_nominal_mw'] = 999
        with self.assertRaises(ValueError): validate_snapshot(s)
    def test_cross_source_snapshot_is_rejected(self):
        s = snapshot(); s['source'] = 'DOGC'
        with self.assertRaises(ValueError): reconcile(s, snapshot())
    def test_foreign_host_and_nondefault_port_not_contacted(self):
        for u in ['https://example.com/resource/dh5g-4nit.json', API + ':444/resource/dh5g-4nit.json', 'http://analisi.transparenciacatalunya.cat/resource/dh5g-4nit.json', API + '/resource/xxxx-xxxx.json']:
            with self.assertRaises(ValueError): official_url(u)
    def test_live_contract_pagination_and_raw_rebuild(self):
        with tempfile.TemporaryDirectory() as d, patch('app.catalunya_inventory.time.sleep'):
            client = InventoryClient(d, session=FakeSession(), page_size=1, pause=0)
            s = client.collect(); self.assertTrue(verify_evidence(s,d))
            self.assertEqual(len(s['datasets']['PV']['rows']), 2)
    def test_repeated_page_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as d, patch('app.catalunya_inventory.time.sleep'):
            with self.assertRaises(ValueError): InventoryClient(d, session=FakeSession(duplicate=True), page_size=1).collect()
    def test_truncated_page_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as d, patch('app.catalunya_inventory.time.sleep'):
            with self.assertRaises(ValueError): InventoryClient(d, session=FakeSession(truncated=True), page_size=1).collect()
    def test_version_drift_fails_acquisition(self):
        with tempfile.TemporaryDirectory() as d, patch('app.catalunya_inventory.time.sleep'):
            with self.assertRaises(ValueError): InventoryClient(d, session=FakeSession(drift=True), page_size=1).collect()
    def test_network_retries_are_bounded(self):
        with tempfile.TemporaryDirectory() as d, patch('app.catalunya_inventory.time.sleep'):
            session = FakeSession(failure=requests.ConnectionError('offline'))
            with self.assertRaises(requests.ConnectionError): InventoryClient(d, session=session).collect()
            self.assertEqual(len(session.calls), 3)
    def test_forbidden_is_not_retried_or_bypassed(self):
        with tempfile.TemporaryDirectory() as d:
            session = FakeSession(failure=403)
            with self.assertRaises(requests.HTTPError): InventoryClient(d, session=session).collect()
            self.assertEqual(len(session.calls), 1)
    def test_corrupt_raw_bytes_fail_verification(self):
        with tempfile.TemporaryDirectory() as d, patch('app.catalunya_inventory.time.sleep'):
            c = InventoryClient(d, session=FakeSession(), page_size=1); s = c.collect()
            next(Path(d).glob('*.bin')).write_bytes(b'corrupted')
            with self.assertRaises(ValueError): verify_evidence(s,d)
    def test_report_escapes_source_markup_and_protects_csv_formulas(self):
        with tempfile.TemporaryDirectory() as d:
            s = snapshot(wind=[row(nom='<script>alert(1)</script>', sol_licitud='=HYPERLINK(1)')])
            write_report(d,s,reconcile(None,s)); text = (Path(d)/'index.html').read_text()
            self.assertIn('&lt;script&gt;',text); self.assertNotIn('<script>alert',text)
            self.assertIn("'=HYPERLINK", (Path(d)/'inventory.csv').read_text())
    def test_state_lock_prevents_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'baseline.json'
            with state_lock(p):
                with self.assertRaises(FileExistsError):
                    with state_lock(p): pass
            self.assertFalse(Path(str(p)+'.lock').exists())
    def test_atomic_json_preserves_original_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'baseline.json'; atomic_json(p,{'old':True}); before=p.read_bytes()
            with patch('app.catalunya_inventory.os.replace', side_effect=OSError('denied')):
                with self.assertRaises(OSError): atomic_json(p,{'new':True})
            self.assertEqual(p.read_bytes(),before)


if __name__ == '__main__': unittest.main()
