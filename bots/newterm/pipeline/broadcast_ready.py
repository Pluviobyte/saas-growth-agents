#!/usr/bin/env python3
"""Read-only bounded prescan readiness/index. No imports of collectors or state writers.
Exit 0=ready, 2=settled partial, 3=deadline timeout. JSON stdout only.
Legacy inputs without completion audit require all three block markers, not DONE alone.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo

RADARS = ('sitemaps', 'capcut', 'producthunt', 'github_trending', 'paid_nav', 'reddit')
OPTIONAL_SOURCES = ('gefei',)
SOURCES = ('gefei', 'newterm', 'tiktok') + tuple('radar_' + x for x in RADARS) + ('radar_md',)

def inspect(out):
    issues, index, rcs = [], {}, {}
    audit = None
    audit_present = (out / 'completion.json').exists() or (out / 'source_status.tsv').exists()
    if (out / 'completion.json').exists():
        try:
            audit = json.loads((out / 'completion.json').read_text())
            if not isinstance(audit, dict): raise ValueError('not object')
        except (ValueError, OSError) as e:
            issues.append('completion.json:invalid:' + type(e).__name__)
    if (out / 'source_status.tsv').exists():
        try:
            for line in (out / 'source_status.tsv').read_text().splitlines():
                k, v = line.split('\t'); rcs[k] = int(v)
        except (ValueError, OSError): issues.append('source_status.tsv:invalid')
    for k, rc in rcs.items():
        if rc: issues.append(k + ':rc=' + str(rc))
    # gefei is an optional paid source; prescan.sh skips it when GEFEI_API_KEY is unset
    missing_rc = [k for k in SOURCES if k not in rcs and k not in OPTIONAL_SOURCES] if audit_present else []
    if missing_rc: issues.append('missing_source_status:' + ','.join(missing_rc))
    markers = {k: (out / k).exists() for k in ('DONE', 'FAILED', 'TIKTOK_DONE', 'TIKTOK_FAILED', 'RADAR_DONE', 'SETTLED', 'PARTIAL', 'ALL_FAILED')}
    if markers['FAILED'] or markers['TIKTOK_FAILED'] or markers['ALL_FAILED'] or markers['PARTIAL']:
        issues.append('failure_or_partial_marker')
    for name in ('report.md', 'radar.md', 'tiktok.json') + tuple('radar_' + x + '.json' for x in RADARS):
        p = out / name
        entry = {'path': str(p)}
        index[name] = entry
        try:
            if not p.stat().st_size: raise ValueError('empty')
            if p.suffix == '.json':
                d = json.loads(p.read_text())
                if not isinstance(d, dict): raise ValueError('not object')
                keys = ('passed', 'early_watch', 'needs_review', 'tikhub_top_unmatched') if name == 'tiktok.json' else (('new_candidates',) if name == 'radar_sitemaps.json' else ('first_time_candidates',))
                # Missing required candidate arrays is not an empty successful collection.
                required = keys[:2] if name == 'tiktok.json' else keys
                if any(not isinstance(d.get(k), list) for k in required): raise ValueError('candidate_schema')
                entry['counts'] = {k: len(d[k]) for k in keys + ('oldword_newsites', 'oldword_newsites_model') if isinstance(d.get(k), list)}
                failed = []
                for group in ('sites', 'cats', 'subs', 'domains'):
                    for k, v in (d.get(group) or {}).items():
                        if isinstance(v, dict) and v.get('ok') is False: failed.append(k)
                for k in ('feed_ok', 'html_ok'):
                    if d.get(k) is False: failed.append(k)
                if d.get('blocked'): failed.append('blocked')
                if d.get('errors'): failed.append('errors')
                if failed: issues.append(name + ':source_degraded:' + ','.join(failed))
            entry['available'] = True
        except (OSError, ValueError, TypeError, AttributeError) as e:
            entry['available'] = False
            entry['error'] = str(e) if isinstance(e, ValueError) else type(e).__name__
            issues.append(name + ':missing_or_invalid')
    if audit_present:
        settled = bool(audit and audit.get('settled') is True and not missing_rc)
        if audit and audit.get('state') != 'complete': issues.append('completion_state:' + str(audit.get('state')))
    else:
        settled = ((markers['DONE'] or markers['FAILED']) and (markers['TIKTOK_DONE'] or markers['TIKTOK_FAILED']) and markers['RADAR_DONE'])
    return {'settled': bool(settled), 'audit_mode': 'audited' if audit_present else 'legacy_markers', 'issues': issues, 'files': index}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('slot', choices=('morning', 'noon', 'evening'))
    p.add_argument('--input-dir', type=Path)
    p.add_argument('--date', help='YYYYMMDD, default today Asia/Shanghai')
    p.add_argument('--timeout', type=float, default=600)
    p.add_argument('--poll', type=float, default=5)
    a = p.parse_args()
    if not 0 <= a.timeout <= 600 or not 0.01 <= a.poll <= 60: p.error('timeout must be 0..600; poll 0.01..60')
    day = a.date or datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
    try: datetime.datetime.strptime(day, '%Y%m%d')
    except ValueError: p.error('date must be YYYYMMDD')
    out = (a.input_dir or Path(os.environ.get('NEWTERM_HOME') or Path(__file__).resolve().parent) / ('prescan_' + day + '_' + a.slot)).resolve()
    start = time.monotonic()
    while True:
        result = inspect(out)
        elapsed = time.monotonic() - start
        if result['settled']:
            state = 'partial' if result['issues'] else 'ready'
            break
        if elapsed >= a.timeout:
            state = 'timeout'
            break
        time.sleep(min(a.poll, a.timeout - elapsed))
    print(json.dumps(dict(status=state, slot=a.slot, input_dir=str(out), waited_seconds=round(elapsed, 3), **result), ensure_ascii=False, separators=(',', ':')))
    return {'ready': 0, 'partial': 2, 'timeout': 3}[state]

if __name__ == '__main__':
    raise SystemExit(main())
