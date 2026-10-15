"""Plan bounded regional backfill from verified pilots and audit every source/month.

This does not merge or publish a database and never certifies all Spanish regions.
All inputs are original artifacts from the same workflow run and code revision.
Failed and missing source/months remain explicit; they are never zero projects.
"""
from __future__ import annotations

import argparse
import calendar
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re

SOURCES = ('BOA', 'BOCYL', 'DOCM', 'DOE', 'BORM', 'BOCM', 'DOG', 'DOGC')
MONTHS = tuple(f'{2024 + (9 + i) // 12}-{(9 + i) % 12 + 1:02d}' for i in range(24))
PILOT_MONTHS = (MONTHS[0], MONTHS[-1])
ARTIFACT = re.compile(r'^regional-historical-([A-Z]+)-(\d{4}-\d{2})-attempt-([1-9]\d*)$')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_evidence(folder: Path, manifest: dict) -> None:
    """Reuse the existing DB/day verifier and additionally verify original reports."""
    database = folder / 'historical.sqlite'
    if digest(database) != manifest.get('database_sha256'):
        raise ValueError('Original SQLite digest mismatch')
    reports = manifest.get('original_report_sha256')
    if not isinstance(reports, dict) or not reports:
        raise ValueError('Original report digest inventory missing')
    workspace = (folder / 'workspace').resolve()
    report_root = workspace / 'reports'
    for name, expected in reports.items():
        target = (workspace / name).resolve()
        if not target.is_relative_to(report_root) or not target.is_file():
            raise ValueError('Missing or unsafe original report path: ' + str(name))
        if digest(target) != expected:
            raise ValueError('Original report digest mismatch: ' + name)
    actual = {str(p.relative_to(workspace)) for p in report_root.rglob('*') if p.is_file()}
    if actual != set(reports):
        raise ValueError('Original report inventory mismatch')
    from scripts.merge_historical_shards import load_shard
    load_shard(folder)


def inspect_artifacts(root: Path, run_id: str, head_sha: str) -> tuple[dict, list]:
    """Latest attempt wins within a run; prior artifacts remain untouched."""
    found = {}
    errors = []
    if root.exists():
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            match = ARTIFACT.fullmatch(folder.name)
            if not match or match[1] not in SOURCES or match[2] not in MONTHS:
                errors.append({'artifact': folder.name, 'error': 'Unexpected artifact scope'})
                continue
            key = (match[1], match[2])
            attempt = int(match[3])
            if key not in found or attempt > found[key][0]:
                found[key] = (attempt, folder)
    rows = {}
    for source in SOURCES:
        for month in MONTHS:
            row = {'source': source, 'month': month, 'status': 'NOT_ATTEMPTED',
                   'events': None, 'source_days_ok': None, 'source_days_failed': None,
                   'quality': None, 'error': None}
            rows[(source, month)] = row
            if (source, month) not in found:
                continue
            attempt, folder = found[(source, month)]
            row.update(attempt=attempt, artifact=folder.name)
            try:
                path = folder / 'manifest.json'
                manifest = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(manifest, dict):
                    raise ValueError('Manifest is not an object')
                if (manifest.get('source'), manifest.get('month')) != (source, month):
                    raise ValueError('Artifact/manifest source-month mismatch')
                if str(manifest.get('run_id')) != run_id or manifest.get('head_sha') != head_sha:
                    raise ValueError('Artifact belongs to another run or code revision')
                row['manifest_sha256'] = digest(path)
                row['source_failures'] = manifest.get('source_failures', [])
                for field in ('events', 'source_days_ok', 'source_days_failed', 'quality'):
                    row[field] = manifest.get(field)
                if manifest.get('certified') is not True:
                    row.update(status='INCOMPLETE', error=manifest.get('error') or 'Original monthly certification failed')
                    continue
                year, number = map(int, month.split('-'))
                days = calendar.monthrange(year, number)[1]
                expected = {'pipeline_return_code': 0, 'source_days_expected': days,
                            'source_days_ok': days, 'source_days_failed': 0}
                if any(type(manifest.get(k)) is not int or manifest[k] != v for k, v in expected.items()):
                    raise ValueError('Certified manifest has inconsistent source/day or process state')
                if type(manifest.get('events')) is not int or manifest['events'] < 0:
                    raise ValueError('Invalid source-event count')
                quality = manifest.get('quality', {})
                if not isinstance(quality, dict) or type(quality.get('ERROR')) is not int or quality['ERROR'] != 0:
                    raise ValueError('Missing or failing structural quality gate')
                if manifest.get('structural_errors') != [] or manifest.get('legally_restricted_source_bodies', 0):
                    raise ValueError('Structural or restricted-evidence gap')
                _verify_evidence(folder, manifest)
                row['status'] = 'VERIFIED'
            except Exception as exc:
                row.update(status='INVALID_EVIDENCE', error=str(exc))
    return rows, errors


