#!/usr/bin/env python3
"""搜词找站：一个词 -> Google 前 N 名里的站，过滤掉大站，记进站点台账。

  python3 serp_sites.py "ai video generator" ["another keyword" ...] [--depth 30]

台账：SITEOPS_HOME/sites.csv（domain, first_keyword, first_seen, best_rank, keywords）
同一个域名多次出现只更新排名和关键词，不重复建行。下一步用 dr_check.py 查这些站的 DR 和外链。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib' / 'aisa'))
import sources  # noqa: E402
from client import AisaError, STATS  # noqa: E402

HOME = Path(os.environ.get('SITEOPS_HOME', '.'))
SITES = HOME / 'sites.csv'
COLS = ['domain', 'first_keyword', 'first_seen', 'best_rank', 'keywords']
# 搜词找站时没有参考价值的大站，按需增删
BIG = {'youtube.com', 'reddit.com', 'wikipedia.org', 'github.com', 'medium.com', 'quora.com', 'x.com', 'twitter.com',
       'facebook.com', 'instagram.com', 'tiktok.com', 'linkedin.com', 'amazon.com', 'apple.com', 'google.com',
       'microsoft.com', 'pinterest.com', 'producthunt.com', 'play.google.com', 'apps.apple.com'}


def domain(url: str) -> str:
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith('www.') else h


def load():
    if not SITES.exists():
        return {}
    with SITES.open(encoding='utf-8') as f:
        return {r['domain']: r for r in csv.DictReader(f)}


def save(rows):
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = SITES.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r['first_seen']))
    os.replace(tmp, SITES)


def organic(res):
    for task in res.get('tasks') or []:
        for result in task.get('result') or []:
            for item in result.get('items') or []:
                if item.get('type') == 'organic' and item.get('url'):
                    yield item.get('rank_group') or item.get('rank_absolute'), item['url']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('keywords', nargs='+')
    ap.add_argument('--depth', type=int, default=30)
    a = ap.parse_args()
    rows, today, report = load(), dt.date.today().isoformat(), {}
    for kw in a.keywords:
        try:
            res = sources.serp_google(kw, depth=a.depth)
        except AisaError as e:
            report[kw] = {'error': str(e)}
            continue
        new, seen = [], []
        for rank, url in organic(res):
            d = domain(url)
            if not d or any(d == b or d.endswith('.' + b) for b in BIG):
                continue
            r = rows.get(d)
            if r is None:
                rows[d] = {'domain': d, 'first_keyword': kw, 'first_seen': today, 'best_rank': rank, 'keywords': kw}
                new.append(d)
            else:
                kws = set(r['keywords'].split('|')) | {kw}
                r['keywords'] = '|'.join(sorted(kws))
                r['best_rank'] = min(int(r['best_rank'] or 999), int(rank or 999))
                seen.append(d)
        report[kw] = {'new_sites': new, 'already_known': seen}
    save(rows)
    print(json.dumps({'sites_total': len(rows), 'by_keyword': report, 'aisa': STATS}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
