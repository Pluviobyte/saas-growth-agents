#!/usr/bin/env python3
"""模板站 sitemap 雷达（只采集，不进播报）。
用法: python3 radar_sitemaps.py --out <目录> [--no-score] [--max-usd 0.10] [--max-terms 24]
每次拉 watchlist.json 里各站的 sitemap，跟 radar/sitemap_<站>.json 上次快照比，新网址里抽梗名
（归一化，合并多语言 / 模板页+教程页），对照 pushed.json、tiktok_pool.json 标出「我们没记过」，记 first_seen。
首次运行只建基线：所有网址记为已见，仅把 lastmod 在近 2 天内的页当「基线期近期页」列出。
没记过的梗可选用 AIsa DataForSEO Trends 跟 GPTs 比（7 天均值剔除最后 24h、近 24h），有花费上限。
结果: <out>/radar_sitemaps.json；累计库 radar/sitemap_candidates.json。"""
import os, sys, re, json, time, argparse, traceback, datetime as dt
import requests
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
from radar_common import *

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
# 监控名单不放在仓库里：每个人的赛道不同，名单写在工作目录的 watchlist.json 的 "sitemaps" 下（格式见 watchlist.example.json）。
# 每项：type = meme / ai / event；roots = sitemap 地址；big = 大站（只拉近期变动的子 sitemap，只比新网址）；
#       keep = 只留匹配的网址；child = 只拉匹配的子 sitemap；path = 从路径里取名字的正则（第 1 组是 slug），
#       不写就取「单段路径」或「templates/xxx 这类两段路径」的最后一段；exclude = 不当名字的 slug；
#       name = meme / ai / event / codes（slug 怎么变成名字，默认跟 type 走）；page = 页面类型标签
WATCHLIST = os.environ.get('NEWTERM_WATCHLIST') or os.path.join(D, 'watchlist.json')
SITES = {k: v for k, v in (load_json(WATCHLIST, {}).get('sitemaps') or {}).items() if not k.startswith('_')}

TYPE_ORDER = {'meme': 0, 'ai': 1, 'event': 2}
CANDF = os.path.join(RD, 'sitemap_candidates.json')
BASELINE_DAYS = 2
SUFFIX = r'(?:-v\d+)?(?:-ai)?(?:-(?:trend|video|filter|effect|runway|generator|template))*(?:-ai)?(?:-v\d+)?$'

def get(u, timeout=60):
    r = requests.get(u, headers={'User-Agent': UA}, timeout=timeout); r.raise_for_status(); return r.text

def fetch_sitemap(cfg, since=None):
    """拉一个站的全部（或近期变动的）子 sitemap。since=YYYY-MM-DD 时，大站只拉索引 lastmod >= since 的子 sitemap。
    返回 (urls{网址: lastmod}, 拉取的文件数, 跳过的子 sitemap 数)"""
    urls, queue, seen, skipped = {}, list(cfg['roots']), set(), 0
    max_files = int(cfg.get('max_files', 60))
    while queue and len(seen) < max_files:
        u = queue.pop(0)
        if u in seen: continue
        seen.add(u)
        try: t = get(u)
        except Exception:
            if u in cfg['roots'] and len(cfg['roots']) == 1: raise
            continue
        if '<sitemapindex' in t:
            for b in re.findall(r'<sitemap>(.*?)</sitemap>', t, re.S):
                l = re.search(r'<loc>\s*(.*?)\s*</loc>', b); m = re.search(r'<lastmod>\s*(.*?)\s*</lastmod>', b)
                if not l: continue
                loc = l.group(1).strip()
                if cfg.get('child') and not re.search(cfg['child'], loc): continue
                if since and m and m.group(1)[:10] < since: skipped += 1; continue
                queue.append(loc)
            continue
        for b in re.findall(r'<url>(.*?)</url>', t, re.S):
            l = re.search(r'<loc>\s*(.*?)\s*</loc>', b); m = re.search(r'<lastmod>\s*(.*?)\s*</lastmod>', b)
            if not l: continue
            loc = l.group(1).strip().rstrip('/')
            if cfg.get('keep') and not re.search(cfg['keep'], loc + '/'): continue
            urls[loc] = (m.group(1)[:10] if m else '')
    if not urls: raise RuntimeError('sitemap 为空或读不出')
    return urls, len(seen), skipped

