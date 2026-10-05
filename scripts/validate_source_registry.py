"""Reconcile certified source membership and exact complete-day coverage.

Enrichments are not discovery collectors. A row count is not sufficient proof of
coverage: every source must account once for each day in the same closed window.
"""
from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path


def validate_source_registry(expected, path='config/sources.json'):
    from app.run_pipeline import COLLECTOR_CLASSES, parse_args
    expected=set(expected)
    rows=json.loads(Path(path).read_text(encoding='utf-8'))
    codes=[r['code'] for r in rows]
    if len(codes)!=len(set(codes)):
        raise ValueError('Repeated source code in registry')
    enabled={r['code'] for r in rows if r.get('implemented') and r.get('kind') in ('bulletin','project_discovery')}
    if enabled!=expected or set(COLLECTOR_CLASSES)!=expected:
        raise ValueError('Registry, ordinary collector map and certification source list differ')
    defaults=parse_args([]).sources.split(',')
    if len(defaults)!=len(set(defaults)) or set(defaults)!=expected:
        raise ValueError('Default launcher source list is incomplete or repeated')
    return {'discovery_collectors':len(expected),'source_codes':sorted(expected),
            'ordinary_defaults_match_registry':True,'enrichments_not_counted_as_discovery':True}


def validate_source_days(coverage, expected, days=30):
    expected=set(expected)
    if not expected or type(days) is not int or days<1:
        raise ValueError('Invalid expected source/day scope')
    reference=None
    for code in sorted(expected):
        rows=[r for r in coverage if r['source_code']==code]
        dates=sorted(date.fromisoformat(r['date']) for r in rows)
        if len(dates)!=days or len(set(dates))!=days or any(r['status']!='OK' for r in rows):
            raise ValueError('Missing, repeated or failed source days: '+code)
        if dates!=[dates[0]+timedelta(days=n) for n in range(days)]:
            raise ValueError('Non-contiguous coverage for '+code)
        if reference is not None and dates!=reference:
            raise ValueError('Collectors cover different date windows')
        reference=dates
    return {'start':str(reference[0]),'end':str(reference[-1]),'days':days,
            'collectors':len(expected),'source_day_rows':days*len(expected),
            'unique_contiguous_same_window':True}
