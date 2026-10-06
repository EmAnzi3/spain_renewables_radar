"""Bounded complete-response GVA transport with anonymous connection reuse.

A supplied session keeps connections between successful requests, with a minimum
interval. Transient failures reset its connection pool and anonymous cookies.
Without a supplied session, each attempt uses an independent anonymous session.
Permanent HTTP errors, denial, TLS and semantic failures are never retried.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit
import uuid

import requests
from requests.adapters import HTTPAdapter

MAX_ATTEMPTS = 3
MAX_REDIRECTS = 4
TRANSIENT_STATUS = {500, 502, 503, 504}


def verified_url(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.gva.es')
            or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment):
        raise ValueError('GVA destination is not an official HTTPS endpoint')
    return url


def fetch_official(url, *, output, audit, timeout, user_agent, limit=12_000_000, session=None):
    origin = verified_url(url)
    if type(limit) is not int or not 0 < limit <= 20_000_000:
        raise ValueError('Invalid GVA response-size limit')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    operation = uuid.uuid4().hex
    attempts = audit.setdefault('transport_attempts', [])
    for number in range(1, MAX_ATTEMPTS + 1):
        attempt = {'operation': operation, 'origin_url': origin, 'attempt': number,
                   'started_at': datetime.now(timezone.utc).isoformat(),
                   'complete': False, 'responses': []}
        attempts.append(attempt)
        if session is not None:
            adapter = session.get_adapter(origin)
            if adapter.max_retries.total:
                session.mount('https://', HTTPAdapter(max_retries=0))
        try:
            with (nullcontext(session) if session is not None else requests.Session()) as connection:
                connection.headers['User-Agent'] = user_agent
                if number > 1 or session is None:
                    connection.mount('https://', HTTPAdapter(max_retries=0))
                current = origin
                visited = set()
                for hop in range(MAX_REDIRECTS + 1):
                    verified_url(current)
                    if current in visited:
                        raise ValueError('GVA redirect cycle')
                    visited.add(current)
                    receipt = {'url': current, 'method': 'GET', 'received_bytes': 0}
                    attempt['responses'].append(receipt)
                    response = None
                    chunks = []
                    try:
                        if session is not None:
                            delay = getattr(connection, '_gva_not_before', 0) - time.monotonic()
                            if delay > 0:
                                time.sleep(delay)
                        response = connection.get(current, timeout=timeout, stream=True, allow_redirects=False)
                        if session is not None:
                            connection._gva_not_before = time.monotonic() + 0.75
                        receipt['status'] = response.status_code
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get('Location')
                            if not location:
                                raise ValueError('Official redirect lacks a destination')
                            current = verified_url(urljoin(current, location))
                            receipt['location'] = current
                            if hop == MAX_REDIRECTS:
                                raise ValueError('GVA redirect budget exhausted')
                            continue
                        response.raise_for_status()
                        if response.status_code != 200:
                            raise ValueError('Unexpected GVA response status')
                        for chunk in response.iter_content(65536):
                            receipt['received_bytes'] += len(chunk)
                            if receipt['received_bytes'] > limit:
                                raise ValueError('Official source exceeds bounded download size')
                            chunks.append(chunk)
                        raw = b''.join(chunks)
                        declared = response.headers.get('Content-Length')
                        encoding = response.headers.get('Content-Encoding', 'identity').lower()
                        if declared is not None and encoding in ('', 'identity'):
                            if not str(declared).isdecimal():
                                raise ValueError('Invalid source Content-Length')
                            if int(declared) != len(raw):
                                raise requests.exceptions.ChunkedEncodingError('Incomplete GVA response length')
                        sha = hashlib.sha256(raw).hexdigest()
                        filename = sha + ('.pdf' if raw.startswith(b'%PDF-') else '.html')
                        (output / filename).write_bytes(raw)
                        acquired = {'url': current, 'file': filename, 'sha256': sha,
                                    'bytes': len(raw), 'retrieved_at': datetime.now(timezone.utc).isoformat()}
                        audit.setdefault('acquisitions', []).append(acquired)
                        receipt.update(acquired, content_type=response.headers.get('Content-Type'))
                        attempt['complete'] = True
                        return raw, current
                    except Exception as exc:
                        receipt.update(error_type=type(exc).__name__, error=str(exc)[:500])
                        if chunks:
                            partial = b''.join(chunks)
                            digest = hashlib.sha256(partial).hexdigest()
                            filename = 'transport_partial_' + digest + '.bin'
                            (output / filename).write_bytes(partial)
                            receipt.update(partial_file=filename, partial_sha256=digest,
                                           partial_bytes=len(partial))
                        raise
                    finally:
                        if response is not None:
                            response.close()
            raise ValueError('GVA did not return a complete response')
        except Exception as exc:
            attempt.update(error_type=type(exc).__name__, error=str(exc)[:500])
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            transient = (isinstance(exc, (requests.ConnectionError, requests.Timeout,
                                         requests.exceptions.ChunkedEncodingError))
                         or isinstance(exc, requests.HTTPError) and status in TRANSIENT_STATUS)
            if isinstance(exc, requests.exceptions.SSLError) or not transient or number == MAX_ATTEMPTS:
                raise
            if session is not None:
                session.close()
                session.cookies.clear()
            print(f'GVA transient {type(exc).__name__}: complete GET retry {number + 1}/{MAX_ATTEMPTS}', flush=True)
            time.sleep(number * 3)
        finally:
            attempt['finished_at'] = datetime.now(timezone.utc).isoformat()
            temporary = output / ('transport_attempts.' + operation + '.tmp')
            temporary.write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(output / 'transport_attempts.json')
    raise RuntimeError('Unreachable GVA transport retry state')