def clean(slug):
    s = re.sub(SUFFIX, '', slug.lower())
    return s.replace('-', ' ').strip()

# 路径里这些段只是栏目，名字在下一段
HUBS = {'templates', 'template', 'trends', 'trend', 'video', 'videos', 'effects', 'ai-effects', 'video-effects',
        'tools', 'tool', 'guides', 'meme', 'memes', 'dance', 'filters', 'filter'}
# 常见的非内容页，不当名字
RESERVED = {'', 'about', 'pricing', 'privacy', 'privacy-policy', 'terms', 'terms-of-service', 'refund-policy',
            'contact', 'login', 'signup', 'sign-up', 'blog', 'docs', 'api', 'help', 'faq', 'changelog', 'page',
            'categories', 'category', 'search', 'account', 'dashboard', 'affiliate', 'cookie', 'cookies'} | HUBS

def parse(site, url):
    """网址 -> (名字, 类型, 页面类型) 或 None；规则来自 watchlist.json 里这个站的配置"""
    cfg = SITES.get(site, {})
    p = re.sub(r'^https?://[^/]+', '', url).strip('/')
    p = re.sub(r'^(?:es|ko|ja|zh(?:-tw)?|de|fr|pt|it|ar|ru|nl|pl|tr|id)/', '', p, flags=re.I)  # 多语言合并
    if cfg.get('path'):
        m = re.search(cfg['path'], p)
        if not m: return None
        slug = m.group(1)
    else:
        seg = p.split('/')
        if not (len(seg) == 1 or (len(seg) == 2 and seg[0] in HUBS)): return None
        slug = seg[-1]
    if not slug or slug in RESERVED or slug in set(cfg.get('exclude') or ()) or slug.isdigit(): return None
    if slug.startswith(('how-to-', 'what-is-')) and not cfg.get('path'): return None
    namer = cfg.get('name') or cfg.get('type', 'meme')
    name = {'ai': ai_name, 'event': event_name, 'codes': codes_name}.get(namer, clean)(slug)
    return name, cfg.get('type', 'meme'), cfg.get('page', 'page')

def ai_name(slug):
    s = re.sub(r'(?<=\d)-(?=\d)', '.', slug.lower())
    s = re.sub(r'-(?:api|ai-api|pricing|review|guide|online|free)$', '', s)
    return s.replace('-', ' ').strip()

MONTHS = set('january february march april may june july august september october november december'.split())
CUT = set("""launches launch launched is are was were gets get adds add announced announces revealed reveals coming comes
returns return release releases released date dates now out arrives arriving cancelled canceled confirmed delayed
leaks leaked shuts update updates patch notes guide review preview vs explained in on at with for as""".split())
def event_name(slug):
    """新闻标题 slug -> 短名字（取第一个动词/介词之前的部分，去掉月份年份）；返回 (短名, 原标题)"""
    w = [x for x in slug.lower().split('-') if x]
    head = ' '.join(w)
    out = []
    for x in w:
        if x in CUT and len(out) >= 1: break
        if x in MONTHS or re.match(r'^20\d\d$', x): continue
        out.append(x)
    while out and out[0] in ('the', 'a', 'an', 'new', 'how', 'when', 'what', 'why', 'where', 'best', 'all', 'every'): out.pop(0)
    return (' '.join(out) or head, head)

def codes_name(slug):
    """兑换码页 slug -> (短名, 原标题)；去掉 working/updated 等前缀后走 event_name。"""
    s = slug.lower().strip('-')
    s = re.sub(r'^(?:all-|working-|updated-|new-|latest-)+', '', s)
    return event_name(s)