def build_plan(rows: dict) -> dict:
    eligible = [source for source in SOURCES
                if all(rows[(source, month)]['status'] == 'VERIFIED' for month in PILOT_MONTHS)]
    pending = [{'source': source, 'month': month} for source in eligible
               for month in MONTHS if month not in PILOT_MONTHS]
    return {'mode': 'VERIFIED_OLDEST_AND_NEWEST_PILOTS_THEN_REMAINING_MONTHS',
            'eligible_sources': eligible,
            'blocked_sources': [source for source in SOURCES if source not in eligible],
            'pilot_months': list(PILOT_MONTHS), 'matrix': {'include': pending},
            'national_certification': False}


def build_audit(rows: dict, errors: list, run_id: str, head_sha: str) -> dict:
    entries = [rows[(source, month)] for source in SOURCES for month in MONTHS]
    totals = dict(Counter(row['status'] for row in entries))
    verified = totals.get('VERIFIED', 0)
    return {'schema': 1, 'state': 'SOURCE_MONTH_EVIDENCE_NOT_NATIONAL_CERTIFICATION',
            'run_id': run_id, 'head_sha': head_sha,
            'window_start': '2024-10-01', 'window_end': '2026-09-30',
            'sources': list(SOURCES), 'expected_source_months': len(SOURCES) * len(MONTHS),
            'status_counts': totals, 'verified_source_months': verified,
            'all_planned_source_months_verified': verified == len(entries) and not errors,
            'nationwide_historical_24_months_complete': False,
            'complete_17_regions_claim': False, 'database_merged': False,
            'non_implemented_regions_are_not_zero_opportunities': True,
            'artifact_errors': errors, 'source_months': entries}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan', 'audit'))
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    run_id = os.environ.get('GITHUB_RUN_ID', '')
    head_sha = os.environ.get('GITHUB_SHA', '')
    if not run_id.isdigit() or not re.fullmatch(r'[0-9a-f]{40}', head_sha):
        raise SystemExit('Explicit GitHub workflow run/code provenance required')
    rows, errors = inspect_artifacts(args.artifacts, run_id, head_sha)
    result = build_plan(rows) if args.mode == 'plan' else build_audit(rows, errors, run_id, head_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.mode == 'plan':
        result['artifact_errors'] = errors
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
            out.write('matrix=' + json.dumps(result['matrix'], separators=(',', ':')) + '\n')
            out.write('has_work=' + str(bool(result['matrix']['include'])).lower() + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as out:
            out.write('## Regional historical evidence\n\n')
            out.write('October 2024 through September 2026. No national certification or database publication.\n\n')
            out.write('| Source | Verified months | Incomplete | Invalid evidence | Not attempted |\n|---|---:|---:|---:|---:|\n')
            for source in SOURCES:
                counts = Counter(rows[(source, month)]['status'] for month in MONTHS)
                out.write('| ' + source + ' | ' + ' | '.join(str(counts[s]) for s in (
                    'VERIFIED', 'INCOMPLETE', 'INVALID_EVIDENCE', 'NOT_ATTEMPTED')) + ' |\n')
    print('REGIONAL_HISTORICAL_' + args.mode.upper(), json.dumps({
        key: value for key, value in result.items() if key not in ('source_months', 'matrix')}, ensure_ascii=False))
    if args.mode == 'audit' and not result['all_planned_source_months_verified']:
        raise SystemExit('Regional campaign has explicit gaps; see original evidence audit')


if __name__ == '__main__':
    main()
