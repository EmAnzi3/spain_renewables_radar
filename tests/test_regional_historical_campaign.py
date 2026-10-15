import calendar
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import regional_historical_campaign as campaign

RUN = '123456'
SHA = 'a' * 40


class RegionalHistoricalCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def artifact(self, source='BOA', month='2024-10', attempt=1, **changes):
        folder = self.root / f'regional-historical-{source}-{month}-attempt-{attempt}'
        folder.mkdir(parents=True, exist_ok=True)
        days = calendar.monthrange(*map(int, month.split('-')))[1]
        manifest = dict(source=source, month=month, run_id=RUN, head_sha=SHA,
                        certified=True, pipeline_return_code=0, source_days_expected=days,
                        source_days_ok=days, source_days_failed=0, events=2,
                        quality={'ERROR': 0, 'WARN': 1, 'INFO': 0}, structural_errors=[])
        manifest.update(changes)
        (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return folder

    def inspect(self):
        with patch.object(campaign, '_verify_evidence') as verifier:
            rows, errors = campaign.inspect_artifacts(self.root, RUN, SHA)
        return rows, errors, verifier

    def test_exact_scope_and_pilots(self):
        self.assertEqual((len(campaign.MONTHS), campaign.MONTHS[0], campaign.MONTHS[-1]),
                         (24, '2024-10', '2026-09'))
        self.assertEqual(len(set(campaign.MONTHS)), 24)
        self.assertNotIn('BOE', campaign.SOURCES)
        self.assertNotIn('BOJA', campaign.SOURCES)
        self.assertEqual(len(campaign.SOURCES) * len(campaign.MONTHS), 192)

    def test_missing_is_not_zero(self):
        rows, errors, verifier = self.inspect()
        row = rows[('BOA', '2024-10')]
        self.assertEqual(row['status'], 'NOT_ATTEMPTED')
        self.assertIsNone(row['events'])
        self.assertEqual(campaign.build_plan(rows)['matrix'], {'include': []})
        self.assertEqual(campaign.build_audit(rows, errors, RUN, SHA)['verified_source_months'], 0)
        verifier.assert_not_called()

    def test_two_verified_pilots_unlock_exactly_remaining_twenty_two(self):
        for month in campaign.PILOT_MONTHS:
            self.artifact(month=month)
        rows, _, verifier = self.inspect()
        plan = campaign.build_plan(rows)
        self.assertEqual(plan['eligible_sources'], ['BOA'])
        self.assertEqual(len(plan['matrix']['include']), 22)
        self.assertFalse(any(x['month'] in campaign.PILOT_MONTHS for x in plan['matrix']['include']))
        self.assertEqual(verifier.call_count, 2)

    def test_one_pilot_does_not_unlock_source(self):
        self.artifact()
        rows, _, _ = self.inspect()
        self.assertEqual(campaign.build_plan(rows)['eligible_sources'], [])

    def test_failure_blocks_only_its_source(self):
        for month in campaign.PILOT_MONTHS:
            self.artifact('BOA', month)
            self.artifact('BOCYL', month, certified=False, error='source unavailable')
        rows, _, _ = self.inspect()
        plan = campaign.build_plan(rows)
        self.assertEqual(plan['eligible_sources'], ['BOA'])
        self.assertEqual(rows[('BOCYL', '2024-10')]['status'], 'INCOMPLETE')

    def test_foreign_run_or_revision_is_never_promoted(self):
        self.artifact(run_id='other')
        self.artifact('BOCYL', head_sha='b' * 40)
        rows, _, verifier = self.inspect()
        self.assertEqual(rows[('BOA', '2024-10')]['status'], 'INVALID_EVIDENCE')
        self.assertEqual(rows[('BOCYL', '2024-10')]['status'], 'INVALID_EVIDENCE')
        verifier.assert_not_called()

    def test_source_month_substitution_is_rejected(self):
        folder = self.artifact()
        manifest = json.loads((folder / 'manifest.json').read_text())
        manifest['source'] = 'DOG'
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        rows, _, verifier = self.inspect()
        self.assertEqual(rows[('BOA', '2024-10')]['status'], 'INVALID_EVIDENCE')
        verifier.assert_not_called()

    def test_latest_attempt_is_explicit_and_old_evidence_preserved(self):
        old = self.artifact(attempt=1)
        new = self.artifact(attempt=2, certified=False, error='network')
        rows, _, _ = self.inspect()
        self.assertEqual(rows[('BOA', '2024-10')]['attempt'], 2)
        self.assertEqual(rows[('BOA', '2024-10')]['status'], 'INCOMPLETE')
        self.assertTrue((old / 'manifest.json').exists())
        self.assertTrue((new / 'manifest.json').exists())

    def test_false_green_day_and_quality_states_rejected(self):
        for source, changes in zip(campaign.SOURCES, (
            {'source_days_ok': 30}, {'source_days_failed': 1},
            {'pipeline_return_code': 1}, {'events': -1},
            {'quality': {'ERROR': 1}}, {'structural_errors': ['bad']},
            {'legally_restricted_source_bodies': 1}, {'source_days_expected': True},
        )):
            self.artifact(source, **changes)
        rows, _, verifier = self.inspect()
        self.assertTrue(all(rows[(s, '2024-10')]['status'] == 'INVALID_EVIDENCE' for s in campaign.SOURCES))
        verifier.assert_not_called()

    def test_corrupt_evidence_is_not_a_verified_pilot(self):
        self.artifact()
        with patch.object(campaign, '_verify_evidence', side_effect=ValueError('digest mismatch')):
            rows, _ = campaign.inspect_artifacts(self.root, RUN, SHA)
        self.assertEqual(rows[('BOA', '2024-10')]['status'], 'INVALID_EVIDENCE')

    def test_database_digest_checked_before_loading(self):
        folder = self.artifact()
        (folder / 'historical.sqlite').write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'SQLite digest'):
            campaign._verify_evidence(folder, {'database_sha256': '0' * 64})

    def test_report_digest_and_traversal_checked(self):
        folder = self.artifact()
        database = folder / 'historical.sqlite'
        database.write_bytes(b'test database')
        report = folder / 'workspace/reports/source.json'
        report.parent.mkdir(parents=True)
        report.write_text('original')
        manifest = {'database_sha256': campaign.digest(database),
                    'original_report_sha256': {'reports/source.json': '0' * 64}}
        with self.assertRaisesRegex(ValueError, 'report digest'):
            campaign._verify_evidence(folder, manifest)
        manifest['original_report_sha256'] = {'../manifest.json': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'unsafe original report'):
            campaign._verify_evidence(folder, manifest)

    def test_complete_planned_matrix_still_not_national_certificate(self):
        rows, _, _ = self.inspect()
        for row in rows.values():
            row['status'] = 'VERIFIED'
        audit = campaign.build_audit(rows, [], RUN, SHA)
        self.assertEqual(audit['verified_source_months'], 192)
        self.assertTrue(audit['all_planned_source_months_verified'])
        self.assertFalse(audit['nationwide_historical_24_months_complete'])
        self.assertFalse(audit['complete_17_regions_claim'])
        self.assertFalse(audit['database_merged'])

    def test_missing_or_invalid_manifest_is_explicit(self):
        folder = self.artifact()
        (folder / 'manifest.json').unlink()
        rows, _, _ = self.inspect()
        self.assertEqual(rows[('BOA', '2024-10')]['status'], 'INVALID_EVIDENCE')
        (folder / 'manifest.json').write_text('broken')
        rows, _, _ = self.inspect()
        self.assertEqual(rows[('BOA', '2024-10')]['status'], 'INVALID_EVIDENCE')

    def test_unexpected_scope_is_audited(self):
        (self.root / 'regional-historical-BOE-2024-10-attempt-1').mkdir()
        rows, errors, _ = self.inspect()
        self.assertEqual(len(errors), 1)
        self.assertFalse(campaign.build_audit(rows, errors, RUN, SHA)['all_planned_source_months_verified'])


if __name__ == '__main__':
    unittest.main()
