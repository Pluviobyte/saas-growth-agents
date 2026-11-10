#!/usr/bin/env python3
"""TikTok 梗词扫描（预跑用）。
用法: python3 tiktok_scan.py <slot> [--date YYYYMMDD] [--x-input PATH] [--no-trends]
  slot: morning | noon | evening | test …；输出 prescan_<date>_<slot>/tiktok.json + TIKTOK_DONE
流程:
 1) tikhub 泛搜（9 个关键词 × 相关度/点赞 × 2 页，近 7 天）+ 标签 aitrend/aifilter/capcutaitrend 视频
 2) 合并 X / 标签页输入文件（routine 写，默认 prescan_<date>_<slot>/tiktok_x_input.json）进梗池 tiktok_pool.json
 3) 梗池里每个梗按名字直搜 tikhub（不限时间、相关度），取近 30 天内重复出现的最早视频日期 = 出现时间
 4) 每个梗的写法经 aisa_trends 跟 GPTs 比（全球 past_7_days，4 词 + GPTs 一组），≥ 0.05 为过线，否则早期观察
"""
import os, sys, re, json, time, datetime as dt, argparse, traceback
from concurrent.futures import ThreadPoolExecutor
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import aisa_trends as AT
import pandas as pd

TZ = dt.timezone(dt.timedelta(hours=8))
THRESH = float(os.environ.get('TIKTOK_THRESH', 0.05))
POOL_DAYS = 14
GEN_KEYWORDS = ['ai trend', 'ai filter', 'ai video', 'capcut ai', 'capcut template', 'ai trend tutorial',
                'ai dance', 'photo to video', 'how to make this trend']
HASHTAGS = ['aitrend', 'aifilter', 'capcutaitrend']
GENERIC = set("""ai trend trends trending filter filters video videos capcut template templates tutorial how to make
the a an this that viral new edit effect free app with your you my in of for and on is it photo photos pic
dance tiktok fyp foryou foryoupage pioneer capcutpioneer pioneertemplate generator maker meme memes""".split())

def norm(s): return re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower()).split()
def key(s): return ''.join(norm(s))
def today(): return dt.datetime.now(TZ).date()

# ---------------- tikhub ----------------
def vids(resp):
    out = []
    d = (resp or {}).get('data') or {}
    for it in (d.get('search_item_list') or d.get('aweme_list') or []):
        a = it.get('aweme_info', it) if isinstance(it, dict) else {}
        if not a or not a.get('aweme_id'): continue
        st = a.get('statistics') or {}
        tags = [t.get('hashtag_name') for t in (a.get('text_extra') or []) if t.get('hashtag_name')]
        au = (a.get('author') or {}).get('unique_id') or ''
        out.append(dict(id=str(a['aweme_id']), ts=a.get('create_time', 0),
                        date=dt.datetime.fromtimestamp(a.get('create_time', 0), TZ).strftime('%Y-%m-%d'),
                        play=st.get('play_count') or 0, like=st.get('digg_count') or 0,
                        desc=(a.get('desc') or '')[:300], tags=tags, music=((a.get('music') or {}).get('title') or '')[:100],
                        author=au, url=f"https://www.tiktok.com/@{au}/video/{a['aweme_id']}" if au else ''))
    return out

def safe(fn, *a, **k):
    try: return fn(*a, **k)
    except Exception as e:
        ERR.append(f"{fn.__name__}{a}: {str(e)[:120]}"); return None
ERR = []
KNOWN_CORES = []

