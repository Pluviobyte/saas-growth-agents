#!/usr/bin/env python3
"""每日新词发现：toolify / Google Trends 热搜 / 词根 rising / GitHub / HF -> Google Trends 对比 GPTs -> report_YYYYMMDD.md
2026-10-20 起 Trends 主通道改为 AIsa(DataForSEO google_trends explore/live)，单组失败重试 1 次后回退 pytrends。"""
import json, re, time, random, datetime as dt, os, sys, traceback
from concurrent.futures import ThreadPoolExecutor
import requests, pandas as pd
from pytrends.request import TrendReq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aisa_trends as AT
THREADS = int(os.environ.get('AISA_THREADS', 4))
USE_AISA = os.environ.get('TRENDS_BACKEND', 'aisa') != 'pytrends'
CACHE_TTL_H = float(os.environ.get('CACHE_TTL_H', 18))    # 打分缓存有效期（小时）：同日复用晨间结果，省午晚重复打分
ROOTS_TTL_H = float(os.environ.get('ROOTS_TTL_H', 24))    # 词根 rising 缓存有效期（小时）：日更即可
FALLBACKS = []                                            # 回退到 pytrends 的组

D = os.path.dirname(os.path.abspath(__file__))
TODAY = dt.datetime.now()
STAMP = TODAY.strftime('%Y%m%d')
LOG = []
def log(*a):
    s = ' '.join(str(x) for x in a); print(s, flush=True); LOG.append(s)

ROOTS = ["generator","maker","converter","editor","checker","creator","detector","calculator",
 "ai video","ai image","ai music","tts","translator","remover","upscaler","downloader","simulator",
 "quiz","test","game","template","prompt","filter","chat","ai agent","ai art","ai voice","ai song",
 "ai photo","solver"]
TOOLWORDS = set("""ai video videos image images photo pic art music song voice tts generator gen maker creator editor
converter checker detector calculator translator remover upscaler downloader simulator quiz test game games template
templates prompt prompts filter chat app online free studio dance anime meme avatar maker hub tool tools io lab""".split())
BRANDS = set("""google youtube chatgpt openai gpt gemini claude anthropic apple iphone amazon netflix spotify tiktok instagram facebook
meta whatsapp microsoft copilot adobe photoshop canva capcut midjourney nvidia tesla twitter x reddit discord telegram
pinterest snapchat roblox minecraft fortnite disney pokemon nike samsung android windows excel word notion figma github""".split())
BAD = re.compile(r"(porn|nsfw|xxx|nude|naked|sex|hentai|onlyfans|undress|deepnude|to mp3|to mp4|mp3 converter|downloader for|"
                 r"halloween|christmas|thanksgiving|black friday|valentine|easter|new year|cyber monday|casino|uncensored|abliterated|quantized|bet\b|crack|torrent)")
GENERIC = re.compile(r"\b(mod|mods|warrants?|cricket|alabama|texas|georgia|brewers|guardians|politica|politico|ideologia|challenge|apk|nj|ny|ca|review|comparison|pricing|quotes|essentials|setup|insurance|renovation|learn|products|vs|login)\b")
STOP = set("free online best how what the for and to of in a an with near me app download login apk".split())

def norm(s): return re.sub(r'[^a-z0-9 ]', ' ', s.lower()).split()
def key(s): return ''.join(norm(s))

