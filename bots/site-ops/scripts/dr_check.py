#!/usr/bin/env python3
"""查站点的 DR 和外链数（Ahrefs，经 AIsa），存快照、和上一次对比。

  python3 dr_check.py mysite.com other.com        # 查指定域名
  python3 dr_check.py --own                       # 查 SITEOPS_HOME/own_sites.txt 里的自有站（每天一次的例程用这个）
  python3 dr_check.py --from-sites 20             # 查 sites.csv 里最新的 20 个竞品站

快照：SITEOPS_HOME/metrics.jsonl，一行一个域名一次查询。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib' / 'aisa'))
import sources  # noqa: E402
from client import AisaError, STATS  # noqa: E402

HOME = Path(os.environ.get('SITEOPS_HOME', '.'))
METRICS = HOME / 'metrics.jsonl'
WANT = ('domain_rating', 'ahrefs_rank', 'org_traffic', 'org_keywords', 'refdomains', 'backlinks', 'live_refdomains')


def flat_numbers(obj, out=None):
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k in WANT:
                out.setdefault(k, v)
            elif isinstance(v, (dict, list)):
                flat_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            flat_numbers(v, out)
    return out


def last_snapshot():
    last = {}
    if METRICS.exists():
        for line in METRICS.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line)
                last[r['domain']] = r
    return last


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('domains', nargs='*')
    ap.add_argument('--own', action='store_true')
    ap.add_argument('--from-sites', type=int, default=0)
    a = ap.parse_args()
    doms = list(a.domains)
    if a.own:
        f = HOME / 'own_sites.txt'
        doms += [l.strip() for l in f.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')] if f.exists() else []
    if a.from_sites:
        with (HOME / 'sites.csv').open(encoding='utf-8') as f:
            rows = sorted(csv.DictReader(f), key=lambda r: r['first_seen'], reverse=True)
        doms += [r['domain'] for r in rows[:a.from_sites]]
    if not doms:
        sys.exit('没有要查的域名')

    prev, today, out = last_snapshot(), dt.date.today().isoformat(), []
    for d in dict.fromkeys(doms):
        rec = {'domain': d, 'date': today}
        try:
            rec.update(flat_numbers(sources.ahrefs_domain_rating(d)))
            rec.update(flat_numbers(sources.ahrefs_metrics(d)))
        except AisaError as e:
            rec['error'] = str(e)
        p = prev.get(d)
        if p and 'error' not in rec:
            rec['delta'] = {k: round(rec[k] - p[k], 2) for k in WANT if k in rec and isinstance(p.get(k), (int, float))}
            rec['prev_date'] = p.get('date')
        out.append(rec)
    HOME.mkdir(parents=True, exist_ok=True)
    with METRICS.open('a', encoding='utf-8') as f:
        for r in out:
            if 'error' not in r:
                f.write(json.dumps({k: v for k, v in r.items() if k not in ('delta', 'prev_date')}, ensure_ascii=False) + '\n')
    print(json.dumps({'checked': out, 'aisa': STATS}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