def generic_pool():
    jobs = [(k, s, off) for k in GEN_KEYWORDS for s in (0, 1) for off in (0, 20)]
    pool = {}
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda j: safe(AT.tiktok_video_search, j[0], publish_time=7, sort_type=j[1], offset=j[2]), jobs))
    for (k, s, off), r in zip(jobs, res):
        for v in vids(r): pool.setdefault(v['id'], v).setdefault('src', set()).add('search:' + k)
    tags = {}
    for t in HASHTAGS:
        r = safe(AT.tiktok_hashtag_search, t)
        ch = None
        for c in ((r or {}).get('data') or {}).get('challenge_list') or []:
            ci = c.get('challenge_info', c)
            if (ci.get('cha_name') or '').lower() == t:
                ch = ci.get('cid'); tags[t] = dict(views=ci.get('view_count'), users=ci.get('user_count')); break
        cur = 0
        for _ in range(2):
            if not ch: break
            r = safe(AT.tiktok_hashtag_videos, ch, cursor=cur)
            for v in vids(r): pool.setdefault(v['id'], v).setdefault('src', set()).add('hashtag:' + t)
            cur = ((r or {}).get('data') or {}).get('cursor') or 0
            if not cur: break
    return pool, tags

def text(v): return ' '.join(norm(v['desc'] + ' ' + ' '.join(v['tags']) + ' ' + v['music']))
def stem(w): return re.sub(r'(ing|es|s)$', '', w) if len(w) > 4 else w
def core(term): return [stem(w) for w in (norm(term) if not [w for w in norm(term) if w not in GENERIC] else [w for w in norm(term) if w not in GENERIC])]
def matches(v, terms):
    t = text(v); tc = t.replace(' ', '')
    for term in terms:
        c = core(term)
        if c and (all(re.search(r'\b' + re.escape(w), t) for w in c) or ''.join(c) in tc): return True   # 词首匹配，兼容复数/ing
    return False

# 从泛搜视频文案里抽候选梗名（启发式；routine 也会看 tikhub_top_unmatched 自行判断）
PAT = [r'how to (?:make|do|create) (?:the |this |that )?(?:viral |new |trending )?["“]?([a-z0-9 \'’]{3,40}?)["”]? (?:ai )?(?:trend|edit|filter|video|effect)',
       r'["“]([a-z0-9 \'’]{4,40})["”] (?:ai )?(?:trend|edit|filter|template)',
       r'\b([a-z0-9]+(?: [a-z0-9]+){0,3}) ai (?:trend|filter|edit|dance|video) tutorial',
       r'learn how to make (?:the )?viral ["“]?([a-z0-9 \'’]{3,40}?)["”]? ']
def auto_candidates(pool, known):
    cnt = {}
    for v in pool.values():
        d = (v['desc'] or '').lower()
        for p in PAT:
            for m in re.finditer(p, d):
                name = ' '.join(norm(m.group(1)))
                c = core(name)
                if not c or len(name) < 4 or len(c) > 4 or len(set(c)) < len(c): continue   # 太长或词重复的多半是文案碎片
                k = ''.join(c)
                if any(k == kk or k in kk or kk in k for kk in known if len(kk) >= 4): continue
                if any(set(c) <= set(kc) or set(kc) <= set(c) for kc in KNOWN_CORES): continue
                e = cnt.setdefault(k, dict(name=name, videos=set(), authors=set(), play=0))
                if v['id'] not in e['videos']:
                    e['videos'].add(v['id']); e['authors'].add(v['author']); e['play'] += v['play']
    # 至少 2 个不同作者；只有 1 个核心词的要 3 个作者（避免 tonight 这类普通词）
    out = [e for e in cnt.values() if len(e['authors']) >= (3 if len(core(e['name'])) == 1 else 2)]
    return sorted(out, key=lambda e: -e['play'])[:10]

# ---------------- 梗池 ----------------
POOLF = os.environ.get('TIKTOK_POOL_FILE') or os.path.join(D, 'tiktok_pool.json')   # 夜间采集用副本，不动正式梗池
def load_pool():
    return json.load(open(POOLF)) if os.path.exists(POOLF) else {'memes': {}}
