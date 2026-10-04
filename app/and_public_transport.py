"""Bounded retry of interrupted official archive bodies, never of bad schemas."""
from __future__ import annotations
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urljoin
import requests

RECOVERABLE = (requests.exceptions.ChunkedEncodingError,
               requests.exceptions.ContentDecodingError,
               requests.exceptions.ConnectionError,
               requests.exceptions.Timeout)


ARCHIVE_ROUTES = {
    ('datos.juntadeandalucia.es', '/api/v0/public-documents/all'),
    ('www.juntadeandalucia.es', '/ssdigitales/festa/download-pro/dataset-documento_sometido_a_informacion.json'),
}


def validate_archive_url(url):
    """Only the official API and its observed, official dataset redirect."""
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or (parsed.hostname, parsed.path) not in ARCHIVE_ROUTES):
        raise ValueError('Unexpected archive destination: ' + url)
    return url


def download_archive(session, url, output, timeout, audit, *, max_attempts=3,
                     max_bytes=64 * 1024 * 1024):
    """Return complete bytes and URL; partial transfers are evidence, never input."""
    if max_attempts < 1 or max_attempts > 3:
        raise ValueError('Download attempt budget must be between one and three')
    validate_archive_url(url)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    attempts = audit.setdefault('download_attempts', [])
    for attempt in range(1, max_attempts + 1):
        response, parts, size = None, [], 0
        info = {'attempt': attempt, 'url': url, 'complete': False,
                'started_at': datetime.now(timezone.utc).isoformat()}
        attempts.append(info)
        try:
            target = url
            info['redirects'] = []
            for _ in range(4):
                response = session.get(target, timeout=timeout, stream=True, allow_redirects=False)
                info['http_status'] = response.status_code
                info['download_url'] = response.url
                validate_archive_url(response.url)
                if response.status_code not in (301, 302, 303, 307, 308):
                    break
                location = response.headers.get('Location')
                if not location:
                    raise ValueError('Archive redirect has no destination')
                destination = urljoin(target, location)
                info['redirects'].append({'from': target, 'to': destination,
                                          'http_status': response.status_code})
                target = validate_archive_url(destination)
                response.close()
                response = None
            else:
                raise ValueError('Archive redirect budget exceeded')
            response.raise_for_status()
            for part in response.iter_content(chunk_size=65536):
                size += len(part)
                if size > max_bytes:
                    raise ValueError('Official archive exceeds download size limit')
                parts.append(part)
            raw = b''.join(parts)
            length = response.headers.get('Content-Length')
            encoding = response.headers.get('Content-Encoding', 'identity').lower()
            if encoding == 'identity' and length and length.isdigit() and len(raw) != int(length):
                raise requests.exceptions.ChunkedEncodingError('Archive body length differs from HTTP Content-Length')
            info.update(complete=True, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                        retrieved_at=datetime.now(timezone.utc).isoformat())
            audit['download_recovered_after_retry'] = attempt > 1
            return raw, response.url
        except RECOVERABLE as exc:
            raw = b''.join(parts)
            (output / f'archive_attempt_{attempt}.partial').write_bytes(raw)
            info.update(error_type=type(exc).__name__, error=str(exc)[:500],
                        bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            if attempt == max_attempts:
                raise
            time.sleep(2 * attempt)
        except Exception as exc:
            info.update(error_type=type(exc).__name__, error=str(exc)[:500], bytes=size)
            raise
        finally:
            if response is not None:
                response.close()
    raise RuntimeError('Archive download finished without a result')