# ---------------- sources ----------------
def src_toolify():
    from curl_cffi import requests as cr
    from bs4 import BeautifulSoup
    out = []
    r = cr.get('https://www.toolify.ai/new', impersonate='chrome', timeout=40)
    r.raise_for_status()
    s = BeautifulSoup(r.text, 'html.parser'); n = 0
    for c in s.select('.tool-dom'):
        hrefs = [a.get('href') for a in c.find_all('a') if a.get('href')]
        det = next((h for h in hrefs if h.startswith('/tool/')), None)
        site = next((h for h in hrefs if h.startswith('http')), None)
        if not det: continue
        n += 1
        texts = [t for t in c.stripped_strings]
        name, desc = (texts[0] if texts else det), (texts[1] if len(texts) > 1 else '')
        if not site:
            try:
                d = cr.get('https://www.toolify.ai' + det, impersonate='chrome', timeout=30).text
                m = re.search(r'href="(https?://[^"]+)\?utm_source=toolify', d); site = m.group(1) if m else None
            except Exception: pass
        if not site: continue
        host = re.sub(r'^www\.', '', re.sub(r'https?://', '', site).split('/')[0].lower())
        if host.count('.') > 1: continue            # 子域名不算关键词域名
        stem = host.rsplit('.', 1)[0]
        kw = keyword_from_stem(stem)
        if kw: out.append(dict(term=kw, src='toolify', desc=f"{name}：{desc}", url=f"https://{host}", extra=host))
    log(f"[toolify] 卡片 {n} 个，域名像关键词的 {len(out)} 个")
    return out

SUFFIX = sorted(TOOLWORDS, key=len, reverse=True)
def keyword_from_stem(stem):
    """域名主干里带工具词/版本号才算关键词域名，例如 foo47video -> foo 47；纯品牌名(kooko)返回 None"""
    s = stem.replace('-', '')
    if any(b == s or s.startswith(b) for b in BRANDS if len(b) > 3): return None
    core, stripped = s, []
    changed = True
    while changed:
        changed = False
        for w in SUFFIX:
            if core.endswith(w) and len(core) - len(w) >= 3:
                core = core[:-len(w)]; stripped.insert(0, w); changed = True; break
    has_digit = bool(re.search(r'\d', core))
    if not stripped and not has_digit: return None
    core = re.sub(r'([a-z])(\d)', r'\1 \2', core)   # foo47 -> foo 47
    return core.strip() if len(core) >= 3 else None

def src_trending_us():
    r = requests.get('https://trends.google.com/trending/rss?geo=US', timeout=30); r.raise_for_status()
    items = re.findall(r'<item>\s*<title>(.*?)</title>', r.text)
    out = [dict(term=t, src='trends-US热搜', desc='') for t in items
           if set(norm(t)) & TOOLWORDS or re.search(r'\d', t) and not re.search(r'\bvs\b', t.lower())]
    log(f"[Trends US 热搜] 共 {len(items)} 条，带工具/版本特征的 {len(out)} 条（其余多为新闻、体育、人名，跳过）")
    return out, items

def _github_trending_quick(limit=25):
    """轻量拉今日 Trending（HTML overall）；失败返回 []。不写 seen 库。"""
    try:
        from curl_cffi import requests as creq
        r = creq.get('https://github.com/trending?since=daily', impersonate='chrome131', timeout=25)
        text, code = r.text, r.status_code
    except Exception:
        try:
            r = requests.get('https://github.com/trending?since=daily',
                             headers={'User-Agent': 'Mozilla/5.0'}, timeout=25)
            text, code = r.text, r.status_code
        except Exception:
            return []
    if code != 200 or 'Box-row' not in text: return []
    out = []
    for block in re.findall(r'<article class="Box-row">([\s\S]*?)</article>', text)[:limit]:
        hm = re.search(r'<h2[^>]*>\s*<a[^>]*href="(/[^"\s]+)"', block)
        if not hm: continue
        path = hm.group(1).strip('/')
        parts = path.split('/')
        if len(parts) < 2: continue
        full = f'{parts[0]}/{parts[1]}'
        name = re.sub(r'[-_]+', ' ', parts[1]).strip()
        dm = re.search(r'<p class="col-9[^"]*"[^>]*>([\s\S]*?)</p>', block)
        desc = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', dm.group(1))).strip()[:200] if dm else ''
        stm = re.search(r'([\d,]+)\s+stars?\s+today', block, re.I)
        stars_today = int(re.sub(r'[^\d]', '', stm.group(1))) if stm else 0
        out.append(dict(term=name, src='GitHub-trending', desc=desc,
                        url=f'https://github.com/{full}',
                        extra=f"trending daily +{stars_today}★ · {full}"))
    return out

