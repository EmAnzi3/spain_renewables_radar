"""Complete live Andalucía catalogue; offline exports are not live-count snapshots.

The official API exposes count and ordered search, but no documented offset.
Two overlapping, oppositely ordered bounded results cover the entire identity
set. Counts, order, uniqueness and identical overlapping originals must agree.
No event, lifecycle, publication date or project value is inferred here.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

API = 'https://datos.juntadeandalucia.es/api/v0/public-documents'
MAX_CATALOGUE = 19000
MAX_RESPONSE_BYTES = 30_000_000
MODE = 'COMPLETE_ORDERED_PREFIX_SUFFIX'


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def count_value(data) -> int:
    value = data.get('count', {}).get('result') if isinstance(data, dict) and isinstance(data.get('count'), dict) else None
    if type(value) is not int or not 0 < value <= MAX_CATALOGUE:
        raise ValueError('Invalid or out-of-bound live catalogue count')
    return value


def search_parameters(count: int, mode: str) -> dict:
    count_value({'count': {'result': count}})
    if mode not in {'ASC', 'DESC'}:
        raise ValueError('Invalid source sort mode')
    return {'organism': '-', 'themes': '-', 'counseling': '-', 'title': '-',
            'order_by': 'id', 'format': 'json', 'size': min(count, (count + 1)//2 + 100), 'mode': mode}


def validate_contract(spec) -> None:
    try:
        paths = spec['paths']
        parameters = paths['/api/v0/public-documents/search']['get']['parameters']
        if 'get' not in paths['/api/v0/public-documents/count']:
            raise ValueError('Count operation missing')
        names = {p['name'] for p in parameters if p['in'] == 'query'}
        if not set(search_parameters(1, 'ASC')) <= names:
            raise ValueError('Required search parameters missing')
        schemas = spec['components']['schemas']
        for schema, values in {'_Enum_Mode': {'ASC', 'DESC'}, '_Enum_fields': {'id'},
                               '_Enum_Organisms': {'-'}, '_Enum_Themes': {'-'},
                               '_Enum_Counselings': {'-'}}.items():
            if not values <= set(schemas[schema]['enum']):
                raise ValueError('Required official option missing: ' + schema)
    except (KeyError, TypeError) as exc:
        raise ValueError('Official live search contract changed') from exc


def parse_part(data, count: int, mode: str) -> dict[str, dict]:
    size = search_parameters(count, mode)['size']
    if (not isinstance(data, dict) or type(data.get('hits')) is not int or
            type(data.get('total_hits')) is not int or data['hits'] != size or data['total_hits'] != count):
        raise ValueError('Search count/total differs from the requested complete partition')
    rows = data.get('results')
    if not isinstance(rows, list) or len(rows) != size:
        raise ValueError('Search partition truncated or malformed')
    ids = []
    for row in rows:
        identity = row.get('id') if isinstance(row, dict) else None
        if not isinstance(identity, str) or not re.fullmatch(r'[0-9]+', identity):
            raise ValueError('Unexpected official string identity')
        ids.append(identity)
    # The observed official keyword sort is lexical, not numeric. Never coerce IDs.
    if len(set(ids)) != size or ids != sorted(ids, reverse=mode == 'DESC'):
        raise ValueError('Search identity order or uniqueness failed')
    return dict(zip(ids, rows))


def reconcile(before, ascending, descending, after) -> tuple[list[dict], dict]:
    count = count_value(before)
    if count_value(after) != count:
        raise ValueError('Live catalogue changed during acquisition')
    a, b = parse_part(ascending, count, 'ASC'), parse_part(descending, count, 'DESC')
    union, overlap = set(a) | set(b), set(a) & set(b)
    if len(union) != count:
        raise ValueError('Full catalogue identity union does not match the official total')
    if any(a[key] != b[key] for key in overlap):
        raise ValueError('Original overlapping records changed between requests')
    combined = dict(a); combined.update(b)
    records = [combined[key] for key in sorted(combined)]
    return records, {'mode': MODE, 'expected_records': count, 'archive_records': len(records),
                     'overlap_checked': len(overlap), 'partition_size': len(a),
                     'first_id': records[0]['id'], 'last_id': records[-1]['id']}


def acquire_catalogue(session, output: Path, timeout=(10, 90)) -> tuple[list[dict], dict]:
    """Fresh live read; bounded transport; originals and failures retained separately."""
    root = Path(output) / 'live_catalogue' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    manifest = []
    state = {'complete': False, 'mode': MODE}

    def fetch(label: str, endpoint: str, parameters=None):
        if endpoint not in {'openapi.json', 'count', 'search'}:
            raise ValueError('Unsupported catalogue endpoint')
        for attempt in (1, 2):
            response = None; chunks = []; size = 0
            observation = {'label': label, 'attempt': attempt, 'url': API + '/' + endpoint,
                           'parameters': parameters, 'method': 'GET', 'complete': False,
                           'started_at': datetime.now(timezone.utc).isoformat()}
            try:
                response = session.get(observation['url'], params=parameters, timeout=timeout,
                                       stream=True, allow_redirects=False)
                observation['status'] = response.status_code
                if 300 <= response.status_code < 400:
                    raise ValueError('Unexpected live API redirect; contract review required')
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Unexpected live API status')
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise ValueError('Source response exceeds bounded byte limit')
                    chunks.append(chunk)
                raw = b''.join(chunks)
                digest = hashlib.sha256(raw).hexdigest()
                (root / (digest + '.json')).write_bytes(raw)
                observation.update(sha256=digest, bytes=len(raw), file=digest + '.json',
                                   retrieved_at=datetime.now(timezone.utc).isoformat())
                data = json.loads(raw)
                observation['complete'] = True
                return data
            except Exception as exc:
                observation.update(error_type=type(exc).__name__, error=str(exc), received_bytes=size)
                if chunks and 'file' not in observation:
                    raw = b''.join(chunks); digest = hashlib.sha256(raw).hexdigest()
                    (root / (digest + '.partial')).write_bytes(raw)
                    observation['partial_file'] = digest + '.partial'
                transient = (isinstance(exc, (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)) or
                             (isinstance(exc, requests.HTTPError) and response is not None and response.status_code in (500,502,503,504)))
                if isinstance(exc, requests.exceptions.SSLError) or not transient or attempt == 2:
                    raise
                time.sleep(1)
            finally:
                if response is not None:
                    response.close()
                manifest.append(observation)
                write_json(root / 'manifest.json', manifest)
        raise RuntimeError('Unreachable retry branch')

    try:
        validate_contract(fetch('contract', 'openapi.json'))
        before = fetch('count-before', 'count'); count = count_value(before)
        ascending = fetch('ordered-asc', 'search', search_parameters(count, 'ASC'))
        descending = fetch('ordered-desc', 'search', search_parameters(count, 'DESC'))
        after = fetch('count-after', 'count')
        records, metrics = reconcile(before, ascending, descending, after)
        write_json(root / 'catalogue.json', records)
        raw = (root / 'catalogue.json').read_bytes()
        state.update(metrics, complete=True, source_url=API + '/search',
                     assembled_sha256=hashlib.sha256(raw).hexdigest(),
                     acquisition_started_at=manifest[0]['started_at'], retrieved_at=manifest[-1]['retrieved_at'],
                     source_bytes_preserved=True, acquisition_scope='LIVE_ORDERED_SEARCH_NOT_OFFLINE_EXPORT')
        return records, dict(state, catalogue_generation=str(root.relative_to(output)))
    except Exception as exc:
        state.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        write_json(root / 'audit.json', state)


def replay_catalogue(output: Path, audit: dict) -> list[dict]:
    """Rebuild all records from response bytes and verify request provenance."""
    output = Path(output).resolve()
    relative = audit.get('catalogue_generation')
    if not isinstance(relative, str) or not re.fullmatch(r'live_catalogue/[0-9TZ]+-[a-f0-9]{8}', relative):
        raise ValueError('Invalid catalogue evidence path')
    root = (output / relative).resolve()
    if not root.is_relative_to(output):
        raise ValueError('Catalogue evidence outside its root')
    state = json.loads((root / 'audit.json').read_text())
    if not state.get('complete') or state.get('mode') != MODE:
        raise ValueError('Live catalogue acquisition is incomplete')
    manifest = json.loads((root / 'manifest.json').read_text())
    complete = {}
    for meta in manifest:
        if not meta.get('complete'):
            continue
        label, digest = meta['label'], meta['sha256']
        if label in complete or not re.fullmatch(r'[a-f0-9]{64}', digest) or meta['file'] != digest + '.json':
            raise ValueError('Ambiguous catalogue response evidence')
        raw = (root / meta['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest or len(raw) != meta['bytes'] or meta['status'] != 200:
            raise ValueError('Catalogue original byte integrity failure')
        if datetime.fromisoformat(meta['retrieved_at']).tzinfo is None:
            raise ValueError('Original source retrieval timestamp lacks timezone')
        complete[label] = (meta, json.loads(raw))
    if set(complete) != {'contract', 'count-before', 'ordered-asc', 'ordered-desc', 'count-after'}:
        raise ValueError('Incomplete catalogue original response set')
    count = count_value(complete['count-before'][1])
    for label, (meta, _) in complete.items():
        endpoint = 'openapi.json' if label == 'contract' else 'search' if label.startswith('ordered-') else 'count'
        params = search_parameters(count, 'ASC' if label == 'ordered-asc' else 'DESC') if endpoint == 'search' else None
        if meta['url'] != API + '/' + endpoint or meta['parameters'] != params or meta['method'] != 'GET':
            raise ValueError('Catalogue original request provenance changed')
    validate_contract(complete['contract'][1])
    records, metrics = reconcile(*(complete[label][1] for label in ('count-before','ordered-asc','ordered-desc','count-after')))
    raw = (root / 'catalogue.json').read_bytes()
    if records != json.loads(raw) or hashlib.sha256(raw).hexdigest() != state['assembled_sha256']:
        raise ValueError('Assembled catalogue differs from original responses')
    for key, value in metrics.items():
        if state.get(key) != value or audit.get(key) != value:
            raise ValueError('Catalogue audit metric mismatch: ' + key)
    if audit.get('retrieved_at') != complete['count-after'][0]['retrieved_at']:
        raise ValueError('Catalogue source timestamp was replaced')
    return records
