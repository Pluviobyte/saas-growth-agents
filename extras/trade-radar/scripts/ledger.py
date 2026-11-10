#!/usr/bin/env python3
"""判断账本：每条推送过的判断记一行，事后回看对错，统计命中率。

  python3 ledger.py add --json judgment.json        # Bot 把分析结果（JSON）记进账本
  python3 ledger.py due                             # 已经到期、等待复盘的判断
  python3 ledger.py resolve <id> hit|miss|partial|void --price 81234 --note "..."
  python3 ledger.py stats [--days 7]                # 命中率，按资产和置信度分组

账本：TRADE_HOME/judgment-ledger.jsonl，一行一个 JSON。只记判断，不记任何仓位、订单或钱包信息。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

HOME = Path(os.environ.get('TRADE_HOME', '.'))
LEDGER = HOME / 'judgment-ledger.jsonl'
FIELDS = ('event', 'credibility', 'attribution', 'assets', 'direction', 'horizon_h', 'levels',
          'invalidation', 'confidence', 'analogs', 'materials', 'pushed')
FORBIDDEN = ('order', 'position', 'wallet', 'private_key', 'seed', 'pairing_code')


def now():
    return dt.datetime.now().astimezone()


def rows():
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text(encoding='utf-8').splitlines() if l.strip()]


def write_all(rs):
    tmp = LEDGER.with_suffix('.tmp')
    tmp.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rs), encoding='utf-8')
    os.replace(tmp, LEDGER)


def cmd_add(a):
    src = Path(a.json).read_text(encoding='utf-8') if a.json != '-' else sys.stdin.read()
    j = json.loads(src)
    bad = [k for k in j if any(f in k.lower() for f in FORBIDDEN)]
    if bad:
        sys.exit(f'账本只记判断，不记交易信息：{bad}')
    missing = [k for k in ('event', 'direction', 'invalidation') if not j.get(k)]
    if missing:
        sys.exit(f'缺少必填字段：{missing}（没有「什么情况说明判断错了」的判断不能入账）')
    t = now()
    rec = {'id': f"j{t:%Y%m%d%H%M%S}", 'ts': t.isoformat(timespec='seconds'), 'outcome': 'pending'}
    rec.update({k: j[k] for k in FIELDS if k in j})
    rec.setdefault('horizon_h', 24)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps({'ok': True, 'id': rec['id']}, ensure_ascii=False))
    return 0


def cmd_due(a):
    t = now()
    due = [r for r in rows() if r.get('outcome') == 'pending'
           and dt.datetime.fromisoformat(r['ts']) + dt.timedelta(hours=float(r.get('horizon_h', 24))) <= t]
    print(json.dumps({'count': len(due), 'due': due}, ensure_ascii=False, indent=1))
    return 0


def cmd_resolve(a):
    rs = rows()
    hit = next((r for r in rs if r['id'] == a.id), None)
    if not hit:
        sys.exit(f'没有这条：{a.id}')
    hit.update(outcome=a.outcome, resolved_at=now().isoformat(timespec='seconds'))
    if a.price is not None:
        hit['price_at_review'] = a.price
    if a.note:
        hit['review_note'] = a.note
    write_all(rs)
    print(json.dumps({'ok': True, 'id': a.id, 'outcome': a.outcome}, ensure_ascii=False))
    return 0


def cmd_stats(a):
    since = now() - dt.timedelta(days=a.days)
    rs = [r for r in rows() if dt.datetime.fromisoformat(r['ts']) >= since]
    done = [r for r in rs if r.get('outcome') in ('hit', 'miss', 'partial')]

    def rate(group):
        if not group:
            return None
        score = sum(1 if r['outcome'] == 'hit' else 0.5 if r['outcome'] == 'partial' else 0 for r in group)
        return round(score / len(group), 2)

    by_asset, by_conf = {}, {}
    for r in done:
        for asset in (r.get('assets') or ['?']):
            by_asset.setdefault(str(asset), []).append(r)
        c = r.get('confidence')
        band = '高' if isinstance(c, (int, float)) and c >= 0.7 else '中' if isinstance(c, (int, float)) and c >= 0.4 else '低/未填'
        by_conf.setdefault(band, []).append(r)
    print(json.dumps({
        'days': a.days, 'total': len(rs), 'reviewed': len(done),
        'pending': sum(r.get('outcome') == 'pending' for r in rs),
        'hit_rate': rate(done),
        'by_asset': {k: {'n': len(v), 'hit_rate': rate(v)} for k, v in by_asset.items()},
        'by_confidence': {k: {'n': len(v), 'hit_rate': rate(v)} for k, v in by_conf.items()},
    }, ensure_ascii=False, indent=1))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('add'); s.add_argument('--json', required=True, help='判断 JSON 文件，- 表示标准输入'); s.set_defaults(fn=cmd_add)
    s = sub.add_parser('due'); s.set_defaults(fn=cmd_due)
    s = sub.add_parser('resolve'); s.add_argument('id'); s.add_argument('outcome', choices=('hit', 'miss', 'partial', 'void'))
    s.add_argument('--price', type=float); s.add_argument('--note'); s.set_defaults(fn=cmd_resolve)
    s = sub.add_parser('stats'); s.add_argument('--days', type=int, default=7); s.set_defaults(fn=cmd_stats)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == '__main__':
    raise SystemExit(main())