def src_github():
    since = (TODAY - dt.timedelta(days=14)).strftime('%Y-%m-%d')
    headers = {'Accept': 'application/vnd.github+json'}
    tok = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''
    if tok: headers['Authorization'] = f'Bearer {tok}'
    r = requests.get('https://api.github.com/search/repositories',
                     params=dict(q=f'created:>{since}', sort='stars', order='desc', per_page=30),
                     headers=headers, timeout=30); r.raise_for_status()
    out = []
    for it in r.json()['items']:
        age = max((TODAY - dt.datetime.strptime(it['created_at'][:10], '%Y-%m-%d')).days, 1)
        if it['stargazers_count'] / age < 200: continue
        name = re.sub(r'[-_]+', ' ', it['name']).strip()
        out.append(dict(term=name, src='GitHub', desc=(it.get('description') or '')[:200],
                        url=it['html_url'], extra=f"{it['stargazers_count']}★/{age}天"))
    # 合并今日 Trending（去重按归一化 term；同词优先保留已有 GitHub 高流速条目）
    seen_k = {key(c['term']) for c in out}
    trend = _github_trending_quick()
    added = 0
    for c in trend:
        k = key(c['term'])
        if not k or k in seen_k: continue
        seen_k.add(k); out.append(c); added += 1
    log(f"[GitHub] 14 天内建库 top30，日均 200 星以上 {len(out)-added} 个；Trending 合并 +{added}（共 {len(out)}）")
    return out

def src_hf():
    r = requests.get('https://huggingface.co/api/models', params=dict(sort='trendingScore', limit=50, full='false'),
                     timeout=30); r.raise_for_status()
    out = []; cut = TODAY - dt.timedelta(days=30)
    for m in r.json():
        ca = m.get('createdAt', '')[:10]
        if ca and dt.datetime.strptime(ca, '%Y-%m-%d') < cut: continue
        base = m['id'].split('/')[-1]
        base = re.sub(r'(?i)[-_](\d+(\.\d+)?[bm]|instruct|it|base|gguf|fp8|bf16|awq|int4|preview|hf|a\d+b|e\d+b)\b.*$', '', base)
        out.append(dict(term=re.sub(r'[-_]', ' ', base), src='HuggingFace', desc=f"HF 模型 {m['id']}（{m.get('pipeline_tag') or ''}）",
                        url=f"https://huggingface.co/{m['id']}", extra=ca))
    log(f"[HuggingFace] 热门前 50 中 30 天内新建 {len(out)} 个")
    return out

# ---------------- pytrends ----------------
PT = None
def pt():
    global PT
    if PT is None: PT = TrendReq(hl='en-US', tz=-480, timeout=(10, 30))
    return PT
STATS = dict(req=0, fail=0, r429=0)
GAP = [8.0]          # 自适应间隔：429 后加大，成功后慢慢回落
def trends_call(fn, kws, tf='now 7-d', tries=5):
    global PT
    for i in range(tries):
        time.sleep(GAP[0] + random.uniform(0, 4))
        try:
            STATS['req'] += 1
            pt().build_payload(kws, timeframe=tf, geo='')
            r = fn(); log(f"  trends ok {kws[:5]} {tf} (gap {GAP[0]:.0f}s)")
            GAP[0] = max(8.0, GAP[0] * 0.85); return r
        except Exception as e:
            if '429' in str(e):
                STATS['r429'] += 1; GAP[0] = min(60.0, GAP[0] * 1.6)
            log(f"  trends 失败 {kws} 第{i+1}次: {str(e)[:80]}")
            PT = None; time.sleep(30 + 30 * i)
    STATS['fail'] += 1
    return None

def _aisa_iot(kws, tf):
    try:
        STATS['req'] += 1
        return AT.interest_over_time(kws, tf, retries=1)
    except Exception as e:
        log(f"  AIsa 失败 {kws} {tf}: {str(e)[:100]}")
        return None
