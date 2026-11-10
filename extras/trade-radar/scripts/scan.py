#!/usr/bin/env python3
"""交易雷达：扫一遍价格和关键词，判断要不要触发分析，触发了就打包一份材料。

  python3 scan.py [--config config.json]

只做三件事：取数据、和上次比、判断有没有达到触发条件。
不分析、不下单。触发后由 Agent 读材料包，按岗位说明自己分析，再决定推不推送。

输出（标准输出一行 JSON）：
  {"triggered": false, ...}                         没事，Bot 什么都不用说
  {"triggered": true, "materials": "<路径>", ...}   有事，Bot 读材料包开始分析

状态存在 TRADE_HOME/state.json：价格历史（默认留 6 小时）、提醒的上膛状态、看过的推文 ID。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib' / 'aisa'))
import sources  # noqa: E402
from client import AisaError, STATS  # noqa: E402

HOME = Path(os.environ.get('TRADE_HOME', '.'))
STATE = HOME / 'state.json'
MATERIALS = HOME / 'materials'
KEEP_HOURS = 6


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return default


def save(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, p)


def number(obj, keys):
    """在返回结构里按字段名找第一个数字（各接口字段名不统一）。"""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k in keys:
                v = cur.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
            stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def price_ago(history: list, minutes: int):
    """history: [[iso时间, 价格], ...]，找 minutes 分钟前最接近的一条。"""
    target = now() - dt.timedelta(minutes=minutes)
    older = [h for h in history if dt.datetime.fromisoformat(h[0]) <= target]
    return older[-1][1] if older else None


def check_moves(state, cfg, quotes, triggers):
    window = int(cfg.get('move_window_min', 15))
    for asset, q in quotes.items():
        hist = state['history'].setdefault(asset, [])
        before = price_ago(hist, window)
        hist.append([now().isoformat(timespec='seconds'), q['price']])
        cutoff = now() - dt.timedelta(hours=KEEP_HOURS)
        state['history'][asset] = [h for h in hist if dt.datetime.fromisoformat(h[0]) >= cutoff]
        limit = q['move_pct']
        if before:
            pct = (q['price'] - before) / before * 100
            q[f'change_{window}m_pct'] = round(pct, 2)
            if abs(pct) >= limit:
                triggers.append({'type': 'price_move', 'asset': asset, 'window_min': window,
                                 'from': before, 'to': q['price'], 'change_pct': round(pct, 2), 'limit_pct': limit})


def check_alerts(state, cfg, quotes, triggers):
    """价格提醒：跌破 below / 涨破 above 各提醒一次，回到 rearm 以上/以下才重新上膛。"""
    armed = state.setdefault('armed', {})
    for i, al in enumerate(cfg.get('price_alerts', [])):
        q = quotes.get(al['asset'])
        if not q:
            continue
        p, key = q['price'], f"{al['asset']}#{i}"
        if 'below' in al:
            if p < al['below'] and armed.get(key, True):
                triggers.append({'type': 'price_alert', 'asset': al['asset'], 'rule': f"跌破 {al['below']}", 'price': p})
                armed[key] = False
            elif p >= al.get('rearm', al['below']):
                armed[key] = True
        elif 'above' in al:
            if p >= al['above'] and armed.get(key, True):
                triggers.append({'type': 'price_alert', 'asset': al['asset'], 'rule': f"涨破 {al['above']}", 'price': p})
                armed[key] = False
            elif p <= al.get('rearm', al['above']):
                armed[key] = True


def scan_keywords(state, cfg, triggers, errors):
    seen = set(state.get('seen_tweets', []))
    words = [w.lower() for w in cfg.get('keywords', [])]
    hits = []
    for query in cfg.get('x_queries', []):
        try:
            res = sources.twitter_search(query)
        except AisaError as e:
            errors.append(f'twitter_search({query}): {e}')
            continue
        for t in res.get('tweets') or res.get('data') or []:
            tid = str(t.get('id') or t.get('id_str') or '')
            if not tid or tid in seen:
                continue
            seen.add(tid)
            text = t.get('text') or t.get('full_text') or ''
            matched = [w for w in words if w in text.lower()]
            if not matched:
                continue
            author = (t.get('author') or {}).get('userName') or t.get('screen_name') or ''
            hits.append({'id': tid, 'author': author, 'text': text[:600], 'matched': matched,
                         'created_at': t.get('createdAt') or t.get('created_at'),
                         'url': t.get('url') or (f'https://x.com/{author}/status/{tid}' if author else None),
                         'likes': t.get('likeCount'), 'retweets': t.get('retweetCount')})
    state['seen_tweets'] = list(seen)[-3000:]
    if hits:
        triggers.append({'type': 'keyword', 'count': len(hits), 'matched': sorted({w for h in hits for w in h['matched']})})
    return hits


def get_quotes(cfg, errors):
    quotes = {}
    coins = cfg.get('coins', [])
    if coins:
        try:
            res = sources.coin_prices([c['id'] for c in coins])
            for c in coins:
                d = res.get(c['id']) or {}
                if 'usd' in d:
                    quotes[c['id']] = {'symbol': c.get('symbol', c['id']), 'price': float(d['usd']),
                                       'change_24h_pct': round(d.get('usd_24h_change') or 0, 2),
                                       'move_pct': c.get('move_pct', cfg.get('default_move_pct', 3))}
        except AisaError as e:
            errors.append(f'coin_prices: {e}')
    for s in cfg.get('stocks', []):
        try:
            res = sources.stock_snapshot(s['ticker'])
            p = number(res, ('price', 'last', 'close', 'day_close'))
            if p is not None:
                quotes[s['ticker']] = {'symbol': s['ticker'], 'price': p,
                                       'day_change_pct': number(res, ('day_change_percent', 'change_percent')),
                                       'move_pct': s.get('move_pct', 5)}
        except AisaError as e:
            errors.append(f"stock_snapshot({s['ticker']}): {e}")
    return quotes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', default=os.environ.get('TRADE_CONFIG', str(HOME / 'config.json')))
    ap.add_argument('--no-keywords', action='store_true', help='这次只看价格，不搜 X（省钱）')
    a = ap.parse_args()
    cfg = load(Path(a.config), None)
    if cfg is None:
        sys.exit(f'找不到配置文件 {a.config}，先复制 config.example.json 改一份')

    state = load(STATE, {'history': {}, 'armed': {}, 'seen_tweets': []})
    triggers, errors = [], []
    quotes = get_quotes(cfg, errors)
    check_moves(state, cfg, quotes, triggers)
    check_alerts(state, cfg, quotes, triggers)
    tweets = [] if a.no_keywords else scan_keywords(state, cfg, triggers, errors)
    state['last_scan'] = now().isoformat(timespec='seconds')
    save(STATE, state)

    out = {'triggered': bool(triggers), 'at': state['last_scan'], 'triggers': triggers,
           'quotes': {k: {x: v[x] for x in v if x != 'move_pct'} for k, v in quotes.items()},
           'errors': errors, 'aisa': STATS}
    if triggers:
        MATERIALS.mkdir(parents=True, exist_ok=True)
        path = MATERIALS / f"{now():%Y%m%d-%H%M%S}.json"
        save(path, {**out, 'tweets': tweets,
                    'next_steps': [
                        '核实：aisa_cli.py run perplexity question="<事件> 是否属实，最新进展"',
                        '核实：aisa_cli.py run web_search query="<事件>" days=2',
                        '个股新闻：aisa_cli.py run stock_news ticker=<代码>',
                        '事件概率：aisa_cli.py run polymarket_events tag_slug=crypto',
                    ]})
        out['materials'] = str(path)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
