"""Official Catalan municipal inventory; deliberately not a dated event collector.

Source rows and administrative labels are evidence, not new opportunities.
Socrata system IDs are retained but excluded from semantic snapshot comparison:
a publisher may replace the whole dataset without changing the actual records.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import tempfile
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

SOURCE = 'CATALUNYA_INVENTORY'
DATASETS = {'WIND': 'dh5g-4nit', 'PV': 'ggx8-jkp4'}
API = 'https://analisi.transparenciacatalunya.cat'
ORIGIN = 'https://mediambient.gencat.cat/es/05_ambits_dactuacio/avaluacio_ambiental/energies_renovables/visor/index.html'
PROVINCES = {'08': 'Barcelona', '17': 'Girona', '25': 'Lleida', '43': 'Tarragona'}
REQUIRED = {'sol_licitud', 'nom', 'municipi', 'codi_municipi', 'pot_ncia_mw', 'sol_licitant', 'estat', 'data_pon_ncia'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def original_row(row):
    return {k: v for k, v in row.items() if k != 'socrata_row_id'}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def official_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Non-public or non-HTTPS inventory destination')
    if p.hostname == 'mediambient.gencat.cat' and p.path == urlsplit(ORIGIN).path:
        return url
    if p.hostname == 'analisi.transparenciacatalunya.cat' and re.fullmatch(
            r'/(?:api/views|resource)/(?:dh5g-4nit|ggx8-jkp4)\.json', p.path):
        return url
    raise ValueError('Unexpected inventory destination: ' + url)


def numeric(value):
    if value in (None, ''):
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not a source quantity')
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid source quantity') from exc
    if not number.is_finite() or number < 0 or number > Decimal('1000000000'):
        raise ValueError('Out-of-range source quantity')
    return number


def one_quantity(rows, field, flags):
    values = [numeric(row.get(field)) for row in rows]
    positives = sorted({v for v in values if v is not None and v > 0})
    if any(v == 0 for v in values):
        flags.append(field.upper() + '_SOURCE_ZERO_PRESERVED')
    if len(positives) > 1:
        flags.append(field.upper() + '_CONFLICT_NOT_RESOLVED')
        return None
    return float(positives[0]) if positives else None


def build_groups(technology, rows):
    """Exact reference + exact name groups only; never claim unique-project census."""
    if technology not in DATASETS:
        raise ValueError('Unknown dataset technology')
    groups = defaultdict(list)
    names_by_reference = defaultdict(set)
    unidentified = Counter()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('nom'), str) or not row['nom'].strip():
            raise ValueError('Source row without a usable name')
        if not isinstance(row.get('municipi'), str) or not row['municipi'].strip():
            raise ValueError('Source row without municipality')
        for field in ('estat', 'sol_licitant'):
            if row.get(field) is not None and not isinstance(row[field], str):
                raise ValueError('Invalid source text field: ' + field)
        reference = row.get('sol_licitud')
        if reference is not None and not isinstance(reference, str):
            raise ValueError('Administrative reference must remain text')
        if reference and reference.strip():
            key = digest([DATASETS[technology], reference, row['nom']])
            names_by_reference[reference].add(row['nom'])
        else:
            # Without a reference even same-name municipal rows are not merged.
            identity = digest([DATASETS[technology], original_row(row)])
            unidentified[identity] += 1
            key = identity + ':' + str(unidentified[identity])
        groups[key].append(row)
    result = []
    for key, members in sorted(groups.items()):
        members = sorted(members, key=lambda r: canonical(original_row(r)))
        first = members[0]
        flags = []
        ref = first.get('sol_licitud') or None
        if ref is not None and not ref.strip():
            ref = None
        if ref is None:
            flags.append('REFERENCE_MISSING_NO_CROSS_MUNICIPALITY_MERGE')
        elif len(names_by_reference[ref]) > 1:
            flags.append('REFERENCE_SHARED_BY_DIFFERENT_NAMES_NOT_MERGED')
        municipalities = []
        for row in members:
            code = row.get('codi_municipi')
            province = PROVINCES.get(code[:2]) if isinstance(code, str) and re.fullmatch(r'\d{6}', code) else None
            if province is None:
                flags.append('MUNICIPALITY_CODE_UNRESOLVED')
            municipalities.append({'code': code, 'name': row['municipi'], 'province': province,
                                   'source_area_ha': row.get('superf_cie_al_municipi_ha'),
                                   'source_turbines': row.get('aerogeneradors_al_municipi')})
        provinces = sorted({m['province'] for m in municipalities if m['province']})
        states = sorted({r.get('estat') for r in members if r.get('estat')})
        promoters = sorted({r.get('sol_licitant') for r in members if r.get('sol_licitant')})
        if len(states) != 1:
            flags.append('SOURCE_STATE_MISSING_OR_CONFLICTING')
        if len(promoters) != 1:
            flags.append('SOURCE_PROMOTER_MISSING_OR_CONFLICTING')
        dates = []
        for row in members:
            raw_date = row.get('data_pon_ncia')
            if raw_date:
                try:
                    dates.append(datetime.fromisoformat(raw_date).date().isoformat())
                except (ValueError, TypeError) as exc:
                    raise ValueError('Invalid environmental meeting date') from exc
        mw = one_quantity(members, 'pot_ncia_mw', flags)
        area = one_quantity(members, 'superf_cie_ha', flags) if technology == 'PV' else None
        turbines = one_quantity(members, 'n_m_aerogeneradors', flags) if technology == 'WIND' else None
        if mw is None:
            flags.append('PROJECT_POWER_UNKNOWN')
        result.append({'group_key': key, 'dataset_id': DATASETS[technology], 'technology': technology,
                       'reference': ref, 'name': first['nom'], 'municipal_rows': len(members),
                       'identity_basis': 'EXACT_REFERENCE_AND_NAME' if ref else 'UNRESOLVED_SOURCE_ROW',
                       'source_url': API + '/d/' + DATASETS[technology], 'municipalities': municipalities,
                       'provinces': provinces, 'source_states': states, 'source_promoters': promoters,
                       'reported_nominal_mw': mw, 'reported_total_area_ha': area,
                       'reported_total_turbines': turbines, 'environmental_meeting_dates': sorted(set(dates)),
                       'web_publication_date': None, 'authorization_date': None,
                       'construction_start': None, 'construction_end': None, 'epc_contractor': None,
                       'quality_flags': sorted(set(flags)), 'source_rows': members,
                       'semantic_sha256': digest([original_row(r) for r in members])})
    return result


def content_signature(snapshot):
    return digest({tech: sorted([original_row(r) for r in data['rows']], key=canonical)
                   for tech, data in sorted(snapshot['datasets'].items())})


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('source') != SOURCE or snapshot.get('schema_version') != 1 or snapshot.get('complete') is not True:
        raise ValueError('Invalid or incomplete inventory snapshot')
    if set(snapshot.get('datasets', {})) != set(DATASETS):
        raise ValueError('Both official datasets must be present')
    for tech, data in snapshot['datasets'].items():
        if data.get('dataset_id') != DATASETS[tech] or not isinstance(data.get('rows'), list):
            raise ValueError('Wrong dataset identity')
        if data.get('source_count') != len(data['rows']) or not data['rows']:
            raise ValueError('Inventory row accounting mismatch')
        expected = build_groups(tech, data['rows'])
        if data.get('groups') != expected:
            raise ValueError('Derived inventory groups differ from original rows')
    if snapshot.get('content_sha256') != content_signature(snapshot):
        raise ValueError('Snapshot content signature differs')


def reconcile(previous, current):
    validate_snapshot(current)
    new = {g['group_key']: g for d in current['datasets'].values() for g in d['groups']}
    if previous is None:
        return {'mode': 'BASELINE', 'groups_observed': len(new), 'newly_observed': [], 'changed': [],
                'not_seen': [], 'new_commercial_opportunities': 0, 'dated_events_created': 0}
    validate_snapshot(previous)
    old = {g['group_key']: g for d in previous['datasets'].values() for g in d['groups']}
    return {'mode': 'DELTA', 'groups_observed': len(new), 'newly_observed': sorted(new.keys() - old.keys()),
            'changed': sorted(k for k in new.keys() & old.keys() if new[k]['semantic_sha256'] != old[k]['semantic_sha256']),
            'not_seen': sorted(old.keys() - new.keys()), 'new_commercial_opportunities': 0, 'dated_events_created': 0}


class InventoryClient:
    def __init__(self, evidence_dir, *, session=None, page_size=500, pause=.15, timeout=40):
        if not 1 <= page_size <= 1000:
            raise ValueError('Page size must be between 1 and 1000')
        self.root = Path(evidence_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        if session is None:
            self.session.headers['User-Agent'] = 'SpainRenewablesRadar/0.6 (official inventory)'
        self.page_size, self.pause, self.timeout = page_size, pause, timeout
        self.acquisitions = []

    def get(self, url):
        official_url(url)
        for attempt in range(3):
            response = None
            try:
                # A changed endpoint or redirect is reviewed, never followed silently.
                response = self.session.get(url, timeout=(8, self.timeout), stream=True, allow_redirects=False)
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.exceptions.ConnectionError('Transient HTTP ' + str(response.status_code))
                if 300 <= response.status_code < 400:
                    raise ValueError('Source redirected; baseline not replaced')
                response.raise_for_status()
                parts, size = [], 0
                for part in response.iter_content(65536):
                    size += len(part)
                    if size > 5_000_000:
                        raise ValueError('Source response exceeds bounded size')
                    parts.append(part)
                raw = b''.join(parts)
                sha = hashlib.sha256(raw).hexdigest()
                (self.root / (sha + '.bin')).write_bytes(raw)
                self.acquisitions.append({'url': url, 'status': response.status_code, 'sha256': sha,
                                          'bytes': size, 'retrieved_at': utcnow(), 'attempt': attempt + 1})
                time.sleep(self.pause)
                return raw
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
                self.acquisitions.append({'url': url, 'attempt': attempt + 1, 'error': type(exc).__name__,
                                          'retrieved_at': utcnow()})
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
            finally:
                if response is not None:
                    response.close()
                atomic_json(self.root / 'acquisitions.json', self.acquisitions)
        raise RuntimeError('Unreachable retry state')

    def query(self, dataset, **params):
        return json.loads(self.get(API + '/resource/' + dataset + '.json?' + urlencode(params)))

    def metadata(self, dataset):
        data = json.loads(self.get(API + '/api/views/' + dataset + '.json'))
        if not isinstance(data, dict) or data.get('id') != dataset:
            raise ValueError('Wrong top-level metadata identity')
        columns = data.get('columns', [])
        fields = {c.get('fieldName') for c in columns}
        if not REQUIRED.issubset(fields) or type(data.get('rowsUpdatedAt')) is not int or data['rowsUpdatedAt'] <= 0:
            raise ValueError('Required fields or source version missing')
        types = {c.get('fieldName'): c.get('dataTypeName') for c in columns}
        if types.get('pot_ncia_mw') != 'number' or types.get('sol_licitud') != 'text':
            raise ValueError('Source quantity/reference column types changed')
        return {'dataset_id': dataset, 'title': data.get('name'), 'attribution': data.get('attribution'),
                'rows_updated_at': data['rowsUpdatedAt'],
                'columns': [{k: c.get(k) for k in ('fieldName', 'dataTypeName', 'description')} for c in columns if not c.get('fieldName', '').startswith(':')]}

    def count(self, dataset):
        data = self.query(dataset, **{'$select': 'count(*)'})
        if not isinstance(data, list) or len(data) != 1 or not re.fullmatch(r'\d+', str(data[0].get('count', ''))):
            raise ValueError('Invalid official count')
        count = int(data[0]['count'])
        if not 0 < count <= 100000:
            raise ValueError('Empty or unexpectedly large official inventory; review required')
        return count

    def collect(self):
        soup = BeautifulSoup(self.get(ORIGIN), 'html.parser')
        linked = {urlsplit(urljoin(ORIGIN, a['href'])).path.split('/')[-2] for a in soup.select('a[href]')
                  if urlsplit(urljoin(ORIGIN, a['href'])).hostname == 'analisi.transparenciacatalunya.cat' and a['href'].endswith('/about_data')}
        if not set(DATASETS.values()).issubset(linked):
            raise ValueError('Official environmental portal no longer links both inventories')
        snapshot = {'source': SOURCE, 'schema_version': 1, 'complete': False, 'retrieved_at': utcnow(),
                    'datasets': {}, 'dated_events_created': 0, 'unique_projects_certified': False}
        for technology, dataset in DATASETS.items():
            meta, count = self.metadata(dataset), self.count(dataset)
            rows, seen = [], set()
            for offset in range(0, count, self.page_size):
                page = self.query(dataset, **{'$select': ':id as socrata_row_id, *', '$order': ':id',
                                              '$limit': self.page_size, '$offset': offset})
                if not isinstance(page, list) or len(page) != min(self.page_size, count - offset):
                    raise ValueError('Truncated or inconsistent inventory page')
                for row in page:
                    sid = row.get('socrata_row_id') if isinstance(row, dict) else None
                    if not isinstance(sid, str) or not sid or sid in seen:
                        raise ValueError('Missing/duplicate source row ID across pages')
                    seen.add(sid)
                rows.extend(page)
            groups = build_groups(technology, rows)
            snapshot['datasets'][technology] = {'dataset_id': dataset, 'source_count': count,
                                                'metadata': meta, 'rows': rows, 'groups': groups}
        # Recheck both datasets after all acquisition, not just after each page.
        for data in snapshot['datasets'].values():
            dataset = data['dataset_id']
            if self.metadata(dataset) != data['metadata'] or self.count(dataset) != data['source_count']:
                raise ValueError('Source version/count changed during inventory acquisition')
        snapshot['complete'] = True
        snapshot['content_sha256'] = content_signature(snapshot)
        validate_snapshot(snapshot)
        return snapshot



def verify_evidence(snapshot, raw_dir):
    """Rebuild the inventory from the acquired page bytes, not parsed reports alone."""
    validate_snapshot(snapshot)
    root = Path(raw_dir)
    acquisitions = json.loads((root / 'acquisitions.json').read_text(encoding='utf-8'))
    reconstructed = {dataset: [] for dataset in DATASETS.values()}
    counts = defaultdict(list)
    versions = defaultdict(list)
    offsets = defaultdict(list)
    for acquisition in acquisitions:
        if acquisition.get('error'):
            continue
        url = official_url(acquisition['url'])
        sha = acquisition.get('sha256', '')
        if not re.fullmatch(r'[a-f0-9]{64}', sha):
            raise ValueError('Invalid original response hash')
        raw = (root / (sha + '.bin')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha or len(raw) != acquisition['bytes'] or acquisition['status'] != 200:
            raise ValueError('Original response integrity mismatch')
        retrieved = datetime.fromisoformat(acquisition['retrieved_at'])
        if retrieved.tzinfo is None:
            raise ValueError('Acquisition time lacks timezone')
        parts = urlsplit(url)
        dataset = Path(parts.path).stem
        if dataset not in reconstructed:
            continue
        payload = json.loads(raw)
        if parts.path.startswith('/api/views/'):
            if payload.get('id') != dataset:
                raise ValueError('Original metadata identity mismatch')
            versions[dataset].append(payload.get('rowsUpdatedAt'))
        else:
            query = parse_qs(parts.query)
            if query.get('$select') == ['count(*)']:
                counts[dataset].append(int(payload[0]['count']))
            elif query.get('$select') == [':id as socrata_row_id, *'] and query.get('$order') == [':id']:
                offsets[dataset].append((int(query['$offset'][0]), len(payload)))
                reconstructed[dataset].extend(payload)
            else:
                raise ValueError('Unexpected inventory query provenance')
    for data in snapshot['datasets'].values():
        dataset = data['dataset_id']
        if reconstructed[dataset] != data['rows']:
            raise ValueError('Snapshot rows differ from acquired pages')
        position = 0
        for offset, count in offsets[dataset]:
            if offset != position:
                raise ValueError('Missing or repeated inventory page')
            position += count
        if position != data['source_count'] or counts[dataset] != [position, position]:
            raise ValueError('Source count proofs incomplete')
        version = data['metadata']['rows_updated_at']
        if versions[dataset] != [version, version]:
            raise ValueError('Source version proofs incomplete')
    return True


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            name = stream.name
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@contextmanager
def state_lock(path):
    lock = Path(str(path) + '.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def safe_csv(value):
    value = '' if value is None else str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def write_report(root, snapshot, changes):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    groups = [g for d in snapshot['datasets'].values() for g in d['groups']]
    atomic_json(root / 'inventory.json', snapshot)
    atomic_json(root / 'changes.json', changes)
    metrics = {'source': SOURCE, 'retrieved_at': snapshot['retrieved_at'], 'complete': True,
               'content_sha256': snapshot['content_sha256'], 'mode': changes['mode'],
               'dated_events_created': 0, 'unique_projects_certified': False, 'datasets': {}}
    table = []
    with (root / 'inventory.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Tecnologia', 'Nome fonte', 'Riferimento', 'Stato fonte', 'MW nominali riportati', 'Superficie totale ha', 'Comuni', 'Province', 'Qualita'])
        for group in groups:
            row = [group['technology'], group['name'], group['reference'], '; '.join(group['source_states']),
                   group['reported_nominal_mw'], group['reported_total_area_ha'],
                   '; '.join(sorted({m['name'] for m in group['municipalities']})),
                   '; '.join(group['provinces']), '; '.join(group['quality_flags'])]
            writer.writerow([safe_csv(v) for v in row])
            table.append('<tr>' + ''.join('<td>' + html.escape('n.d.' if v is None else str(v)) + '</td>' for v in row) + '</tr>')
    for tech, data in snapshot['datasets'].items():
        gs = data['groups']
        metrics['datasets'][tech] = {'rows': len(data['rows']), 'diagnostic_groups': len(gs),
            'exact_reference_name_groups': sum(g['reference'] is not None for g in gs),
            'unresolved_reference_rows': sum(g['reference'] is None for g in gs),
            'multi_municipal_groups': sum(g['municipal_rows'] > 1 for g in gs),
            'groups_without_power': sum(g['reported_nominal_mw'] is None for g in gs),
            'flags': dict(Counter(f for g in gs for f in g['quality_flags'])),
            'dataset_updated_at': datetime.fromtimestamp(data['metadata']['rows_updated_at'], timezone.utc).isoformat()}
    atomic_json(root / 'metrics.json', metrics)
    title = 'Catalogna — inventario ufficiale degli impianti'
    page = '<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title>'
    page += '<style>body{font:16px system-ui;margin:2rem;line-height:1.5}table{border-collapse:collapse;font-size:14px}td,th{border:1px solid #ccc;padding:.6rem;text-align:left;vertical-align:top}th{background:#eee}input{font:inherit;padding:.5rem;width:min(90%,36rem)}.scroll{overflow:auto}</style>'
    page += '<h1>' + title + '</h1><p>Acquisizione: ' + html.escape(snapshot['retrieved_at']) + '. Modalità: ' + changes['mode'] + '.</p>'
    page += '<p><strong>Inventario, non elenco di nuovi cantieri.</strong> Le righe possono rappresentare comuni dello stesso impianto. I raggruppamenti sono diagnostici: nessun censimento di progetti unici è certificato. Le potenze ripetute non sono sommate. Gli zeri originali e i conflitti sono conservati.</p>'
    page += '<p>Stato dichiarato dalla fonte e data della riunione ambientale non attestano una nuova autorizzazione. Nessuna data di pubblicazione o di lavori, nessun EPC è dedotto. La prima acquisizione è una baseline; una voce non più osservata non equivale a rinuncia.</p>'
    page += '<p><a href="inventory.csv">CSV</a> · <a href="inventory.json">Originali strutturati e gruppi</a> · <a href="changes.json">Variazioni</a> · <a href="metrics.json">Controlli</a></p><label>Cerca nome, comune o riferimento <input id="q" type="search"></label>'
    page += '<div class="scroll"><table id="data"><thead><tr>' + ''.join('<th>' + h + '</th>' for h in ['Tecnologia','Nome fonte','Riferimento','Stato fonte','MW nominali riportati','Superficie totale ha','Comuni','Province','Qualità']) + '</tr></thead><tbody>' + ''.join(table) + '</tbody></table></div>'
    page += '<script>document.getElementById("q").addEventListener("input",e=>{const q=e.target.value.toLocaleLowerCase();for(const r of document.querySelectorAll("tbody tr")){r.hidden=!r.textContent.toLocaleLowerCase().includes(q);}});</script></html>'
    (root / 'index.html').write_text(page, encoding='utf-8')
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='reports/catalunya_inventory')
    parser.add_argument('--baseline', default='data/catalunya_inventory_baseline.json')
    parser.add_argument('--page-size', type=int, default=500)
    args = parser.parse_args()
    output, baseline = Path(args.output), Path(args.baseline)
    output.mkdir(parents=True, exist_ok=True)
    generation = output / 'snapshots' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    with state_lock(baseline):
        baseline_replaced = False
        try:
            previous = json.loads(baseline.read_text(encoding='utf-8')) if baseline.exists() else None
            if previous is not None:
                validate_snapshot(previous)
            current = InventoryClient(generation / 'raw', page_size=args.page_size).collect()
            verify_evidence(current, generation / 'raw')
            changes = reconcile(previous, current)
            replay = reconcile(current, current)
            if any(replay[k] for k in ('newly_observed', 'changed', 'not_seen')):
                raise ValueError('Snapshot replay is not idempotent')
            metrics = write_report(generation, current, changes)
            metrics['idempotent_replay'] = True
            atomic_json(generation / 'metrics.json', metrics)
            atomic_json(baseline, current)
            baseline_replaced = True
            atomic_json(output / 'latest.json', {'snapshot_dir': str(generation.relative_to(output)), 'metrics': metrics})
            relative = generation.relative_to(output).as_posix() + '/index.html'
            (output / 'index.html').write_text('<!doctype html><html lang="it"><meta charset="utf-8"><title>Inventario Catalogna</title><h1>Inventario Catalogna</h1><p><a href="' + relative + '">Apri l’ultima acquisizione verificata</a></p><p><a href="run_status.json">Esito dell’ultimo tentativo</a></p></html>', encoding='utf-8')
            atomic_json(output / 'run_status.json', {'status': 'SUCCESS', 'checked_at': utcnow(), 'snapshot_dir': str(generation.relative_to(output))})
            print('CATALUNYA_INVENTORY', json.dumps(metrics, ensure_ascii=False), flush=True)
            print('CATALUNYA_CHANGES', json.dumps(changes, ensure_ascii=False), flush=True)
        except Exception as exc:
            atomic_json(output / 'run_status.json', {'status': 'ERROR', 'checked_at': utcnow(), 'error_type': type(exc).__name__, 'error': str(exc), 'baseline_replaced': baseline_replaced})
            raise


if __name__ == '__main__':
    main()
