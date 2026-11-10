#!/usr/bin/env python3
"""AIsa（DataForSEO Google Trends / tikhub）轻量客户端。
口径（2026-10-20 验证）：null 当 0；丢弃 missing_data=true 的未结算点；时间索引为 UTC naive（与 pytrends 一致）。
Key 经 aisa_keyring 在槽位 A/B 间轮流；秘密在 .aisa/keys.env(0600)，日志只记槽位。"""
import os, time, json, threading, datetime as dt
import requests, pandas as pd
import aisa_keyring as _keyring

BASE = 'https://api.aisa.one'
ENVF = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
TRENDS_PATH = '/apis/v1/dataforseo/keywords_data/google_trends/explore/live'
MAX_PRICE = os.environ.get('AISA_MAX_PRICE', '0.02')
CALL_LOG = os.environ.get('AISA_CALL_LOG', os.path.join(os.path.dirname(ENVF), 'aisa_calls.log'))
STATS = dict(calls=0, ok=0, fail=0, cost=0.0)
_LOCK = threading.Lock()

def _key():
    """Acquire next A/B slot. Returns (slot_id, secret). Never print secret."""
    return _keyring.acquire_slot()

class AisaError(Exception): pass

def _log(path, cost, secs, note, slot='-'):
    with _LOCK:
        STATS['calls'] += 1; STATS['cost'] += cost
        try: open(CALL_LOG, 'a').write(f"{dt.datetime.now():%F %T}\t{path}\tslot={slot}\t{cost:.6f}\t{secs:.1f}s\t{note}\n")
        except Exception: pass


def call(method, path, body=None, params=None, max_price=None, timeout=120):
    """单次请求；非 200 或网络错误抛 AisaError。返回 json。
    负载轮流选槽；429/限速不换槽重试；401 停用该槽并如实报错（本请求不静默换身份）。"""
    slot, secret = _key()
    h = {'Authorization': f'Bearer {secret}', 'X-AISA-Max-Price-USD': str(max_price or MAX_PRICE)}
    t = time.time()
    try:
        if method == 'POST': r = requests.post(BASE + path, json=body, headers=h, timeout=timeout)
        else: r = requests.get(BASE + path, params=params, headers=h, timeout=timeout)
    except Exception as e:
        _log(path, 0, time.time() - t, f'exc {type(e).__name__}', slot); STATS['fail'] += 1
        raise AisaError(f'network {type(e).__name__} slot={slot}')
    cost = int(r.headers.get('x-aisa-customer-cost-micros-usd') or 0) / 1e6
    _log(path, cost, time.time() - t, f'http {r.status_code}', slot)
    if r.status_code == 401:
        try:
            _keyring.disable_slot(slot, 'http_401')
        except Exception:
            pass
        STATS['fail'] += 1
        raise AisaError(f'http 401 slot={slot} disabled; not retrying with another identity')
    if r.status_code == 429:
        STATS['fail'] += 1
        raise AisaError(f'http 429 slot={slot}; rate limit respected, no key switch')
    if r.status_code != 200:
        STATS['fail'] += 1; raise AisaError(f'http {r.status_code} slot={slot} {r.text[:120]}')
    try: j = r.json()
    except Exception: STATS['fail'] += 1; raise AisaError(f'bad json slot={slot}')
    STATS['ok'] += 1
    return j


def balance():
    slot, secret = _key()
    r = requests.get(BASE + '/v1/credits/balance', headers={'Authorization': f'Bearer {secret}'}, timeout=30)
    if r.status_code == 401:
        try: _keyring.disable_slot(slot, 'http_401')
        except Exception: pass
        raise AisaError(f'http 401 slot={slot} disabled; not retrying with another identity')
    if r.status_code == 429:
        raise AisaError(f'http 429 slot={slot}; rate limit respected, no key switch')
    j = r.json()
    return dict(media_promo=j['media_promo']['balance_micros_usd'] / 1e6, main=j['available_balance_micros_usd'] / 1e6)


TF_MAP = {'now 7-d': 'past_7_days', 'today 3-m': 'past_90_days', 'now 1-d': 'past_day', 'today 1-m': 'past_30_days',
          'today 12-m': 'past_12_months', 'now 4-H': 'past_4_hours', 'now 1-H': 'past_hour'}

def _explore(kws, time_range, item_types=None, retries=1):
    task = {'keywords': list(kws), 'time_range': TF_MAP.get(time_range, time_range), 'type': 'web'}
    if item_types: task['item_types'] = item_types
    last = None
    for i in range(retries + 1):
        try:
            j = call('POST', TRENDS_PATH, [task])
            t = (j.get('tasks') or [{}])[0]
            if t.get('status_code') != 20000: raise AisaError(f"task {t.get('status_code')} {t.get('status_message')}")
            res = (t.get('result') or [None])[0]
            if not res: raise AisaError('empty result')
            return res
        except AisaError as e:
            last = e; time.sleep(2 + 3 * i)
    raise last

