"""Full GVA catalogue with auditable same-run replay and fresh boundary checks.

No cross-run discovery cache, no undated substitution. A completed catalogue may
be replayed during this CI run/attempt only. All original pages are re-parsed;
first and last pages must match new live responses before any reuse is accepted.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import os
import re
from urllib.parse import urlsplit
from app.gva_transport import verified_url

MAX_AGE = 3600


def scope():
    run, attempt = os.getenv('GITHUB_RUN_ID', ''), os.getenv('GITHUB_RUN_ATTEMPT', '')
    return run + ':' + attempt if run.isdecimal() and attempt.isdecimal() else None


def row_signature(rows):
    # Source URLs may contain page-navigation state; all semantic source fields
    # and the official destination must agree. Full originals remain in receipts.
    result = []
    for row in rows:
        parsed = urlsplit(verified_url(row['url']))
        item = {k:v for k,v in row.items() if k != 'url'}
        item['source_endpoint'] = [parsed.scheme, parsed.hostname, parsed.port, parsed.path]
        result.append(item)
    return result


def receipt_for(raw, url, audit):
    sha = hashlib.sha256(raw).hexdigest()
    matches = [r for r in audit['acquisitions'] if r['sha256'] == sha and r['url'] == url]
    if not matches:
        raise ValueError('GVA catalogue response has no original acquisition receipt')
    return dict(matches[-1])


def parse_receipts(receipts, output):
    from app.collectors.gva_public import parse_listing
    if not isinstance(receipts, list) or not 1 <= len(receipts) <= 250:
        raise ValueError('Invalid catalogue receipt inventory')
    rows, parsed = [], []
    for r in receipts:
        if not isinstance(r, dict) or not {'url', 'retrieved_at', 'sha256', 'file', 'bytes'}.issubset(r):
            raise ValueError('Missing required original catalogue receipt fields')
        verified_url(r['url'])
        timestamp = datetime.fromisoformat(r['retrieved_at'])
        if timestamp.tzinfo is None:
            raise ValueError('Catalogue receipt has no original timezone')
        sha = r.get('sha256', '')
        if not re.fullmatch(r'[0-9a-f]{64}',sha) or r.get('file') != sha + '.html':
            raise ValueError('Invalid catalogue original identity')
        raw = (output / r['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha or len(raw)!=r['bytes']:
            raise ValueError('Catalogue original integrity failure')
        parsed.append(parse_listing(raw,r['url']))
    if not parsed or parsed[0][1][0]!=1:
        raise ValueError('Catalogue starts after its first record')
    total, size = parsed[0][1][2], parsed[0][1][1]
    pages = math.ceil(total / size)
    if pages > 250 or len(parsed)!=pages:
        raise ValueError('Catalogue page inventory incomplete')
    for n,(found,bounds,_) in enumerate(parsed,1):
        if bounds != (1+(n-1)*size,min(n*size,total),total):
            raise ValueError('Catalogue page bounds changed')
        rows.extend(found)
    if len(rows)!=total or len({r['external_id'] for r in rows})!=total:
        raise ValueError('Catalogue contains duplicates or missing records')
    return rows, parsed


def load_catalogue(get, output, audit):
    from app.collectors.gva_public import BASE, parse_listing, page_url
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cache=output/'catalogue_same_run.json'
    key=scope()
    initial_raw,initial_url=get(BASE)
    initial=parse_listing(initial_raw,initial_url)
    if initial[1][0]!=1:raise ValueError('GVA catalogue did not start at first row')
    total,size=initial[1][2],initial[1][1]
    count=math.ceil(total/size)
    if count>250:raise ValueError('GVA catalogue exceeds reviewed page count')
    audit['catalogue_reuse']={'scope':key,'reused':False}
    saved=None
    if key and cache.exists():
        try:
            saved=json.loads(cache.read_text(encoding='utf-8'))
            oldest=datetime.fromisoformat(saved['oldest_retrieved_at'])
            if (saved['scope']!=key or oldest.tzinfo is None
                or not 0 <= (datetime.now(timezone.utc)-oldest).total_seconds() <= MAX_AGE):
                saved=None
            if saved:
                rows,parts=parse_receipts(saved['pages'],output)
                now = datetime.now(timezone.utc)
                actual_dates = [datetime.fromisoformat(r['retrieved_at']) for r in saved['pages']]
                if oldest != min(actual_dates) or any(not 0 <= (now-d).total_seconds() <= MAX_AGE for d in actual_dates):
                    raise ValueError('Snapshot age differs from its original page receipts')
                if row_signature(parts[0][0])!=row_signature(initial[0]) or parts[0][1]!=initial[1]:
                    saved=None
                    audit['catalogue_reuse']['reason']='LIVE_FIRST_PAGE_CHANGED'
        except (OSError,ValueError,TypeError,KeyError) as exc:
            audit['catalogue_reuse']['reason']='INVALID_SNAPSHOT: '+str(exc)[:150]
            saved=None
    if saved:
        # No fallback to cache if this live check fails: source error is fatal.
        last_raw,last_url=get(page_url(initial[2],count)) if count>1 else (initial_raw,initial_url)
        tail=parse_listing(last_raw,last_url)
        if tail[1] == parts[-1][1] and row_signature(tail[0])==row_signature(parts[-1][0]):
            for r in saved['pages']:
                if r not in audit['acquisitions']:audit['acquisitions'].append(dict(r))
            audit['catalogue_reuse'].update(reused=True,original_page_count=len(parts),
                oldest_retrieved_at=saved['oldest_retrieved_at'],original_dates_preserved=True,
                complete_original_replay=True,live_first_and_last_verified=True)
            return rows,{'declared_records':total,'archive_records':len(rows),'pages':count,
                         'distinct_ids':total,'catalogue_mode':'SAME_RUN_ORIGINAL_REPLAY_WITH_LIVE_BOUNDARIES'}
        audit['catalogue_reuse']['reason']='LIVE_LAST_PAGE_CHANGED'
    receipts=[receipt_for(initial_raw,initial_url,audit)]
    for n in range(2,count+1):
        raw,url=get(page_url(initial[2],n))
        found,bounds,_=parse_listing(raw,url)
        if bounds != (1+(n-1)*size,min(n*size,total),total):
            raise ValueError('GVA ignored pagination or changed catalogue')
        receipts.append(receipt_for(raw,url,audit))
    rows,parts=parse_receipts(receipts,output)
    final_raw,final_url=get(BASE)
    final=parse_listing(final_raw,final_url)
    if initial[1]!=final[1] or row_signature(initial[0])!=row_signature(final[0]):
        raise ValueError('GVA catalogue changed during acquisition')
    if key:
        saved={'scope':key,'pages':receipts,'oldest_retrieved_at':min(r['retrieved_at'] for r in receipts)}
        temp=cache.with_suffix('.tmp');temp.write_text(json.dumps(saved,ensure_ascii=False),encoding='utf-8');temp.replace(cache)
    return rows,{'declared_records':total,'archive_records':len(rows),'pages':count,
                 'distinct_ids':total,'catalogue_mode':'LIVE_FULL_CATALOGUE'}
