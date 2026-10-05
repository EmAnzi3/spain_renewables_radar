"""Replay acquired DOGC originals; never re-date evidence or trust log counters.

The entry point re-runs the complete index gate from the frozen original index
artifact, then reconstructs PDF/page/header counts from the acquired PDF bytes.
Its report is separate from, and does not modify, the original acquisition audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit, parse_qs

from pypdf import PdfReader
from scripts.dogc_pdf_headers import document_headers


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or '\\' in relative:
        raise ValueError('Invalid evidence path')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Evidence file missing or outside its generation')
    return path


def source_identity(candidate: dict, acquisition: dict) -> None:
    identity, url = candidate['document_id'], candidate['source_url']
    p = urlsplit(url); q = parse_qs(p.query)
    if (p.scheme != 'https' or p.netloc != 'portaldogc.gencat.cat'
            or p.path != '/utilsEADOP/AppJava/PdfProviderServlet'
            or q != {'documentId': [identity], 'type': ['01'], 'language': ['ca_ES']}
            or p.fragment or not re.fullmatch(r'\d+', identity)
            or acquisition['url'] != url or acquisition['document_id'] != identity):
        raise ValueError('Original source identity does not match certified candidate')
    if acquisition.get('redirect'):
        target = acquisition.get('final_url')
        parsed = urlsplit(target)
        base = candidate.get('base_edition', candidate['edition'])
        if (acquisition['redirect'].get('location') != target
                or acquisition['redirect'].get('status') not in (301, 302, 303, 307, 308)
                or parsed.scheme != 'https' or parsed.netloc != 'portaldogc.gencat.cat'
                or parsed.query or parsed.fragment
                or not re.fullmatch(r'/utilsEADOP/PDF/' + re.escape(base) + r'/\d+\.pdf', parsed.path)):
            raise ValueError('Original redirect provenance is not the certified edition')


def verify_bundle(root: Path, candidates: list[dict], expected_run: str, *, require_exact_text: bool = True) -> dict:
    latest = read_json(root / 'latest.json')['generation']
    if not isinstance(latest, str) or not re.fullmatch(r'snapshots/[A-Za-z0-9-]+', latest):
        raise ValueError('Invalid evidence generation')
    generation = root / latest
    original_audit = read_json(safe_file(root, latest + '/audit.json'))
    if original_audit.get('run_id') != expected_run or not original_audit.get('acquisition_complete'):
        raise ValueError('Wrong or incomplete original acquisition')
    documents = read_json(safe_file(generation, 'documents.json'))
    manifest = read_json(safe_file(generation, 'raw/acquisitions.json'))
    completed = {}
    for entry in manifest:
        if entry.get('complete'):
            identity = entry['document_id']
            if identity in completed or entry.get('status') != 200:
                raise ValueError('Ambiguous successful original acquisition')
            if datetime.fromisoformat(entry['retrieved_at']).tzinfo is None:
                raise ValueError('Original acquisition time lacks timezone')
            completed[identity] = entry
    expected = {row['document_id']: row for row in candidates}
    actual = {row['document_id']: row for row in documents}
    if (len(expected) != len(candidates) or len(actual) != len(documents)
            or set(expected) != set(actual) or set(expected) != set(completed)):
        raise ValueError('Candidates, documents and original acquisitions disagree')
    verified = []
    text_differences = []
    for identity, candidate in expected.items():
        doc, meta = actual[identity], completed[identity]
        source_identity(candidate, meta)
        for field in ('document_id', 'publication_date', 'edition', 'base_edition', 'title', 'source_url'):
            if doc.get(field) != candidate.get(field):
                raise ValueError('Document changed a certified index field: ' + field)
        sha = meta.get('sha256')
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
            raise ValueError('Invalid original PDF digest')
        if doc['pdf_sha256'] != sha or doc['pdf_file'] != 'raw/' + sha + '.pdf':
            raise ValueError('PDF path/digest differs from acquisition')
        path = safe_file(generation, doc['pdf_file']); raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha or len(raw) != meta['bytes']:
            raise ValueError('Original PDF byte integrity failed')
        if doc['retrieved_at'] != meta['retrieved_at']:
            raise ValueError('Original acquisition time has changed')
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 150:
            raise ValueError('Unexpected PDF page structure')
        pages = [{'page': n, 'text': page.extract_text() or ''} for n, page in enumerate(reader.pages, 1)]
        saved = read_json(safe_file(generation, doc['pages_file']))
        if saved['page_count'] != len(pages) or doc['page_count'] != len(pages) or len(saved['pages']) != len(pages):
            raise ValueError('Stored page count differs from the PDF original')
        for stored, rebuilt in zip(saved['pages'], pages):
            if stored != rebuilt:
                text_differences.append({'document_id': identity, 'page': rebuilt['page'],
                    'stored_sha256': hashlib.sha256(stored['text'].encode()).hexdigest(),
                    'reconstructed_sha256': hashlib.sha256(rebuilt['text'].encode()).hexdigest()})
        if require_exact_text and saved['pages'] != pages:
            raise ValueError('Stored page text differs from the PDF original: ' + identity)
        if any(not page['text'].strip() for page in pages):
            raise ValueError('An original PDF page has no extracted text')
        headers = document_headers(pages, candidate)
        if any(header['status'] != 'VERIFIED' for header in headers):
            raise ValueError('A printed page masthead remains unverified')
        verified.append({'document_id': identity, 'publication_date': candidate['publication_date'],
                         'edition': candidate['edition'], 'pages': len(pages),
                         'pdf_sha256': sha, 'original_retrieved_at': meta['retrieved_at'],
                         'cve': headers[0]['cve'], 'verified_page_headers': len(headers),
                         'header_checks': headers})
    result = {'verification_type': 'offline_replay_of_original_acquisition',
              'original_run_id': expected_run, 'original_generation': latest,
              'verified_at': datetime.now(timezone.utc).isoformat(),
              'documents': len(verified), 'pdf_pages': sum(row['pages'] for row in verified),
              'verified_document_headers': len(verified),
              'verified_page_headers': sum(row['verified_page_headers'] for row in verified),
              'source_request_provenance_verified': True, 'pdf_byte_digests_verified': True,
              'stored_page_text_reconstructed_from_pdf': not text_differences,
              'exact_text_replay_required': require_exact_text, 'text_replay_differences': text_differences,
              'original_retrieval_dates_preserved': True, 'ocr_used': False,
              'new_source_downloads': 0, 'project_events_created': 0,
              'dated_collector_enabled': False, 'semantic_project_validation_complete': False,
              'original_acquisition_audit': original_audit, 'document_checks': verified}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-root', required=True)
    parser.add_argument('--body-root', required=True)
    parser.add_argument('--expected-index-run', required=True)
    parser.add_argument('--expected-body-run', required=True)
    parser.add_argument('--output', default='reports/dogc_body_recheck.json')
    args = parser.parse_args()
    from scripts.acquire_dogc_bodies import load_verified_index
    index_audit, candidates = load_verified_index(Path(args.index_root), args.expected_index_run)
    result = verify_bundle(Path(args.body_root), candidates, args.expected_body_run)
    result.update(index_full_gate_reexecuted=True, index_run_id=args.expected_index_run,
                  index_sha256=index_audit['index_sha256'])
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('DOGC_ORIGINALS_RECHECKED', json.dumps({k:v for k,v in result.items()
          if k not in ('document_checks', 'original_acquisition_audit')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
