"""Publish a verified existing portal, independently of source availability.

This is artifact replay, not harvesting, data enrichment or a new certification.
The source must be a successful main operational run of this same repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
REPO = 'EmAnzi3/spain_renewables_radar'
WORKFLOW = '.github/workflows/radar-operational-web.yml'
ARTIFACT = 'radar-web-navigable'


class EmbeddedData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.inside = False
        self.blocks: list[str] = []
        self.dependencies: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'script' and attributes.get('id') == 'radar-data':
            if attributes.get('type') != 'application/json':
                raise ValueError('Unexpected embedded data type')
            self.inside = True
            self.blocks.append('')
        if tag == 'script' and attributes.get('src'):
            self.dependencies.append(attributes['src'])
        if tag == 'link' and attributes.get('rel') == 'stylesheet':
            self.dependencies.append(attributes.get('href', ''))

    def handle_endtag(self, tag):
        if tag == 'script':
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.blocks[-1] += data


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must preserve its original timezone')
    return parsed


def check_run(run: dict, run_id: str) -> None:
    if (str(run.get('id')) != run_id or run.get('conclusion') != 'success'
            or run.get('status') != 'completed' or run.get('head_branch') != 'main'
            or run.get('path') != WORKFLOW
            or run.get('event') not in ('push', 'workflow_dispatch', 'schedule')
            or run.get('head_repository', {}).get('full_name') != REPO
            or not re.fullmatch(r'[0-9a-f]{40}', run.get('head_sha', ''))):
        raise ValueError('Source is not the requested successful own main operational run')


def verify_site(site: Path, run: dict) -> dict:
    """Reconcile the browser file, JSON, build receipt and operational status."""
    content = (site / 'index.html').read_bytes()
    data = json.loads((site / 'data.json').read_text(encoding='utf-8'))
    build = json.loads((site / 'build_receipt.json').read_text(encoding='utf-8'))
    browser = json.loads((site / 'browser_receipt.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(content).hexdigest()
    if build.get('index_sha256') != digest:
        raise ValueError('Browser page differs from the recorded original build')
    parser = EmbeddedData()
    parser.feed(content.decode('utf-8'))
    if len(parser.blocks) != 1 or json.loads(parser.blocks[0]) != data:
        raise ValueError('Browser embedded data differs from the downloadable JSON')
    if parser.dependencies:
        raise ValueError('Portal requires unreviewed runtime dependencies')
    records, status = data['records'], data['status']
    identities = [row['project_key'] for row in records]
    events = [event for row in records for event in row['events']]
    if not records or len(set(identities)) != len(identities) or any(not row['events'] for row in records):
        raise ValueError('Empty, duplicate or sourceless project cards')
    if (len(records) != build['projects'] or len(events) != build['events']
            or len(records) != status['projects'] or len(events) != status['events']):
        raise ValueError('Published project/event counts are inconsistent')
    if (status.get('run_id') != str(run['id']) or status.get('head_sha') != run['head_sha']
            or status.get('database_promoted') is not True
            or status.get('state') not in ('COMPLETE', 'PARTIAL')
            or status.get('full_certification') is not False or build.get('full_certification') is not False
            or build.get('state') != status['state'] or status.get('quality', {}).get('ERROR') != 0):
        raise ValueError('Source update provenance or quality is not publishable')
    sources = status['sources']
    complete = sum(row['status'] == 'COMPLETE' for row in sources.values())
    if (len(sources) != status['configured_sources'] or complete != status['complete_sources']
            or (complete == len(sources)) != (status['state'] == 'COMPLETE')):
        raise ValueError('A partial source update is being relabelled or miscounted')
    if (browser.get('javascript_errors') != [] or browser.get('mobile_horizontal_overflow') is not False
            or browser.get('real_data_projects') != len(records)):
        raise ValueError('Original browser validation is not consistent')
    original_time = timestamp(status['completed_at'])
    generation = timestamp(data['generated_at'])
    if generation < original_time or build['generated_at'] != data['generated_at']:
        raise ValueError('Page timestamp is inconsistent with the recorded update')
    return {'source_run_id': str(run['id']), 'source_head_sha': run['head_sha'],
            'projects': len(records), 'events': len(events), 'state': status['state'],
            'complete_sources': complete, 'configured_sources': len(sources),
            'unavailable_sources': sorted(k for k, v in sources.items() if v['status'] != 'COMPLETE'),
            'source_window_start': status['window_start'], 'source_window_end': status['window_end'],
            'original_update_completed_at': status['completed_at'],
            'original_page_generated_at': data['generated_at'], 'index_sha256': digest,
            'new_source_requests': 0, 'data_rewritten': False, 'full_certification': False,
            'publication_type': 'VERIFIED_EXISTING_OPERATIONAL_PORTAL'}


def read_api(path: str) -> dict:
    from scripts.portal_inputs import api
    with api(path) as response:
        response.raise_for_status()
        return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', default='publication')
    args = parser.parse_args()
    if not re.fullmatch(r'[1-9][0-9]{0,19}', args.run_id):
        raise ValueError('Source run must be a positive GitHub run identifier')
    run = read_api('/actions/runs/' + args.run_id)
    check_run(run, args.run_id)
    artifacts = read_api('/actions/runs/' + args.run_id + '/artifacts')['artifacts']
    matches = [item for item in artifacts if item['name'] == ARTIFACT and not item['expired']]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous navigable artifact')
    artifact = matches[0]
    sha = artifact.get('digest', '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', sha):
        raise ValueError('Artifact does not provide an integrity digest')
    from scripts.portal_inputs import download
    root = Path('publication-input')
    download(artifact['id'], artifact['size_in_bytes'], sha[7:], 'verified', root)
    site = root / 'verified' / 'site'
    receipt = verify_site(site, run)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'data.json', 'build_receipt.json', 'browser_receipt.json'):
        shutil.copyfile(site / name, output / name)
    (output / '.nojekyll').write_text('', encoding='utf-8')
    receipt.update(source_artifact_id=artifact['id'], artifact_sha256=sha[7:],
                   artifact_bytes=artifact['size_in_bytes'], artifact_integrity_verified=True,
                   publication_run_id=os.getenv('GITHUB_RUN_ID'))
    (output / 'publication_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    readme = ('SPAIN RENEWABLES RADAR\n\nAprire index.html nel browser: non serve un server.\n'
              f"Schede: {receipt['projects']}; eventi: {receipt['events']}.\n"
              f"Copertura: {receipt['complete_sources']}/{receipt['configured_sources']} fonti, stato {receipt['state']}.\n"
              f"Finestra tentata: {receipt['source_window_start']} - {receipt['source_window_end']}.\n"
              'Le date originali sono conservate. La pubblicazione non e una nuova scansione.\n'
              'Il portale distingue gli avvisi da integrare dai progetti gia presenti nel database.\n')
    (output / 'LEGGIMI.txt').write_text(readme, encoding='utf-8')
    print('PUBLICATION_INPUT_VERIFIED', json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
