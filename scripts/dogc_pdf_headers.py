"""Verify DOGC mastheads independently of PDF text extraction order.

Printed mastheads may be emitted after the body by a PDF text extractor. Match
only the complete journal/CVE block, not incidental historical DOGC references.
Original bytes and original extracted text are never edited by this module.
"""
from __future__ import annotations

from datetime import date
import re

MASTHEAD = re.compile(
    r'N[úu]m\.?\s*(?P<edition>\d+[A-Z]?)\s*[-–—]\s*'
    r'(?P<day>\d{1,2})\s*[./]\s*(?P<month>\d{1,2})\s*[./]\s*(?P<year>\d{4})'
    r'\s*(?P<page>\d+)\s*/\s*(?P<pages>\d+)\s+'
    r'Diari Oficial de la Generalitat de Catalunya\s+'
    r'(?P<cve>CVE-DOGC-[A-Z]-\d+-\d{4})(?!\d)', re.IGNORECASE,
)


def header_check(text: str, candidate: dict, *, expected_page: int | None = None,
                 total_pages: int | None = None) -> dict:
    """Require the original journal block and the exact indexed date/edition."""
    matches = list(MASTHEAD.finditer(text))
    if not matches:
        return {'status': 'UNRECOGNIZED', 'original_header': None}
    if len(matches) != 1:
        raise ValueError('Ambiguous or duplicated DOGC masthead')
    match = matches[0]
    published = date(int(match['year']), int(match['month']), int(match['day']))
    if published != date.fromisoformat(candidate['publication_date']) or match['edition'] != candidate['edition']:
        raise ValueError('PDF masthead conflicts with the indexed edition/publication date')
    page, pages = int(match['page']), int(match['pages'])
    if not 1 <= page <= pages:
        raise ValueError('Invalid page position in the original masthead')
    if expected_page is not None and page != expected_page:
        raise ValueError('PDF page order differs from its printed masthead')
    if total_pages is not None and pages != total_pages:
        raise ValueError('PDF page count differs from its printed masthead')
    return {'status': 'VERIFIED', 'original_header': match[0], 'edition': match['edition'],
            'publication_date': str(published), 'page': page, 'pages': pages, 'cve': match['cve']}


def document_headers(pages: list[dict], candidate: dict) -> list[dict]:
    """Check every page, rejecting mixed documents, missing or reordered pages."""
    if not pages:
        raise ValueError('Document contains no extracted pages')
    headers = []
    for number, page in enumerate(pages, 1):
        if page.get('page') != number or not isinstance(page.get('text'), str):
            raise ValueError('Extracted page identity is invalid')
        headers.append(header_check(page['text'], candidate, expected_page=number, total_pages=len(pages)))
    cves = {header['cve'] for header in headers if header['status'] == 'VERIFIED'}
    if len(cves) > 1:
        raise ValueError('Pages identify different DOGC documents')
    return headers
