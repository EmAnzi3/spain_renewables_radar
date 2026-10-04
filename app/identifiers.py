"""Conservative administrative identifiers; prose is never a project key."""
from __future__ import annotations
import re

LABEL = r'(?:expedientes?|expdte\.?|expte\.?|exp\.)(?:\s*(?:n[ºo°]\.?|n[uú]mero))?'
VALUE = r'((?:(?:INAGA|PRETOR|SIAGGE)\s+)?[A-Z0-9][A-Z0-9._/\-]{2,70})'
TITLE_PATTERNS = (
    re.compile(LABEL + r'\s*[:\-]?\s*' + VALUE, re.I),
    re.compile(r'\b(?:referencia|c[oó]digo)\s*[:\-]\s*' + VALUE, re.I),
    re.compile(r'\b(?:c[oó]digo)\s+((?:PFot|PEol)[- /][A-Z0-9/_-]+)', re.I),
)
BODY_PATTERNS = (
    re.compile(LABEL + r'\s+SIAGGE\s+' + VALUE, re.I),
    re.compile(LABEL + r'\s*:\s*' + VALUE, re.I),
    re.compile(r'(?:^|\n)\s*(?:referencia|c[oó]digo)\s*:\s*' + VALUE, re.I),
    re.compile(r'\b(?:c[oó]digo|n[uú]mero\s+de\s+expediente)\s+((?:PFot|PEol)[- /][A-Z0-9/_-]+)', re.I),
)


def valid_expediente(value) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    # Explicit Galicia authority reference formats retain the original internal space.
    if re.fullmatch(r'IN\d{3}[A-Z]\s+\d{4}/\d+(?:-[A-Z0-9]+)*|FV\s+\d+/\d{4}', value, re.I):
        return True
    return bool(len(value) >= 3 and re.search(r'\d', value)
                and re.fullmatch(r'(?:(?:INAGA|PRETOR|SIAGGE)\s+)?[A-Z0-9][A-Z0-9._/\-]{2,70}', value, re.I))


def extract_identifier(text: str, *, body: bool = False) -> str | None:
    found = []
    for pattern in BODY_PATTERNS if body else TITLE_PATTERNS:
        for match in pattern.finditer(text or ''):
            value = match[1].strip(' .;,)')
            value = re.sub(r'^SIAGGE\s+', '', value, flags=re.I)
            if valid_expediente(value) and value.casefold() not in [x.casefold() for x in found]:
                found.append(value)
    if body and len(found) != 1:
        return None
    return found[0] if found else None