def fetch_many(groups, tf='now 7-d', tries=5):
    """并行用 AIsa 取 interest_over_time；失败的组逐个回退 pytrends。返回与 groups 对齐的 df 列表（失败为 None）。"""
    if not groups: return []
    out = [None] * len(groups)
    if USE_AISA:
        with ThreadPoolExecutor(THREADS) as ex:
            out = list(ex.map(lambda g: _aisa_iot(g, tf), groups))
        for g, df in zip(groups, out):
            if df is not None: log(f"  aisa ok {g[:5]} {tf}")
    for i, g in enumerate(groups):
        if out[i] is None:
            if USE_AISA: FALLBACKS.append(f"{tf}:{'|'.join(g)}"); log(f"  回退 pytrends {g} {tf}")
            out[i] = trends_call(lambda: pt().interest_over_time(), g, tf=tf, tries=tries)
    return out

MISSED_ROOTS = []
def src_roots():
    cp = os.path.join(D, f'roots_{STAMP}.json')
    fresh = os.path.exists(cp) and (time.time() - os.path.getmtime(cp)) < ROOTS_TTL_H * 3600
    if fresh:                                   # 断点续跑：本轮（ROOTS_TTL_H 内）已扫过的词根结果直接复用
        out = json.load(open(cp)); log(f"[词根扫描] 复用 {ROOTS_TTL_H:g} 小时内缓存 {len(out)} 条")
        mp = cp.replace('.json', '_missed.json')
        if os.path.exists(mp): MISSED_ROOTS[:] = json.load(open(mp))
        return out
    out = _src_roots(); json.dump(out, open(cp, 'w'), ensure_ascii=False)
    json.dump(MISSED_ROOTS, open(cp.replace('.json', '_missed.json'), 'w'), ensure_ascii=False); return out
def _src_roots():
    out = []; ok = []; failed = []
    t0 = time.time(); budget = int(os.environ.get('ROOT_BUDGET', 2400))
    def one(r, tries):
        res = trends_call(lambda: pt().related_queries(), [r], tries=tries)
        if res is None: return False
        df = (res.get(r) or {}).get('rising')
        if df is not None and not df.empty:
            for _, row in df.head(15).iterrows():
                out.append(dict(term=row['query'], src=f'词根rising:{r}', desc='', extra=str(row['value'])))
        return True
    def add(r, df):
        if df is not None and not df.empty:
            for _, row in df.head(15).iterrows():
                out.append(dict(term=row['query'], src=f'词根rising:{r}', desc='', extra=str(row['value'])))
    todo = list(ROOTS)
    if USE_AISA:                                 # AIsa 并行；失败的词根再走 pytrends
        def a1(r):
            try:
                STATS['req'] += 1; return AT.related_rising(r, 'past_7_days', retries=1)
            except Exception as e:
                log(f"  AIsa rising 失败 {r}: {str(e)[:100]}"); return None
        with ThreadPoolExecutor(THREADS) as ex: res = list(ex.map(a1, ROOTS))
        todo = []
        for r, df in zip(ROOTS, res):
            if df is None: todo.append(r); FALLBACKS.append(f'rising:{r}')
            else: add(r, df); ok.append(r)
        log(f"[词根扫描] AIsa 成功 {len(ok)}/{len(ROOTS)}" + (f"，回退 pytrends：{todo}" if todo else ''))
    for r in todo:
        if time.time() - t0 > budget: failed.append(r); continue
        (ok if one(r, 2) else failed).append(r)
    if failed:                                   # 第二轮：放慢补查
        log(f"[词根扫描] 第一轮漏 {len(failed)} 个，放慢补查：{failed}")
        GAP[0] = max(GAP[0], 25.0); left = []
        for r in failed:
            (ok if one(r, 3) else left).append(r)
        failed = left
    MISSED_ROOTS[:] = failed
    log(f"[词根扫描] {len(ROOTS)} 个词根成功 {len(ok)} 个，查漏 {failed}，rising 词 {len(out)} 条")
    return out

# ---------------- filter & dedupe ----------------
def rough_ok(t):
    w = norm(t)
    if not w or len(' '.join(w)) < 3 or len(w) > 4: return False
    if re.search(r'\b(lora|dgx|gguf)\b', ' '.join(w)): return False
    if BAD.search(' '.join(w)) or GENERIC.search(' '.join(w)): return False
    core = [x for x in w if x not in STOP and x not in TOOLWORDS]
    if not core: return False                        # 全是通用词
    if all(x in BRANDS for x in core): return False   # 纯品牌
    if any(x in BRANDS for x in core) and len(core) <= 1: return False
    return True

