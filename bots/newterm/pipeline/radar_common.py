#!/usr/bin/env python3
"""雷达公共函数：已知词库（pushed.json + tiktok_pool.json + 雷达历史）、归一化、时间。"""
import os, re, json, datetime as dt
D = os.path.dirname(os.path.abspath(__file__))
RD = os.path.join(D, 'radar'); os.makedirs(RD, exist_ok=True)
TZ = dt.timezone(dt.timedelta(hours=8))
def now(): return dt.datetime.now(TZ)
def nows(): return now().strftime('%Y-%m-%d %H:%M')
def today(): return now().strftime('%Y-%m-%d')
def norm(s): return re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower()).split()
def key(s): return ''.join(norm(s))
FILLER = set('ai video videos trend trends filter effect generator template templates meme memes edit tiktok viral the a an'.split())
def core_key(s):
    w = [x for x in norm(s) if x not in FILLER]
    return ''.join(w) or key(s)

def load_json(p, default):
    try: return json.load(open(p))
    except Exception: return default
def save_json(p, obj):
    tmp = p + '.tmp'; json.dump(obj, open(tmp, 'w'), ensure_ascii=False, indent=1); os.replace(tmp, p)

def known_index():
    """返回 {core_key: (来源, 原词, 日期)}；只读 pushed.json / tiktok_pool.json。"""
    idx = {}
    for k, dates in load_json(os.path.join(D, 'pushed.json'), {}).items():
        ck = core_key(k) if ' ' in k else k
        idx.setdefault(k, ('pushed', k, (dates or [''])[0]))
    for k, m in load_json(os.path.join(D, 'tiktok_pool.json'), {'memes': {}})['memes'].items():
        for s in [m.get('name', k)] + m.get('spellings', []):
            idx.setdefault(core_key(s), ('tiktok_pool', m.get('name', k), m.get('first_seen', '')))
    return idx

def match_known(name, idx):
    ck = core_key(name)
    if not ck: return None
    if ck in idx: return idx[ck]
    k2 = key(name)
    if k2 in idx: return idx[k2]
    if len(ck) >= 6:
        for kk, v in idx.items():
            if len(kk) >= 6 and (kk in ck or ck in kk) and min(len(kk), len(ck)) / max(len(kk), len(ck)) >= 0.6:
                return v
    return None