def upsert(pool, name, spellings, source, day, desc='', urls=None):
    k = key(name)
    for kk, m in pool['memes'].items():          # 名字或任一写法核心相同即视为同一个梗
        if kk == k or any(''.join(core(s)) == ''.join(core(name)) for s in m['spellings']): k = kk; break
    m = pool['memes'].setdefault(k, dict(name=name, spellings=[], first_seen=day, sources={}, desc='', urls=[]))
    for s in spellings or []:
        s = ' '.join(norm(s))
        if s and s not in m['spellings']: m['spellings'].append(s)
    if not m['spellings']: m['spellings'].append(' '.join(norm(name)) + ' ai')
    m['sources'][source] = day
    m['first_seen'] = min(m['first_seen'], day)
    if desc and not m.get('desc'): m['desc'] = desc[:300]
    for u in urls or []:
        if u not in m['urls']: m['urls'].append(u)
    m['last_seen'] = max(m.get('last_seen', day), day)
    return k

def appeared(videos, terms):
    """近 30 天内、7 天窗口里至少 2 条匹配视频的最早日期 = 出现时间"""
    cut = (today() - dt.timedelta(days=30)).isoformat()
    hits = sorted([v for v in videos if matches(v, terms)], key=lambda v: v['ts'])
    rec = [v for v in hits if v['date'] >= cut]
    for i, v in enumerate(rec):
        d0 = dt.date.fromisoformat(v['date'])
        if sum(1 for w in rec[i:] if dt.date.fromisoformat(w['date']) <= d0 + dt.timedelta(days=7)) >= 2:
            return v, hits
    return (rec[0] if rec else None), hits