def dedupe(cands, seen):
    res = []
    for c in cands:
        k = key(c['term'])
        if not k or k in seen: continue
        hit = next((r for r in res if k in key(r['term']) or key(r['term']) in k), None)
        if hit:
            if c['src'] not in hit['src']: hit['src'] += ' / ' + c['src']
            if not hit.get('desc') and c.get('desc'): hit['desc'] = c['desc']
            if len(k) < len(key(hit['term'])): hit['term'] = c['term']  # 取更短的核心词
            continue
        res.append(dict(c))
    return res

CACHEP = os.path.join(D, 'cache.json')
CACHE = json.load(open(CACHEP)) if os.path.exists(CACHEP) else {}
def _fixb(o):
    if isinstance(o, dict): return {k: _fixb(v) for k, v in o.items()}
    return {'True': True, 'False': False}.get(o, o) if isinstance(o, str) else o
CACHE = _fixb(CACHE)
def cache_save(): json.dump(CACHE, open(CACHEP, 'w'), ensure_ascii=False, default=str)
CK = ('err','ratio','daily','peak_day','last24_ratio','spike','trend','active','first','old','spell','spell_note','ts')
def score(cands):
    day = TODAY.strftime('%Y-%m-%d')
    todo = []
    for c in cands:
        hit = CACHE.get(day, {}).get(key(c['term']))
        if hit and not hit.get('err') and hit.get('daily') and time.time() - float(hit.get('ts') or 0) < CACHE_TTL_H * 3600: c.update(hit)
        else: todo.append(c)
    log(f"[打分] 缓存命中 {len(cands)-len(todo)}，需查 {len(todo)}")
    _score(todo)
    for c in todo:
        if 'ratio' in c: CACHE.setdefault(day, {})[key(c['term'])] = {k: c[k] for k in CK if k in c}
    cache_save()
    return cands
def cache_put(c):
    day = TODAY.strftime('%Y-%m-%d'); CACHE.setdefault(day, {}).setdefault(key(c['term']), {}).update({k: c[k] for k in CK if k in c}); cache_save()
GPTS_MIN = float(os.environ.get('GPTS_MIN', 5))   # 同组 GPTs 均值低于此值 = 被大词压扁，小词另行分组重查
def _apply(b, df):
    """按 newterm 口径给一组候选打分，返回该组 GPTs 均值（剔除最后 24h）"""
    if 'isPartial' in df: df = df.drop(columns='isPartial')
    cutoff = df.index.max() - pd.Timedelta(hours=24)
    st = df[df.index <= cutoff]; g = st['GPTs'].mean()
    for c in b:
        s = df[c['term']]; ss = st[c['term']]
        c['ratio'] = round(ss.mean() / g, 2) if g > 0 else 0
        c.pop('err', None)
        if g == 0 and ss.mean() > 0: c['err'] = 'GPTs 被压成 0，无法算倍数（多为新闻爆点）'; c['ratio'] = 0
        daily = ss.resample('D').mean(); gd = st['GPTs'].resample('D').mean()
        c['daily'] = {d.strftime('%m/%d'): round(v / gv, 2) for d, v, gv in zip(daily.index, daily, gd) if gv > 0}
        c['peak_day'] = max(c['daily'], key=c['daily'].get) if c['daily'] and max(c['daily'].values()) > 0 else '-'
        c['last24_ratio'] = round(s[s.index > cutoff].mean() / g, 2) if g > 0 else 0
        last, peak = (daily.iloc[-1] if len(daily) else 0), daily.max()
        first = daily.iloc[:2].mean() if len(daily) >= 2 else 0
        nz = (ss > 0).mean()
        c['spike'] = bool(nz < 0.15)                       # 7天里绝大多数时间为 0，一天冒尖
        if peak == 0: c['trend'] = '无数据'
        elif last >= peak * 0.9 and last > first * 1.2: c['trend'] = '在涨'
        elif last >= peak * 0.7: c['trend'] = '到顶/高位'
        else: c['trend'] = '在回落'
        c['active'] = bool(ss.max() > 0)
        c['ts'] = time.time()
    means = {c['term']: float(st[c['term']].mean()) for c in b}
    top = max(means.values()) if means else 0
    small = [c for c in b if means[c['term']] < top * 0.3]          # 被组内大词压低的小词
    return g, small
