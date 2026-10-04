"""Bounded retry of interrupted official archive bodies, never of bad schemas."""
from __future__ import annotations
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import requests

RECOVERABLE = (requests.exceptions.ChunkedEncodingError,
               requests.exceptions.ContentDecodingError,
               requests.exceptions.ConnectionError,
               requests.exceptions.Timeout)


def download_archive(session, url, output, timeout, audit, *, max_attempts=3,
                     max_bytes=64 * 1024 * 1024):
    """Return complete bytes and URL; partial transfers are evidence, never input."""
    if max_attempts < 1 or max_attempts > 3:
        raise ValueError('Download attempt budget must be between one and three')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    attempts = audit.setdefault('download_attempts', [])
    for attempt in range(1, max_attempts + 1):
        response, parts, size = None, [], 0
        info = {'attempt': attempt, 'url': url, 'complete': False,
                'started_at': datetime.now(timezone.utc).isoformat()}
        attempts.append(info)
        try:
            response = session.get(url, timeout=timeout, stream=True)
            info['http_status'] = response.status_code
            if (urlsplit(response.url).scheme != 'https'
                    or urlsplit(response.url).netloc != urlsplit(url).netloc):
                raise ValueError('Unexpected archive redirect')
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
