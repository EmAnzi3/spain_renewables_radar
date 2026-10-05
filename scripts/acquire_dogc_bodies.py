"""Acquire candidate DOGC PDFs only from an independently verified index.

This is evidence acquisition, not permit/project interpretation. Original PDFs
and every extracted page are retained. No database, lifecycle or registry writes.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests
from pypdf import PdfReader
from app.catalunya_inventory import atomic_json, canonical
from scripts.audit_dogc_index import ENERGY, parse_calendar, parse_search, parse_summary, summary_scopes
from scripts.reconcile_dogc_daily import (daily_parameters, parse_complete_day, require_same_index,
                                          semantic_index, verify_originals, window_days)
from scripts.probe_dogc_services import SERVICE, VerifiedDOGCTLSAdapter

MAX_PDF_BYTES = 20_000_000
MAX_CANDIDATES = 250
HEADER = re.compile(r'N[úu]m\.?\s*(\d+[A-Z]?)\s*[-–—]\s*(\d{1,2})[./](\d{1,2})[./](\d{4})', re.I)


def index_generation(root: Path) -> Path:
    relative = json.loads((root / 'latest.json').read_text(encoding='utf-8')).get('generation')
    if not isinstance(relative, str) or not re.fullmatch(r'snapshots/[A-Za-z0-9-]+', relative):
        raise ValueError('Invalid index generation path')
    generation = (root / relative).resolve()
    if not generation.is_relative_to(root.resolve()) or not generation.is_dir():
        raise ValueError('Index generation outside evidence root or missing')
    return generation


def load_verified_index(root: Path, expected_run: str) -> tuple[dict, list[dict]]:
    generation = index_generation(root)
    audit = json.loads((generation / 'audit.json').read_text(encoding='utf-8'))
    if (audit.get('run_id') != expected_run or audit.get('index_complete') is not True
            or audit.get('independent_live_passes') != 2
            or audit.get('original_byte_replay_verified') is not True
            or audit.get('independent_index_reconciliation') is not True):
        raise ValueError('Input is not the requested complete certified index')
    end = date.fromisoformat(audit['window_end'])
    days = window_days(end, end + timedelta(days=1))
    if str(days[0]) != audit['window_start']:
        raise ValueError('Input window is not thirty complete days')
    manifest = json.loads((generation / 'raw/acquisitions.json').read_text(encoding='utf-8'))
    labels = {}
    for item in manifest:
        label, sha = item.get('label'), item.get('sha256')
        if not isinstance(label, str) or label in labels or not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
            raise ValueError('Ambiguous original acquisition identity')
        raw = (generation / 'raw' / (sha + '.bin')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha or len(raw) != item['bytes'] or item['status'] != 200:
            raise ValueError('Index original bytes fail integrity')
        labels[label] = (item, raw)
    def response(label, route, parameters):
        item, raw = labels[label]
        if item['method'] != 'POST' or item['url'] != SERVICE + '/eadop-rest/api/dogc/' + route or item['parameters'] != parameters:
            raise ValueError('Index request provenance mismatch')
        return json.loads(raw)
    from scripts.audit_dogc_index import search_parameters
    passes = []
    for number in (1, 2):
        calendars, summaries, search, annexes = {}, {}, {}, []
        for year, month in sorted({(day.year, day.month) for day in days}):
            data = response(f'calendar:{number}:{year}:{month}', 'calendarDOGC', {'year': year, 'month': month, 'language': 'ca'})
            calendars.update({d: e for d, e in parse_calendar(data, year, month).items() if d in days})
        if set(calendars) != set(days):
            raise ValueError('Input calendar evidence omits a day')
        for day in days:
            edition = calendars[day]
            entries = {}
            if edition is not None:
                data = response(f'edition:{number}:{day}', 'summaryDOGC', {'numDOGC': edition, 'language': 'ca'})
                entries = parse_summary(data, edition, day)
                annexes.extend(scope for scope, _ in summary_scopes(data, edition, day) if scope != edition)
            daily = parse_complete_day(response(f'daily:{number}:{day}', 'searchDOGC', daily_parameters(day)), day)
            require_same_index(entries, daily)
            if set(entries) & set(summaries) or set(daily) & set(search):
                raise ValueError('Index daily partitions overlap')
            summaries.update(entries); search.update(daily)
        total, _ = parse_search(response(f'monthly:{number}', 'searchDOGC', search_parameters(days[0], end, 1)), days[0], end, 1)
        if total != len(summaries) or total != len(search) or total != audit['dispositions']:
            raise ValueError('Index source counts disagree')
        passes.append({'calendar': calendars, 'summaries': summaries, 'search': search, 'annex_ids': sorted(annexes)})
    first, second = passes
    if first['calendar'] != second['calendar'] or first['annex_ids'] != second['annex_ids']:
        raise ValueError('Index live passes have different calendar/annex scopes')
    require_same_index(first['summaries'], second['summaries'])
    require_same_index(first['search'], second['search'])
    verify_originals(generation / 'raw', first, second)
    digest = hashlib.sha256(canonical(semantic_index(second['summaries'])).encode()).hexdigest()
    if digest != audit['index_sha256'] or second['annex_ids'] != audit['annex_editions']:
        raise ValueError('Certified index digest/scope differs from original bytes')
    candidates = [dict(row, review_status='UNREVIEWED_TITLE_CANDIDATE') for row in second['summaries'].values() if ENERGY.search(row['title'])]
    saved = json.loads((generation / 'candidates.json').read_text(encoding='utf-8'))
    if candidates != saved or len(candidates) != audit['title_candidates'] or len(candidates) > MAX_CANDIDATES:
        raise ValueError('Candidate list is corrupted or above the bounded acquisition')
    return audit, candidates


def validate_document_url(url: str, identity: str) -> None:
    p = urlsplit(url); q = parse_qs(p.query)
    if (p.scheme != 'https' or p.hostname != 'portaldogc.gencat.cat' or p.port not in (None, 443)
            or p.username or p.password or p.fragment
            or p.path != '/utilsEADOP/AppJava/PdfProviderServlet'
            or q.get('documentId') != [identity] or q.get('type') != ['01'] or q.get('language') != ['ca_ES']
            or set(q) != {'documentId', 'type', 'language'}
            or not re.fullmatch(r'\d+', identity)):
        raise ValueError('Document URL does not match the original certified identity')


class BodyClient:
    def __init__(self, root: Path):
        self.root = root; root.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.mount(SERVICE + '/', VerifiedDOGCTLSAdapter())
        self.session.headers['User-Agent'] = 'SpainRenewablesRadar/0.6 (official DOGC evidence acquisition)'
        self.observations = []

    def get_pdf(self, candidate: dict) -> tuple[bytes, dict]:
        identity, url = candidate['document_id'], candidate['source_url']
        validate_document_url(url, identity)
        for attempt in range(1, 3):
            response = None; chunks = []; size = 0
            observation = {'document_id': identity, 'url': url, 'attempt': attempt,
                           'started_at': datetime.now(timezone.utc).isoformat(), 'complete': False}
            try:
                response = self.session.get(url, timeout=(8, 40), stream=True, allow_redirects=False)
                observation['status'] = response.status_code
                # Redirects require explicit new source-contract verification, not blind following.
                if 300 <= response.status_code < 400:
                    observation['location'] = response.headers.get('Location')
                    raise ValueError('PDF endpoint redirected; review the original location before contacting it')
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Unexpected PDF success status')
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise ValueError('PDF exceeds bounded byte limit')
                    chunks.append(chunk)
                raw = b''.join(chunks)
                if not raw.lstrip().startswith(b'%PDF-') or b'%%EOF' not in raw[-4096:]:
                    raise ValueError('Response is not a complete PDF document')
                sha = hashlib.sha256(raw).hexdigest()
                (self.root / (sha + '.pdf')).write_bytes(raw)
                observation.update(complete=True, bytes=len(raw), sha256=sha,
                                   content_type=response.headers.get('Content-Type'),
                                   retrieved_at=datetime.now(timezone.utc).isoformat())
                return raw, observation
            except Exception as exc:
                observation.update(error_type=type(exc).__name__, error=str(exc), received_bytes=size)
                if chunks:
                    partial = b''.join(chunks); sha = hashlib.sha256(partial).hexdigest()
                    (self.root / (sha + '.partial')).write_bytes(partial)
                    observation['partial_sha256'] = sha
                transient = (isinstance(exc, (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError))
                             or (isinstance(exc, requests.HTTPError) and response is not None and response.status_code in (500, 502, 503, 504)))
                if isinstance(exc, requests.exceptions.SSLError) or not transient or attempt == 2:
                    raise
                time.sleep(1)
            finally:
                if response is not None: response.close()
                self.observations.append(dict(observation))
                atomic_json(self.root / 'acquisitions.json', self.observations)
        raise RuntimeError('Unreachable retry state')


def header_check(text: str, candidate: dict) -> dict:
    # Only the header area, not historical DOGC references elsewhere in the act.
    match = HEADER.search(text[:1200])
    if not match:
        return {'status': 'UNRECOGNIZED', 'original_header': None}
    found = date(int(match[4]), int(match[3]), int(match[2]))
    expected = date.fromisoformat(candidate['publication_date'])
    if found != expected or match[1] != candidate['edition']:
        raise ValueError('PDF header conflicts with the certified edition/publication date')
    return {'status': 'VERIFIED', 'original_header': match[0], 'edition': match[1], 'publication_date': str(found)}


def extract_pages(raw: bytes, candidate: dict) -> dict:
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 150:
        raise ValueError('Encrypted PDF or page count outside evidence limit')
    pages = []
    for index, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ''
        if len(text) > 1_000_000:
            raise ValueError('Unexpected extracted page size')
        pages.append({'page': index, 'text': text})
    if sum(len(page['text']) for page in pages) > 10_000_000:
        raise ValueError('Extracted text exceeds evidence limit')
    header = header_check(pages[0]['text'], candidate)
    empty = [p['page'] for p in pages if not p['text'].strip()]
    return {'document_id': candidate['document_id'], 'page_count': len(pages), 'pages': pages,
            'header': header, 'empty_text_pages': empty, 'ocr_used': False,
            'semantic_review': 'NOT_REVIEWED', 'project_fields_extracted': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-root', required=True)
    parser.add_argument('--expected-index-run', required=True)
    parser.add_argument('--output', default='reports/dogc_bodies')
    args = parser.parse_args()
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    generation = output / 'snapshots' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    generation.mkdir(parents=True)
    client = BodyClient(generation / 'raw')
    result = {'head_sha': os.getenv('GITHUB_SHA'), 'run_id': os.getenv('GITHUB_RUN_ID'),
              'index_run_id': args.expected_index_run, 'acquisition_complete': False,
              'dated_collector_enabled': False, 'project_events_created': 0,
              'semantic_project_validation_complete': False, 'generation': str(generation.relative_to(output))}
    records = []
    try:
        audit, candidates = load_verified_index(Path(args.index_root), args.expected_index_run)
        result.update(index_originals_reverified=True, index_sha256=audit['index_sha256'],
                      window_start=audit['window_start'], window_end=audit['window_end'], candidates=len(candidates))
        for candidate in candidates:
            raw, acquisition = client.get_pdf(candidate)
            parsed = extract_pages(raw, candidate)
            text_file = candidate['document_id'] + '.pages.json'
            atomic_json(generation / text_file, parsed)
            again = (generation / 'raw' / (acquisition['sha256'] + '.pdf')).read_bytes()
            if hashlib.sha256(again).hexdigest() != acquisition['sha256'] or extract_pages(again, candidate) != parsed:
                raise ValueError('PDF original-byte replay differs from the extracted pages')
            record = dict(candidate, body_acquired=True, pdf_sha256=acquisition['sha256'],
                          pdf_file='raw/' + acquisition['sha256'] + '.pdf', pages_file=text_file,
                          retrieved_at=acquisition['retrieved_at'], page_count=parsed['page_count'],
                          header=parsed['header'], empty_text_pages=parsed['empty_text_pages'],
                          semantic_review='NOT_REVIEWED')
            records.append(record)
            atomic_json(generation / 'documents.json', records)
            print('DOGC_BODY_ACQUIRED', json.dumps({k: record[k] for k in ('document_id', 'publication_date', 'page_count', 'header', 'empty_text_pages', 'pdf_sha256')}, ensure_ascii=False), flush=True)
        if len(records) != len(candidates):
            raise ValueError('Not every candidate has acquired original evidence')
        result.update(acquisition_complete=True, document_bodies_acquired=len(records),
                      extracted_pages=sum(r['page_count'] for r in records),
                      verified_pdf_headers=sum(r['header']['status'] == 'VERIFIED' for r in records),
                      documents_needing_header_review=[r['document_id'] for r in records if r['header']['status'] != 'VERIFIED'],
                      documents_with_empty_text_pages=[r['document_id'] for r in records if r['empty_text_pages']],
                      original_byte_replay_verified=True, ocr_used=False)
        rows = ''.join('<tr><td>' + html.escape(r['publication_date']) + '</td><td>' + html.escape(r['title']) + '</td><td>' + str(r['page_count']) + '</td><td><a href="' + html.escape(result['generation'] + '/' + r['pdf_file'], quote=True) + '">PDF originale</a></td><td><a href="' + html.escape(result['generation'] + '/' + r['pages_file'], quote=True) + '">Testo per pagina</a></td></tr>' for r in records)
        (output / 'index.html').write_text('<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DOGC — fascicolo documentale</title><style>body{font:16px/1.5 system-ui;margin:24px}td,th{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid}table{border-collapse:collapse}</style><h1>DOGC — fascicolo documentale</h1><p>Originali acquisiti dall’indice riconciliato. La selezione è ampia: include anche avvisi non pertinenti. I testi non sono ancora validati come progetti, autorizzazioni o opportunità commerciali. Nessun evento inserito nel radar.</p><table><tr><th>Pubblicazione</th><th>Titolo della fonte</th><th>Pagine</th><th>PDF</th><th>Testo</th></tr>' + rows + '</table></html>', encoding='utf-8')
        atomic_json(output / 'latest.json', {'generation': result['generation']})
        print('DOGC_BODIES_CERTIFIED', json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc), document_bodies_acquired=len(records))
        print('DOGC_BODIES_FAILED', json.dumps(result, ensure_ascii=False), flush=True)
        raise
    finally:
        client.session.close()
        atomic_json(generation / 'audit.json', result)
        atomic_json(output / 'audit.json', result)


if __name__ == '__main__':
    main()
