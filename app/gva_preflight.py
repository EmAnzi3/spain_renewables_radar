"""Fail early on an unavailable GVA catalogue without skipping its coverage.

No events are produced. A complete catalogue may be reused by later processes
only through the existing original-byte/same-run/fresh-boundary checks.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from app.collectors.gva_public import GVAPublicCollector


def run_preflight(out_dir='reports/gva_public'):
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    collector = GVAPublicCollector(out_dir=str(output))
    result = {'run_id': os.getenv('GITHUB_RUN_ID'),
              'run_attempt': os.getenv('GITHUB_RUN_ATTEMPT'),
              'head_sha': os.getenv('GITHUB_SHA'), 'source_code': 'GVA_PUBLIC',
              'phase': 'CATALOGUE_PREFLIGHT_NOT_PROJECT_CERTIFICATION',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'catalogue_ready': False, 'project_events_created': 0,
              'thirteen_source_backfill_certified': False}
    try:
        collector._load()
        if (collector.audit.get('complete') is not True
                or not collector.inventory
                or len(collector.inventory) != collector.audit.get('declared_records')
                or len(collector.inventory) != collector.audit.get('distinct_ids')):
            raise ValueError('GVA preflight did not obtain a complete catalogue')
        result.update(catalogue_ready=True, archive_records=len(collector.inventory),
                      pages=collector.audit['pages'],
                      acquisition_mode=collector.audit['catalogue_mode'],
                      source_dates_preserved=True)
        return result
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        collector.session.close()
        result['completed_at'] = datetime.now(timezone.utc).isoformat()
        tmp = output / 'preflight.tmp'
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        tmp.replace(output / 'preflight.json')
        print('GVA_PREFLIGHT', json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    run_preflight()
