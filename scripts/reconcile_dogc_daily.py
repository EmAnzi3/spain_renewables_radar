"""Complete DOGC indexes using bounded single-response daily searches.

Monthly offset pagination has returned overlapping rows. The alternative is the
same public date search, partitioned into disjoint calendar days, with each day's
entire result in one response. The declared count, every identity, publication
date and title must agree with the edition/annex summaries, on two live passes.
This module creates no project or lifecycle event and enables no collector.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import uuid
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from app.catalunya_inventory import atomic_json, canonical
from scripts.audit_dogc_index import (
    Client, ENERGY, WEB, compare_indexes as exact_compare_indexes, one_parameter, parse_calendar,
    parse_search, parse_summary, plain_title, search_parameters, source_date,
    summary_scopes,
)

# This is a bounded request, not a silent limit or a claim about a service cap.
# An ignored page size or a count above the bound is an error, never truncation.
DAILY_LIMIT = 1000


def daily_parameters(day: date) -> dict:
    parameters = search_parameters(day, day, 1)
    parameters['numResultsByPage'] = str(DAILY_LIMIT)
    return parameters


def parse_complete_day(data: dict, day: date) -> dict:
    if not isinstance(data, dict) or data.get('error') or data.get('errorCode'):
        raise ValueError('Daily search application error')
    total = data.get('numResultSearch')
    if type(total) is not int or not 0 <= total <= DAILY_LIMIT:
        raise ValueError('Daily total absent, invalid or above the bounded request')
    rows = data.get('resultSearch')
    # Explicit authoritative zero may be serialized without a result array.
    if total == 0 and rows is None:
        rows = []
    if not isinstance(rows, list) or len(rows) != total:
        raise ValueError(f'Incomplete daily response: declared={total}, received={len(rows) if isinstance(rows, list) else None}')
    records = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Malformed daily disposition')
        identity = row.get('idDocument')
        if not isinstance(identity, str) or not re.fullmatch(r'\d+', identity) or row.get('tipusDiari') != 'DOGC':
            raise ValueError('Unexpected daily identity or journal')
        if source_date(row.get('date')) != day:
            raise ValueError('Daily search returned another publication day')
        link = row.get('linkTitle')
        if not isinstance(link, str) or not link.startswith('?') or one_parameter(link, 'documentId') != identity:
            raise ValueError('Daily identity differs from its official link')
        key = (identity, day.isoformat())
        if key in records:
            raise ValueError('Duplicate disposition within a complete daily response')
        records[key] = {'document_id': identity, 'publication_date': day.isoformat(),
                        'title': plain_title(row.get('title')), 'source_record': row}
    return records


def comparison_title(value: str) -> str:
    # Display typography only: no lowercasing, punctuation deletion, accent
    # removal, fuzzy similarity or substitution of administrative terms/numbers.
    return unicodedata.normalize('NFC', value).translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'}))


def compare_indexes(left: dict, right: dict) -> dict:
    differences = exact_compare_indexes(left, right)
    typographic = [key for key in differences['title_conflicts']
                   if comparison_title(left[key]['title']) == comparison_title(right[key]['title'])]
    differences['title_conflicts'] = [key for key in differences['title_conflicts'] if key not in typographic]
    differences['typographic_variants'] = [{'key': key, 'summary_title': left[key]['title'],
                                          'search_title': right[key]['title']} for key in typographic]
    return differences


def semantic_index(records: dict) -> list:
    return sorted((key[0], key[1], comparison_title(value['title'])) for key, value in records.items())


def require_same_index(left: dict, right: dict) -> None:
    differences = compare_indexes(left, right)
    if any(differences[key] for key in ('only_in_edition_summaries', 'only_in_search', 'title_conflicts')):
        raise ValueError('Index mismatch: ' + canonical(differences))


def window_days(end: date, today: date) -> list[date]:
    if end >= today:
        raise ValueError('Only complete Spanish calendar days can be audited')
    return [end - timedelta(days=n) for n in range(29, -1, -1)]


def verify_contract(client: Client) -> None:
    home = BeautifulSoup(client.request('contract:home', WEB + '/ca/inici/'), 'html.parser')
    scripts = {Path(urlsplit(t['src']).path).name: urljoin(WEB, t['src']) for t in home.select('script[src]')}
    constants = client.request('contract:constants', scripts['constants.js']).decode('utf-8')
    host = re.search(r'\bHOST_PRO\s*=\s*[\x27\x22]([^\x27\x22]+)', constants)
    inputs = {t.get('id'): t.get('value') for t in home.select('input[id]')}
    if not host or host[1] != 'portaldogc.gencat.cat':
        raise ValueError('Official production host changed')
    if inputs.get('uriCalendar') != '/eadop-rest/api/dogc/calendarDOGC' or inputs.get('uriCerDogc') != '/eadop-rest/api/dogc/searchDOGC':
        raise ValueError('Official service routes changed')


def acquire_pass(client: Client, days: list[date], pass_number: int, root: Path) -> dict:
    start, end = days[0], days[-1]
    calendar_days, summaries, search, annex_ids, day_metrics = {}, {}, {}, [], []
    # A monthly search supplies a separately checked total, not monthly coverage.
    total, _ = parse_search(client.post(f'monthly:{pass_number}', 'searchDOGC',
                            payload=search_parameters(start, end, 1)), start, end, 1)
    for year, month in sorted({(day.year, day.month) for day in days}):
        response = client.post(f'calendar:{pass_number}:{year}:{month}', 'calendarDOGC',
                               form={'year': year, 'month': month, 'language': 'ca'})
        parsed = parse_calendar(response, year, month)
        calendar_days.update({day: edition for day, edition in parsed.items() if start <= day <= end})
    if set(calendar_days) != set(days):
        raise ValueError('Calendar does not account for all thirty days')
    for day in days:
        edition = calendar_days[day]
        entries = {}
        if edition is not None:
            response = client.post(f'edition:{pass_number}:{day}', 'summaryDOGC',
                                   form={'numDOGC': edition, 'language': 'ca'})
            entries = parse_summary(response, edition, day)
            annex_ids.extend(scope for scope, _ in summary_scopes(response, edition, day) if scope != edition)
        response = client.post(f'daily:{pass_number}:{day}', 'searchDOGC', payload=daily_parameters(day))
        daily = parse_complete_day(response, day)
        differences = compare_indexes(entries, daily)
        atomic_json(root / f'differences-{pass_number}-{day}.json', differences)
        require_same_index(entries, daily)
        if set(entries) & set(summaries) or set(daily) & set(search):
            raise ValueError('Daily partitions overlap')
        summaries.update(entries)
        search.update(daily)
        metric = {'date': str(day), 'edition': edition, 'summary_rows': len(entries),
                  'search_rows': len(daily), 'search_declared_total': response['numResultSearch'],
                  'single_response_complete': True, 'typographic_title_variants': len(differences['typographic_variants'])}
        day_metrics.append(metric)
        print('DOGC_DAILY_RECONCILED', json.dumps(dict(metric, pass_number=pass_number)), flush=True)
    if len(summaries) != total or len(search) != total:
        raise ValueError(f'Monthly/daily totals disagree: monthly={total}, summaries={len(summaries)}, daily={len(search)}')
    require_same_index(summaries, search)
    atomic_json(root / f'edition_index-{pass_number}.json', list(summaries.values()))
    atomic_json(root / f'search_index-{pass_number}.json', list(search.values()))
    return {'summaries': summaries, 'search': search, 'calendar': calendar_days,
            'annex_ids': sorted(annex_ids), 'days': day_metrics, 'monthly_total': total}


def verify_originals(root: Path, first: dict, second: dict) -> None:
    manifest = json.loads((root / 'acquisitions.json').read_text(encoding='utf-8'))
    labels, rebuilt = set(), {1: {'edition': {}, 'daily': {}}, 2: {'edition': {}, 'daily': {}}}
    for item in manifest:
        label = item['label']
        if label in labels:
            raise ValueError('Duplicate acquisition label')
        labels.add(label)
        sha = item['sha256']
        if not re.fullmatch(r'[0-9a-f]{64}', sha):
            raise ValueError('Invalid original file identity')
        raw = (root / (sha + '.bin')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha or len(raw) != item['bytes'] or item['status'] != 200:
            raise ValueError('Original acquisition integrity failure')
        stamp = datetime.fromisoformat(item['retrieved_at'])
        if stamp.tzinfo is None:
            raise ValueError('Original acquisition lacks timezone')
        match = re.fullmatch(r'(edition|daily):([12]):(\d{4}-\d{2}-\d{2})', label)
        if not match:
            continue
        kind, num, day = match[1], int(match[2]), date.fromisoformat(match[3])
        observed = (first, second)[num - 1]
        expected = ({'numDOGC': observed['calendar'][day], 'language': 'ca'} if kind == 'edition' else daily_parameters(day))
        route = 'summaryDOGC' if kind == 'edition' else 'searchDOGC'
        if item['parameters'] != expected or item['method'] != 'POST' or item['url'] != 'https://portaldogc.gencat.cat/eadop-rest/api/dogc/' + route:
            raise ValueError('Original request provenance does not match its daily scope')
        data = json.loads(raw)
        records = parse_summary(data, observed['calendar'][day], day) if kind == 'edition' else parse_complete_day(data, day)
        if set(rebuilt[num][kind]) & set(records):
            raise ValueError('Replay duplicates a daily partition')
        rebuilt[num][kind].update(records)
    for num, observed in enumerate((first, second), 1):
        for day, edition in observed['calendar'].items():
            if f'daily:{num}:{day}' not in labels or (edition is not None and f'edition:{num}:{day}' not in labels):
                raise ValueError('Missing original evidence for an audited day')
        if rebuilt[num]['edition'] != observed['summaries'] or rebuilt[num]['daily'] != observed['search']:
            raise ValueError('Replay from original bytes differs from observed indexes')


def render_index(root: Path, result: dict, candidates: list[dict]) -> None:
    rows = ''.join('<tr><td>' + html.escape(row['publication_date']) + '</td><td>' +
                   html.escape(row['edition']) + '</td><td>' + html.escape(row['title']) +
                   '</td><td><a rel="noreferrer" href="' + html.escape(row['source_url'], quote=True) +
                   '">Atto ufficiale</a></td></tr>' for row in candidates)
    text = '<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DOGC — indice riconciliato</title><style>body{font:16px/1.5 system-ui;max-width:1200px;margin:auto;padding:24px}td,th{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid}table{border-collapse:collapse;width:100%}</style><h1>DOGC — indice riconciliato</h1><p>' + html.escape(result['window_start'] + ' — ' + result['window_end']) + '</p><p>' + str(result['dispositions']) + ' disposizioni ufficiali confrontate tra calendario/sommari e ricerca giornaliera, con due acquisizioni live complete. ' + str(len(candidates)) + ' titoli candidati da verificare: non sono ancora progetti validati. Testi integrali non acquisiti; nessun evento inserito nel radar.</p><table><thead><tr><th>Pubblicazione</th><th>Edizione</th><th>Titolo originale</th><th>Fonte</th></tr></thead><tbody>' + rows + '</tbody></table></html>'
    (root / 'index.html').write_text(text, encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--until')
    parser.add_argument('--output', default='reports/dogc_daily_index')
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    generation = root / 'snapshots' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    generation.mkdir(parents=True)
    today = datetime.now(ZoneInfo('Europe/Madrid')).date()
    end = date.fromisoformat(args.until) if args.until else today - timedelta(days=1)
    days = window_days(end, today)
    client = Client(generation / 'raw')
    result = {'head_sha': os.getenv('GITHUB_SHA'), 'run_id': os.getenv('GITHUB_RUN_ID'),
              'window_start': str(days[0]), 'window_end': str(days[-1]),
              'dated_collector_enabled': False, 'project_events_created': 0,
              'document_bodies_acquired': 0, 'index_complete': False,
              'generation': str(generation.relative_to(root)), 'daily_request_limit': DAILY_LIMIT}
    try:
        verify_contract(client)
        first = acquire_pass(client, days, 1, generation)
        second = acquire_pass(client, days, 2, generation)
        if first['calendar'] != second['calendar'] or first['annex_ids'] != second['annex_ids']:
            raise ValueError('Calendar or annex scope changed between live passes')
        require_same_index(first['summaries'], second['summaries'])
        require_same_index(first['search'], second['search'])
        verify_originals(client.root, first, second)
        candidates = [dict(row, review_status='UNREVIEWED_TITLE_CANDIDATE') for row in second['summaries'].values() if ENERGY.search(row['title'])]
        result.update(index_complete=True, source_days=len(days), independent_live_passes=2,
                      dispositions=len(second['summaries']), monthly_search_total=second['monthly_total'],
                      publication_editions=sum(e is not None for e in second['calendar'].values()),
                      no_edition_days=sum(e is None for e in second['calendar'].values()),
                      annex_editions=second['annex_ids'], daily_search_responses=60,
                      title_candidates=len(candidates), independent_index_reconciliation=True,
                      original_byte_replay_verified=True, semantic_changes_between_passes=0,
                      missing_dispositions=0, extra_dispositions=0, title_conflicts=0,
                      typographic_title_variants=sum(day['typographic_title_variants'] for day in second['days']),
                      title_comparison_rule='NFC and typographic apostrophes/quotes only; originals retained',
                      index_sha256=hashlib.sha256(canonical(semantic_index(second['summaries'])).encode()).hexdigest())
        atomic_json(generation / 'candidates.json', candidates)
        atomic_json(generation / 'day_metrics.json', second['days'])
        render_index(generation, result, candidates)
        atomic_json(root / 'latest.json', {'generation': result['generation']})
        (root / 'index.html').write_text((generation / 'index.html').read_text(encoding='utf-8'), encoding='utf-8')
        for candidate in candidates:
            print('DOGC_TITLE_CANDIDATE', json.dumps(candidate, ensure_ascii=False), flush=True)
        print('DOGC_DAILY_CERTIFIED', json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as exc:
        result.update(index_complete=False, error_type=type(exc).__name__, error=str(exc))
        print('DOGC_DAILY_FAILED', json.dumps(result, ensure_ascii=False), flush=True)
        raise
    finally:
        client.session.close()
        atomic_json(generation / 'audit.json', result)
        atomic_json(root / 'audit.json', result)


if __name__ == '__main__':
    main()