def interest_over_time(kws, time_range='past_7_days', retries=1):
    """等价于 pytrends interest_over_time()（无 isPartial 列）：UTC naive 索引，列=kws，null->0，丢未结算点。"""
    res = _explore(kws, time_range, ['google_trends_graph'], retries)
    items = [x for x in (res.get('items') or []) if x.get('type') == 'google_trends_graph']
    if not items: return pd.DataFrame(columns=list(kws))          # 任务成功但无数据（全为 0），与 pytrends 返回空表一致
    it = items[0]
    n = len(it.get('keywords') or kws)
    if n != len(kws): raise AisaError(f'keyword count mismatch {n}/{len(kws)}')
    rows, idx = [], []
    for p in it.get('data') or []:
        if p.get('missing_data'): continue
        vals = p.get('values') or []
        if len(vals) != len(kws): raise AisaError('values length mismatch')
        idx.append(pd.Timestamp(p['timestamp'], unit='s')); rows.append([0 if v is None else v for v in vals])
    if not rows: return pd.DataFrame(columns=list(kws))
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx, name='date'), columns=list(kws))
    return df

def related_rising(keyword, time_range='past_7_days', retries=1):
    """等价于 pytrends related_queries()[kw]['rising']：DataFrame(query, value)，可能为空。"""
    res = _explore([keyword], time_range, ['google_trends_queries_list'], retries)
    q = [x for x in (res.get('items') or []) if x.get('type') == 'google_trends_queries_list']
    rising = ((q[0].get('data') or {}).get('rising') or []) if q else []
    return pd.DataFrame([dict(query=x.get('query'), value=x.get('value')) for x in rising if x.get('query')],
                        columns=['query', 'value'])

def score_vs_gpts(df, terms, gpts='GPTs'):
    """newterm.py 的打分口径：剔除最后 24h 后均值比、按天倍数（UTC 日）、峰值日、近 24h、spike、走势。"""
    out = {}
    cutoff = df.index.max() - pd.Timedelta(hours=24)
    st = df[df.index <= cutoff]; g = st[gpts].mean()
    for t in terms:
        c = {}
        s = df[t]; ss = st[t]
        c['ratio'] = round(ss.mean() / g, 2) if g > 0 else 0
        if g == 0 and ss.mean() > 0: c['err'] = 'GPTs 被压成 0，无法算倍数（多为新闻爆点）'; c['ratio'] = 0
        daily = ss.resample('D').mean(); gd = st[gpts].resample('D').mean()
        c['daily'] = {d.strftime('%m/%d'): round(v / gv, 2) for d, v, gv in zip(daily.index, daily, gd) if gv > 0}
        c['peak_day'] = max(c['daily'], key=c['daily'].get) if c['daily'] and max(c['daily'].values()) > 0 else '-'
        c['last24_ratio'] = round(s[s.index > cutoff].mean() / g, 2) if g > 0 else 0
        last, peak = (daily.iloc[-1] if len(daily) else 0), daily.max()
        first = daily.iloc[:2].mean() if len(daily) >= 2 else 0
        c['spike'] = bool((ss > 0).mean() < 0.15)
        if peak == 0: c['trend'] = '无数据'
        elif last >= peak * 0.9 and last > first * 1.2: c['trend'] = '在涨'
        elif last >= peak * 0.7: c['trend'] = '到顶/高位'
        else: c['trend'] = '在回落'
        c['active'] = bool(ss.max() > 0)
        out[t] = c
    return out

# ---------- tikhub ----------
TIKHUB = '/apis/v1/tikhub/tiktok'
def tiktok_video_search(keyword, publish_time=7, sort_type=0, offset=0, count=20, region='US'):
    return call('GET', TIKHUB + '/app/v3/fetch_video_search_result', params=dict(
        keyword=keyword, count=count, offset=offset, publish_time=publish_time, sort_type=sort_type, region=region), max_price='0.005')
def tiktok_hashtag_search(keyword, count=5):
    return call('GET', TIKHUB + '/app/v3/fetch_hashtag_search_result', params=dict(keyword=keyword, count=count), max_price='0.005')
def tiktok_hashtag_videos(ch_id, cursor=0, count=20):
    return call('GET', TIKHUB + '/app/v3/fetch_hashtag_video_list', params=dict(ch_id=ch_id, cursor=cursor, count=count), max_price='0.005')