def score_terms(terms):
    """terms 各自跟 GPTs 比，4 个一组；组内 GPTs 被压扁时把小词单独重查"""
    res = {}
    todo = list(dict.fromkeys(terms))
    for rnd in range(2):
        groups = [todo[i:i+4] for i in range(0, len(todo), 4)]
        def one(g):
            try: return AT.interest_over_time(g + ['GPTs'], 'past_7_days', retries=1)
            except Exception as e: ERR.append(f"trends {g}: {str(e)[:100]}"); return None
        with ThreadPoolExecutor(4) as ex: dfs = list(ex.map(one, groups))
        todo = []
        for g, df in zip(groups, dfs):
            if df is None: continue
            if df.empty:
                for t in g: res[t] = dict(ratio=0, last24_ratio=0, daily={}, peak_day='-', trend='无数据', spike=True, active=False)
                continue
            sc = AT.score_vs_gpts(df, g)
            res.update(sc)
            cut = df.index.max() - pd.Timedelta(hours=24)
            gm = df[df.index <= cut]['GPTs'].mean()
            if gm < 5 and rnd == 0 and len(g) > 1:
                means = {t: df[df.index <= cut][t].mean() for t in g}; top = max(means.values())
                todo += [t for t in g if means[t] < top * 0.3]
        if not todo: break
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('slot'); ap.add_argument('--date', default=dt.datetime.now(TZ).strftime('%Y%m%d'))
    ap.add_argument('--x-input', default=None); ap.add_argument('--no-trends', action='store_true')
    a = ap.parse_args()
    out_dir = os.path.join(D, f'prescan_{a.date}_{a.slot}'); os.makedirs(out_dir, exist_ok=True)
    for f in ('TIKTOK_DONE', 'TIKTOK_FAILED'):
        try: os.remove(os.path.join(out_dir, f))
        except FileNotFoundError: pass
    t0 = time.time(); c0 = dict(AT.STATS); day = today().isoformat()
    pool = load_pool()

    # 1) X / 标签页输入
    xin = a.x_input or os.path.join(out_dir, 'tiktok_x_input.json')
    xin_n = 0
    if os.path.exists(xin):
        try:
            j = json.load(open(xin))
            for it in j.get('memes', []):
                src = {'x': 'X', 'tag': 'tag', 'tag page': 'tag', 'browser': 'tag'}.get(str(it.get('source', 'X')).lower(), it.get('source', 'X'))
                upsert(pool, it['name'], it.get('spellings') or [], src, day, it.get('desc', ''), it.get('urls'))
                xin_n += 1
        except Exception as e: ERR.append(f'x-input: {e}')

    # 2) tikhub 泛搜
    gpool, tags = generic_pool()
    known = [''.join(core(s)) for m in pool['memes'].values() for s in m['spellings'] + [m['name']]]
    KNOWN_CORES[:] = [core(s) for m in pool['memes'].values() for s in m['spellings'] + [m['name']]]
    autos = auto_candidates(gpool, known)
    for e in autos:
        kk = upsert(pool, e['name'], [e['name'] + ' ai', e['name']], 'tikhub', day, f"tikhub 泛搜自动抽取：{len(e['videos'])} 条视频 / {len(e['authors'])} 个作者，合计 {e['play']} 播放")
        pool['memes'][kk]['auto'] = True
    for k, m in pool['memes'].items():          # 泛搜里出现过 = tikhub 也看到了
        hit = [v for v in gpool.values() if matches(v, m['spellings'] + [m['name']])]
        if hit:
            m['sources']['tikhub'] = day; m['last_seen'] = day
            m['generic_hits'] = len(hit); m['generic_top_play'] = max(v['play'] for v in hit)

    # 3) 清理过期梗：最近 14 天没再出现且上次 < 0.05
    cutd = (today() - dt.timedelta(days=POOL_DAYS)).isoformat(); dropped = []
    for k in list(pool['memes']):
        m = pool['memes'][k]
        if m.get('last_seen', m['first_seen']) < cutd and (m.get('latest') or {}).get('ratio', 0) < THRESH:
            dropped.append(m['name']); del pool['memes'][k]

    # 4) 按名字直搜，定出现时间
    items = list(pool['memes'].items())
    def direct(km):
        k, m = km
        q = m['spellings'][0] if m['spellings'] else m['name']
        return safe(AT.tiktok_video_search, q, publish_time=0, sort_type=0)
    with ThreadPoolExecutor(4) as ex: dres = list(ex.map(direct, items))
    for (k, m), r in zip(items, dres):
        vs = vids(r); terms = m['spellings'] + [m['name']]
        first, hits = appeared(vs, terms)
        cut30 = (today() - dt.timedelta(days=30)).isoformat()
        older = [v for v in hits if v['date'] < cut30]
        m['direct'] = dict(matched=len(hits), of=len(vs), checked=day, older_than_30d=len(older),
                           earliest_any=min((v['date'] for v in hits), default=None))
        if first:
            m['appeared'] = first['date']; m['appeared_url'] = first['url']
        if hits:
            top = max(hits, key=lambda v: v['play']); m['top_play'] = top['play']; m['top_url'] = top['url']

    # 5) Trends 跟 GPTs 比
    if not a.no_trends:
        prim = {k: m['spellings'][0] for k, m in pool['memes'].items() if m['spellings']}
        sc = score_terms(list(prim.values()))
        alt = {}
        for k, m in pool['memes'].items():          # 主写法为 0 时再试一个备选写法
            s = sc.get(prim.get(k), {})
            if s and s.get('ratio', 0) == 0 and len(m['spellings']) > 1: alt[k] = m['spellings'][1]
        sc.update(score_terms(list(alt.values())) if alt else {})
        for k, m in pool['memes'].items():
            cands = [t for t in (prim.get(k), alt.get(k)) if t and t in sc]
            if not cands: continue
            best = max(cands, key=lambda t: sc[t].get('ratio', 0))
            s = sc[best]
            m['latest'] = dict(term=best, ratio=s.get('ratio', 0), last24_ratio=s.get('last24_ratio', 0), trend=s.get('trend'),
                               peak_day=s.get('peak_day'), daily=s.get('daily'), spike=s.get('spike'), scored_at=dt.datetime.now(TZ).strftime('%F %T'),
                               tried=cands)
            m.setdefault('history', []).append(dict(at=m['latest']['scored_at'], term=best, ratio=m['latest']['ratio']))
            m['history'] = m['history'][-20:]

    json.dump(pool, open(POOLF, 'w'), ensure_ascii=False, indent=1)

    # 6) 输出
    pushed = json.load(open(os.path.join(D, 'pushed.json'))) if os.path.exists(os.path.join(D, 'pushed.json')) else {}
    rows = []
    for k, m in pool['memes'].items():
        L = m.get('latest') or {}
        rows.append(dict(name=m['name'], term=L.get('term'), ratio=L.get('ratio'), last24_ratio=L.get('last24_ratio'), trend=L.get('trend'),
                         peak_day=L.get('peak_day'), daily=L.get('daily'), tried=L.get('tried'),
                         appeared=m.get('appeared'), appeared_basis='tikhub 近 30 天内重复出现的最早视频' if m.get('appeared') else None,
                         appeared_note=(f"30 天前已有 {m['direct']['older_than_30d']} 条同名视频（最早 {m['direct']['earliest_any']}），可能是老梗翻红或同名" if (m.get('direct') or {}).get('older_than_30d') else ''),
                         tikhub_direct_matched=(m.get('direct') or {}).get('matched', 0),
                         needs_review=bool(m.get('auto')),
                         appeared_url=m.get('appeared_url'), top_play=m.get('top_play'), top_url=m.get('top_url'),
                         sources=sorted(m['sources']), found_by_this_run=sorted(k2 for k2, v2 in m['sources'].items() if v2 == day), first_seen=m['first_seen'], desc=m.get('desc', ''), urls=m.get('urls', [])[:3],
                         generic_hits=m.get('generic_hits', 0) if m['sources'].get('tikhub') == day else 0,
                         pushed_dates=pushed.get(key(L.get('term') or ''), []) or pushed.get(key(m['name']), [])))
    passed = sorted([r for r in rows if (r['ratio'] or 0) >= THRESH], key=lambda r: -(r['ratio'] or 0))
    early = sorted([r for r in rows if r['ratio'] is not None and (r['ratio'] or 0) < THRESH], key=lambda r: -(r['ratio'] or 0))
    unmatched = [v for v in gpool.values() if not any(matches(v, m['spellings'] + [m['name']]) for m in pool['memes'].values())]
    unmatched = sorted(unmatched, key=lambda v: -v['play'])[:30]
    cost = AT.STATS['cost'] - c0['cost']; calls = AT.STATS['calls'] - c0['calls']
    res = dict(date=a.date, slot=a.slot, generated_at=dt.datetime.now(TZ).strftime('%F %T'), threshold=THRESH,
               runtime_s=round(time.time() - t0), aisa_calls=calls, aisa_cost_usd=round(cost, 4),
               x_input=dict(path=xin, found=os.path.exists(xin), memes=xin_n),
               generic=dict(keywords=GEN_KEYWORDS, hashtags=tags, videos=len(gpool)),
               auto_candidates=[dict(name=e['name'], videos=len(e['videos']), play=e['play']) for e in autos],
               passed=passed, early_watch=early, dropped_from_pool=dropped,
               tikhub_top_unmatched=[dict(date=v['date'], play=v['play'], desc=v['desc'][:160], music=v['music'], url=v['url']) for v in unmatched],
               errors=ERR[:50])
    json.dump(res, open(os.path.join(out_dir, 'tiktok.json'), 'w'), ensure_ascii=False, indent=1)
    open(os.path.join(out_dir, 'TIKTOK_DONE'), 'w').write(res['generated_at'])
    print(f"tiktok_scan 完成：过线 {len(passed)}，早期观察 {len(early)}，梗池 {len(pool['memes'])}，AIsa {calls} 次 ${cost:.3f}，用时 {res['runtime_s']}s，错误 {len(ERR)}")

if __name__ == '__main__':
    try: main()
    except Exception:
        traceback.print_exc()
        try:
            a = sys.argv[1] if len(sys.argv) > 1 else 'unknown'
            dd = next((sys.argv[i+1] for i, x in enumerate(sys.argv) if x == '--date'), dt.datetime.now(TZ).strftime('%Y%m%d'))
            od = os.path.join(D, f'prescan_{dd}_{a}'); os.makedirs(od, exist_ok=True)
            open(os.path.join(od, 'TIKTOK_FAILED'), 'w').write(traceback.format_exc()[-2000:])
        except Exception: pass
        sys.exit(1)