def _score(cands):
    """每批 4 个候选 + GPTs，返回 GPTs 倍数（剔除最后 24h 后的均值）及走势。
    若某组 GPTs 被大词压扁（均值 < GPTS_MIN），把组内均值不到最大词 30% 的小词重新分组再查（最多 2 轮）。"""
    if past_deadline('SCORE_DEADLINE') or past_deadline():
        for c in cands: c['err'] = '截止时间到，未查'
        return cands
    todo = list(cands)
    for rnd in range(3):
        if not todo: break
        batches = [todo[i:i+4] for i in range(0, len(todo), 4)]
        dfs = fetch_many([[c['term'] for c in b] + ['GPTs'] for b in batches])
        todo = []
        for b, df in zip(batches, dfs):
            if df is None or df.empty:
                for c in b:
                    if 'ratio' not in c: c['err'] = 'trends 失败'
                continue
            g, small = _apply(b, df)
            if g < GPTS_MIN and rnd < 2:
                if small:
                    todo += small
                    log(f"  GPTs 被压扁(均值 {g:.1f})，重查：{[c['term'] for c in small]}")
        if todo: REGROUPED.extend(c['term'] for c in todo)
    for c in cands:
        if 'ratio' in c: cache_put(c)
    return cands
REGROUPED = []

def past_deadline(name='DEADLINE'):
    dl = os.environ.get(name)   # 例如 17:40，到点后不再发新的 Trends 请求，直接出报告
    if not dl: return False
    h, m = map(int, dl.split(':')); return dt.datetime.now() >= dt.datetime.now().replace(hour=h, minute=m, second=0)
def history(cands):
    """近 3 个月（日粒度）判断出现时间、是否老词"""
    if past_deadline(): return cands
    cands = sorted(cands, key=lambda c: -(c.get('ratio') or 0))   # 量级相近的放一组，避免大词把小词压成 0
    batches = [cands[i:i+5] for i in range(0, len(cands), 5)]
    dfs = fetch_many([[c['term'] for c in b] for b in batches], tf='today 3-m')
    for b, df in zip(batches, dfs):
        if df is None or df.empty: continue
        for c in b:
            s = df[c['term']]
            if s.max() == 0: continue
            first = s[s >= s.max() * 0.1].index.min()
            c['first'] = first.strftime('%Y-%m-%d')
            early, recent = s.iloc[:30].mean(), s.iloc[-10:].mean()
            c['old'] = bool(recent > 0 and early / recent > 0.3)
            cache_put(c)
    return cands

def spelling_many(cs):
    """并行预取写法对比（AIsa），再逐个调用 spelling()"""
    need = [c for c in cs if 'spell' not in c and len(norm(c['term'])) >= 2 and not past_deadline()]
    pairs = [[' '.join(norm(c['term'])), ''.join(norm(c['term']))] for c in need]
    dfs = fetch_many(pairs)
    for c, df in zip(need, dfs): c['_spell_df'] = df
    for c in cs:
        if 'spell' not in c: spelling(c)
        c.pop('_spell_df', None); cache_put(c)
def spelling(c):
    w = norm(c['term'])
    if past_deadline(): c['spell'] = c['term']; return
    if len(w) < 2: c['spell'] = c['term']; return
    a, b = ' '.join(w), ''.join(w)
    df = c['_spell_df'] if '_spell_df' in c else trends_call(lambda: pt().interest_over_time(), [a, b])
    if df is None or df.empty: c['spell'] = c['term']; return
    c['spell'] = a if df[a].mean() >= df[b].mean() else b
    c['spell_note'] = f"“{a}” vs “{b}” ≈ {df[a].mean():.0f}:{df[b].mean():.0f}（同图相对值）"