def toks(n): return {w for w in norm(n) if w not in FILLER}
def find_existing(db, name, stype='meme'):
    """同一个梗的不同写法合并：核心词相同、词集合相同，或一方词集是另一方子集（短的一方≥2 个词或≥6 字母）。"""
    ck = core_key(name)
    if ck in db: return ck
    if stype != 'meme': return ck          # AI / 游戏活动类只按核心词精确合并，防止「pokemon go」把一堆新闻并成一条
    t = toks(name)
    for k, c in db.items():
        if c.get('types', ['meme']) != ['meme']: continue
        u = toks(c['name'])
        if not t or not u: continue
        small = t if len(t) <= len(u) else u
        if t == u or ((t <= u or u <= t) and (len(small) >= 2 or len(''.join(small)) >= 6)): return k
    return ck

def score(cands, max_usd, max_terms, log):
    """梗：名字带 / 不带 " ai" 两种都查，取高的；AI、游戏活动：只查原名。每组 4 个词 + GPTs；超过花费上限就停。"""
    import aisa_trends as AT
    jobs = []                                    # (cand, [terms])
    n = 0
    for c in sorted(cands, key=lambda c: TYPE_ORDER.get(c['types'][0], 9)):
        nm = c['name']
        if c['types'][0] == 'meme' and 'ai' not in nm.split(): ts = [nm, nm + ' ai']
        else: ts = [nm]
        if n + len(ts) > max_terms: log.append(f'打分词数到上限 {max_terms}，后面的没打'); break
        jobs.append((c, ts)); n += len(ts)
    groups, cur = [], []
    for j in jobs:
        if sum(len(x[1]) for x in cur) + len(j[1]) > 4: groups.append(cur); cur = []
        cur.append(j)
    if cur: groups.append(cur)
    c0 = AT.STATS['cost']
    for g in groups:
        spent = AT.STATS['cost'] - c0
        if spent + 0.012 > max_usd: log.append(f'打分到花费上限 ${max_usd} 停止'); break
        terms = [t for _, ts in g for t in ts]
        try:
            df = AT.interest_over_time(terms + ['GPTs'], 'past_7_days')
            sc = AT.score_vs_gpts(df, terms) if len(df) else {}
            for c, ts in g:
                tried = []
                for t in ts:
                    x = sc.get(t, {})
                    tried.append(dict(term=t, ratio_7d=x.get('ratio', 0), last24_ratio=x.get('last24_ratio', 0),
                                      trend=x.get('trend', '无数据'), peak_day=x.get('peak_day', '-')))
                best = max(tried, key=lambda d: (max(d['ratio_7d'], d['last24_ratio']), d['ratio_7d']))
                c['score'] = dict(best, at=nows(), tried=tried)
        except Exception as e:
            log.append(f'打分失败 {terms}: {str(e)[:100]}')
    return round(AT.STATS['cost'] - c0, 4)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--no-score', action='store_true')
    ap.add_argument('--max-usd', type=float, default=float(os.environ.get('RADAR_SCORE_MAX_USD', 0.10)))
    ap.add_argument('--max-terms', type=int, default=24)
    ap.add_argument('--sites', default='', help='只跑这些站（逗号分隔），默认全部')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    log, sites_out = [], {}
    if not SITES: log.append(f'没有监控名单：在 {WATCHLIST} 的 "sitemaps" 下填竞品站（格式见 watchlist.example.json），这次跳过')
    db = load_json(CANDF, {}); idx = known_index(); stamp = nows()
    touched = {}
    only = [x for x in a.sites.split(',') if x]
    for site, cfg in SITES.items():
        if only and site not in only: continue
        so = dict(ok=False, type=cfg['type'], big=bool(cfg.get('big')))
        t0 = time.time()
        try:
            snapf = os.path.join(RD, f'sitemap_{site}.json')
            prev = load_json(snapf, None)
            baseline = prev is None
            since = None
            if cfg.get('big') and not baseline:
                since = (dt.datetime.strptime(prev['at'][:10], '%Y-%m-%d') - dt.timedelta(days=2)).strftime('%Y-%m-%d')
            cur, nfiles, skipped = fetch_sitemap(cfg, since)
            # 只比「新网址」，lastmod 变化一律不算；首次运行只建基线，不出候选
            new = [] if baseline else [u for u in cur if u not in prev['urls']]
            allurls = dict(prev['urls']) if (prev and cfg.get('big')) else {}
            allurls.update(cur)                      # 大站只拉了近期子 sitemap，快照取并集
            so.update(ok=True, baseline=baseline, total_urls=len(allurls), fetched_urls=len(cur), files=nfiles,
                      skipped_child_sitemaps=skipped, new_urls=len(new), prev_at=(prev or {}).get('at'),
                      secs=round(time.time() - t0, 1), new_url_list=new[:200])
            for u in new:
                r = parse(site, u)
                if not r: continue
                for name, kind, ptype in (r if isinstance(r, list) else [r]):
                    headline = ''
                    if isinstance(name, tuple): name, headline = name
                    if not name or len(name) < 3: continue
                    stype = cfg['type']
                    ck = find_existing(db, name, stype)
                    c = db.get(ck)
                    if not c:
                        kn = match_known(name, idx)
                        c = db[ck] = dict(name=name, kind=kind, types=[stype], first_seen=stamp, sites={},
                                          known=(dict(src=kn[0], as_=kn[1], date=kn[2]) if kn else None),
                                          new_to_us=not kn, found_in_baseline=False)
                    c.setdefault('types', ['meme'])
                    if stype not in c['types']: c['types'].append(stype)
                    if headline: c['headline'] = headline
                    s_ = c['sites'].setdefault(site, dict(first_seen=stamp, urls=[], lastmod='', published=''))
                    if u not in s_['urls']: s_['urls'].append(u)
                    if ptype not in s_.setdefault('page_types', []): s_['page_types'].append(ptype)
                    s_['lastmod'] = max(s_['lastmod'], cur.get(u) or '')
                    touched[ck] = c
            save_json(snapf, dict(at=stamp, type=cfg['type'], urls=allurls))
        except Exception as e:
            so['error'] = f'{type(e).__name__}: {str(e)[:150]}'; log.append(f'{site} 失败: {so["error"]}')
        sites_out[site] = so
    run_new = [c for c in touched.values() if c['first_seen'] == stamp]
    # 打分：没记过的；游戏活动类只打短名（≤5 个词），长标题不打
    to_score = [c for c in run_new if c['new_to_us'] and 'score' not in c and len(c['name'].split()) <= 5]
    cost = 0.0
    if to_score and not a.no_score:
        try: cost = score(to_score, a.max_usd, a.max_terms, log)
        except Exception as e: log.append(f'打分整体失败: {str(e)[:150]}')
    save_json(CANDF, db)
    def brief(c):
        return dict(name=c['name'], types=c.get('types', ['meme']), kind=c['kind'], headline=c.get('headline', ''),
                    new_to_us=c['new_to_us'], known=c['known'], first_seen=c['first_seen'],
                    sites={k: dict(lastmod=v['lastmod'], published=v.get('published', ''), urls=v['urls'][:3]) for k, v in c['sites'].items()},
                    score=c.get('score'))
    out = dict(at=stamp, sites=sites_out, cost_usd=cost, log=log,
               new_candidates=[brief(c) for c in sorted(run_new, key=lambda c: (not c['new_to_us'], TYPE_ORDER.get(c.get('types', ['meme'])[0], 9), c['name']))],
               new_to_us=sum(1 for c in run_new if c['new_to_us']))
    save_json(os.path.join(a.out, 'radar_sitemaps.json'), out)
    ok = sum(1 for s_ in sites_out.values() if s_['ok'])
    print(f"sitemaps: {ok}/{len(sites_out)} ok, 新候选 {len(run_new)}（我们没记过 {out['new_to_us']}），打分花费 ${cost}")
    for site, s_ in sites_out.items():
        print(f"  {site}[{s_['type']}]: " + (f"{'基线' if s_.get('baseline') else '比对'} 共 {s_['total_urls']} 网址, 本次拉 {s_['fetched_urls']}, 新 {s_['new_urls']}, {s_['secs']}s" if s_['ok'] else s_.get('error', '')))
    for l in log: print(' ', l)

if __name__ == '__main__':
    main()