# ---------------- main ----------------
THRESH = float(os.environ.get('THRESH', 0.2))
def gefei_terms():
    fs = sorted((f for f in os.listdir(D) if f.startswith('gefei_') and (f.endswith('.md') or (f.endswith('.json') and f.startswith('gefei_20')))),
                key=lambda f: os.path.getmtime(os.path.join(D, f)))
    ks = set(); use = fs[-20:]                # 最近 20 份哥飞批次（API 的 json + 旧的 md）
    for f in use:
        fp = os.path.join(D, f)
        if f.endswith('.json'):
            j = json.load(open(fp))
            if not isinstance(j, dict) or 'batch' not in j: continue   # 只认 API 批次文件，跳过 pick/all_keys 等中间文件
            d = j.get('data') or {}
            for k in (d.get('keywords') or d.get('items') or []): ks.add(key(k.get('keyword', '')))
        else:
            for m in re.finditer(r'^## \d+\. (.+)$', open(fp).read(), re.M): ks.add(key(m.group(1)))
    ks.discard(''); return ks, use

def collect():
    cands, srcstat = [], {}
    for name, fn in [('toolify', src_toolify), ('trends_us', src_trending_us), ('github', src_github),
                     ('hf', src_hf), ('roots', src_roots)]:
        try:
            r = fn()
            if name == 'trends_us': r = r[0]
            cands += r; srcstat[name] = len(r)
        except Exception as e:
            srcstat[name] = f'失败: {str(e)[:120]}'; log(f"[{name}] 失败", e)
    return cands, srcstat

def main():
    pushp = os.path.join(D, 'pushed.json')
    pushed = json.load(open(pushp)) if os.path.exists(pushp) else {}
    today = TODAY.strftime('%Y-%m-%d')
    ep = os.path.join(D, 'enrich.json'); enrich = json.load(open(ep)) if os.path.exists(ep) else {}
    gk, gfiles = gefei_terms()
    resume = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--resume=')), None)
    if resume:                                  # 用已打分的候选重新出报告（不再请求 Trends 打分）
        st = json.load(open(os.path.join(D, resume)))
        cands, srcstat = [c for c in st['cands'] if rough_ok(c['term'])], st['srcstat']; MISSED_ROOTS[:] = st.get('missed_roots', [])
        for k2, v in st.get('stats', {}).items(): STATS[k2] = v
    else:
        cands, srcstat = collect()
        raw = len(cands)
        cands = [c for c in cands if rough_ok(c['term'])]
        cands = dedupe(cands, {})
        log(f"候选 {raw} 条，粗筛+去重后 {len(cands)} 条")
    for c in cands:                             # 走势统一按 GPTs 归一后的按天倍数判断
        d = list((c.get('daily') or {}).values())
        if d and max(d) > 0:
            pk, last, first = max(d), d[-1], sum(d[:2]) / 2
            c['trend'] = '在涨' if last >= pk * 0.9 and last > first * 1.2 else ('到顶/高位' if last >= pk * 0.7 else '在回落')
    def in_gefei(c):
        k = key(c['term']); return any(k == g or (len(k) >= 5 and (k in g or g in k)) for g in gk)
    gdup = [c['term'] for c in cands if in_gefei(c)]
    cands = [c for c in cands if not in_gefei(c)]
    if not resume: score(cands)
    good = [c for c in cands if c.get('ratio', 0) >= THRESH and not c.get('spike')]
    history([c for c in good if 'old' not in c and 'first' not in c])
    keep = [c for c in good if not c.get('old')]
    spelling_many(keep)
    dup_today = [c['term'] for c in keep if today in pushed.get(key(c['term']), [])]
    sel = sorted([c for c in keep if today not in pushed.get(key(c['term']), [])], key=lambda c: -c['ratio'])
    json.dump(dict(cands=cands, srcstat=srcstat, missed_roots=MISSED_ROOTS, stats=STATS),
              open(os.path.join(D, f'state_{STAMP}.json'), 'w'), ensure_ascii=False, indent=1, default=str)

    def fmt(c):
        e = enrich.get(key(c['term']), {})
        days = '，'.join(f"{d} ×{v:g}" for d, v in c.get('daily', {}).items())
        L = [f"### {c['term']}", f"- 新词：{c['term']}",
             f"- 热度(GPTs)：GPTs × {c['ratio']:g}（近 7 天均值，已剔除最后 24h；最后 24h 未结算，仅参考 ×{c.get('last24_ratio',0):g}）",
             f"- 走势：{c['trend']}，峰值 {c['peak_day']}（按天：{days}）",
             f"- 出现时间：{e.get('first') or c.get('first') or '近 3 个月无明显数据'} 前后开始有搜索（Trends 近 3 个月口径）",
             f"- 主流写法：{c.get('spell', c['term'])}" + (f"（{c['spell_note']}）" if c.get('spell_note') else ''),
             f"- 来源：{e.get('origin','')}（数据源：{c['src']}" + (f"，{c['extra']}" if c.get('extra') else '') + "）",
             f"- 是做什么的：{e.get('what') or c.get('desc') or '待补'}"]
        comp = e.get('competitors') or ([c['url']] if c.get('url') and c['src'].startswith('toolify') else [])
        if comp: L.append("- 竞品网站：" + '，'.join(f"[{u.split('//')[-1].rstrip('/')}]({u})" for u in comp))
        return '\n'.join(L) + '\n'

    md = [f"# 新词日报 {TODAY:%Y-%m-%d}", "",
          f"口径：Google Trends 全球、now 7-d，与 GPTs 同图比较；门槛 GPTs × {THRESH:g}；已与哥飞词库（{', '.join(gfiles) or '无'}）去重。", "",
          "## 数据源", *[f"- {k}: {v}" for k, v in srcstat.items()],
          f"- 词根查漏：{('、'.join(MISSED_ROOTS)) or '无'}",
          f"- Trends 请求 {STATS['req']} 次，最终失败 {STATS['fail']} 次，429 限流 {STATS['r429']} 次",
          f"- Trends 通道：AIsa {AT.STATS['calls']} 次调用（${AT.STATS['cost']:.3f}）" + (f"，GPTs 被压扁后重分组 {len(REGROUPED)} 个词" if REGROUPED else "") + (f"，回退 pytrends {len(FALLBACKS)} 组：{'；'.join(FALLBACKS)[:300]}" if FALLBACKS else "，无回退") if USE_AISA else "- Trends 通道：pytrends", "",
          f"## 达标新词（{len(sel)}）", *([fmt(c) for c in sel] or ['（今天没有达标的新词）']), "",
          "## 剔除记录",
          "- 与哥飞词库重复：" + ('、'.join(gdup) or '无'),
          "- 今日已推送过：" + ('、'.join(dup_today) or '无'),
          "- 达标但属老词（3 个月前已有相当热度）：" + ('、'.join(f"{c['term']}(×{c['ratio']:g})" for c in good if c.get('old')) or '无'),
          "- 一天冒尖就归零：" + ('、'.join(c['term'] for c in cands if c.get('spike')) or '无'),
          f"- 打分失败（Trends 未拿到）：" + ('、'.join(c['term'] for c in cands if c.get('err')) or '无'),
          f"- 低于 ×{THRESH:g}：" + ('、'.join(f"{c['term']}(×{c.get('ratio',0):g})" for c in cands if 'ratio' in c and c['ratio'] < THRESH and not c.get('spike')) or '无'), ""]
    out = os.path.join(D, f'report_{STAMP}.md'); open(out, 'w').write('\n'.join(md))
    if '--dry' not in sys.argv:
        for c in sel: pushed.setdefault(key(c['term']), [])
        for c in sel:
            if today not in pushed[key(c['term'])]: pushed[key(c['term'])].append(today)
        json.dump(pushed, open(pushp, 'w'), ensure_ascii=False, indent=1)
    log(f"完成：达标 {len(sel)} -> {out}；AIsa 调用 {AT.STATS['calls']} 次 ${AT.STATS['cost']:.3f}，回退 {len(FALLBACKS)} 组 {FALLBACKS}")

if __name__ == '__main__':
    main()
