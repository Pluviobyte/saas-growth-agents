#!/usr/bin/env python3
"""付费/混合 AI 导航站「新上架工具名」雷达（只发现，不投付费）。
用法:
  python3 radar_paid_nav.py --out <目录> [--max-sec 480] [--domain X]

抓各站 /new|/latest|/today|RSS|工具 sitemap 里的新工具展示名（不是域名本身）。
对照 pushed.json / tiktok_pool.json / radar/paid_nav_seen.json 去重。
结果: <out>/radar_paid_nav.json（含 oldword_newsites）；累计库 radar/paid_nav_seen.json。
同轮后处理：老词新站筛（radar_oldword_newsites），无额外 Trends 成本。
"""
import os, sys, re, time, html, argparse, collections
from urllib.parse import urljoin, urlparse
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
from radar_common import *

try:
    from curl_cffi import requests as creq
    def _get(url, headers=None, timeout=35):
        r = creq.get(url, impersonate='chrome131', headers=headers or {},
                     timeout=timeout, allow_redirects=True)
        return r.status_code, r.text or '', dict(r.headers)
except Exception:
    import requests as req
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36'
    def _get(url, headers=None, timeout=35):
        h = {'User-Agent': UA}; h.update(headers or {})
        r = req.get(url, headers=h, timeout=timeout, allow_redirects=True)
        return r.status_code, r.text or '', dict(r.headers)

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

SEENF = os.path.join(RD, 'paid_nav_seen.json')

# 导航站自身品牌名 / 提交页噪，不当工具名
BRAND_JUNK = {
    'toolify', 'toolify.ai', 'gptdemo', 'gpt demo', 'aixploria', 'bestaito', 'best ai to',
    'best free ai websites', 'creati', 'creati.ai', 'theresanaiforthat', "there's an ai for that",
    'taaft', 'fazier', 'dang.ai', 'dang ai', 'topai', 'topai.tools', 'saashub', 'alternativeto',
    'betalist', 'uneed', 'uneed.best', 'startupfa', 'twelve.tools', 'twelve tools',
    'submit', 'pricing', 'advertise', 'login', 'register', 'categories', 'blog', 'about',
    'sponsored by', 'all tools', 'new tools', 'latest', 'home', 'explore',
}
JUNK_NAME_RE = re.compile(
    r'^(submit|pricing|advertise|login|sign\s*up|register|blog|about|categories?|home|'
    r'explore|browse|search|contact|privacy|terms|cookie|sponsored|featured|all\s*tools|'
    r'new\s*tools|latest|free\s*tools|top\s*\d+)\b', re.I)

def slug_to_name(slug):
    s = (slug or '').strip('-_')
    if not s: return ''
    # keep version-ish digits; hyphens → spaces
    parts = re.split(r'[-_]+', s)
    out = []
    for p in parts:
        if not p: continue
        if p.isupper() or re.match(r'^\d', p) or len(p) <= 2:
            out.append(p)
        else:
            out.append(p[:1].upper() + p[1:])
    return ' '.join(out)

def abs_url(base, href):
    if not href: return ''
    return urljoin(base, href.split('#')[0])

def clean_name(name):
    name = html.unescape(re.sub(r'\s+', ' ', (name or '')).strip())
    name = re.sub(r'\s*[|–—-]\s*(AI Tools?|Review|Alternatives?).*$', '', name, flags=re.I).strip()
    return name

def is_junk_name(name):
    n = (name or '').strip()
    if not n or len(n) < 2: return True
    if len(n) > 80: return True
    if key(n) in {key(x) for x in BRAND_JUNK}: return True
    if JUNK_NAME_RE.match(n): return True
    if n.lower() in ('ai', 'tool', 'tools', 'new', 'latest'): return True
    return False

# ---- per-domain parsers -------------------------------------------------

def parse_toolify_new(text, page_url):
    """toolify.ai/new：.tool-dom 卡片，工具展示名 + /tool/slug"""
    out = []
    if not BeautifulSoup: return out
    soup = BeautifulSoup(text, 'html.parser')
    for c in soup.select('.tool-dom'):
        texts = [t for t in c.stripped_strings]
        if not texts: continue
        name = texts[0]
        if name.lower().startswith('sponsored'): continue
        href = None
        for a in c.find_all('a', href=True):
            h = a['href']
            if re.search(r'/tool/[a-z0-9-]+/?$', h.split('?')[0], re.I):
                href = abs_url(page_url, h); break
        if not href:
            # external-only cards still have a name
            for a in c.find_all('a', href=True):
                if a['href'].startswith('http') and 'toolify' not in a['href']:
                    href = a['href']; break
        if not href: continue
        out.append(dict(name=clean_name(name), url=href, source_page=page_url))
    return out

def parse_anchor_keep(text, page_url, keep_re, name_from='text'):
    """通用：匹配 keep_re 的 a[href]，取锚文本或 slug 当名。"""
    out = []; seen = set()
    if not BeautifulSoup: return out
    soup = BeautifulSoup(text, 'html.parser')
    kre = re.compile(keep_re, re.I)
    for a in soup.find_all('a', href=True):
        href = abs_url(page_url, a['href'])
        path = urlparse(href).path
        if not kre.search(path): continue
        # drop pagination / filters
        if re.search(r'/page/\d+', path) or '?' in a['href']:
            # allow query on listing hosts but skip filter-only
            if re.search(r'[?&](pricing|sort|page)=', a['href']): continue
        m = kre.search(path)
        slug = ''
        if m and m.lastindex:
            slug = m.group(1)
        name = clean_name(a.get_text(' ', strip=True))
        if name_from == 'slug' or is_junk_name(name) or len(name) > 70:
            name = slug_to_name(slug) or name
        if is_junk_name(name): continue
        # canonical tool url without query
        canon = href.split('?')[0]
        ck = key(name) + '|' + canon.rstrip('/').lower()
        if ck in seen: continue
        seen.add(ck)
        out.append(dict(name=name, url=canon, source_page=page_url, slug=slug))
    return out

def parse_rss_items(text, page_url, link_keep=None):
    out = []
    for e in re.findall(r'<item>(.*?)</item>', text, re.S | re.I):
        g = lambda p: (re.search(p, e, re.S | re.I) or [None, ''])[1]
        title = clean_name(re.sub(r'<[^>]+>', '', html.unescape(g(r'<title[^>]*>(.*?)</title>'))))
        link = html.unescape(g(r'<link[^>]*>(.*?)</link>') or g(r'<link[^>]*href="(.*?)"'))
        link = link.strip()
        if link_keep and not re.search(link_keep, link, re.I): continue
        if is_junk_name(title): continue
        out.append(dict(name=title, url=link or page_url, source_page=page_url))
    for e in re.findall(r'<entry>(.*?)</entry>', text, re.S | re.I):
        g = lambda p: (re.search(p, e, re.S | re.I) or [None, ''])[1]
        title = clean_name(re.sub(r'<[^>]+>', '', html.unescape(g(r'<title[^>]*>(.*?)</title>'))))
        link = g(r'<link[^>]*href="(.*?)"') or g(r'<link[^>]*>(.*?)</link>')
        link = html.unescape(link.strip())
        if link_keep and not re.search(link_keep, link, re.I): continue
        if is_junk_name(title): continue
        out.append(dict(name=title, url=link or page_url, source_page=page_url))
    return out

def parse_taaft_new(text, page_url):
    """theresanaiforthat.com/new：a.ai_link → span 名 + /ai/slug"""
    out = []; seen = set()
    # primary: ai_link anchors
    for m in re.finditer(
        r'<a[^>]*class="[^"]*ai_link[^"]*"[^>]*href="(https?://theresanaiforthat\.com/ai/([a-z0-9-]+)/[^"]*)"[^>]*>(.*?)</a>',
        text, re.S | re.I):
        url, slug, inner = m.group(1), m.group(2), m.group(3)
        if slug in ('new', 'launch', 'category', 'categories'): continue
        name = clean_name(re.sub(r'<[^>]+>', ' ', inner))
        # drop version suffix noise like "v1"
        name = re.sub(r'\s+v\d+\s*$', '', name, flags=re.I).strip()
        if is_junk_name(name):
            name = slug_to_name(slug)
        if is_junk_name(name): continue
        canon = f'https://theresanaiforthat.com/ai/{slug}/'
        if slug in seen: continue
        seen.add(slug)
        out.append(dict(name=name, url=canon, source_page=page_url, slug=slug))
    if out: return out
    # fallback: unique /ai/slug from hrefs
    for m in re.finditer(r'theresanaiforthat\.com/ai/([a-z0-9-]+)/', text):
        slug = m.group(1)
        if slug in seen or slug in ('new', 'launch', 'category', 'categories'): continue
        seen.add(slug)
        out.append(dict(name=slug_to_name(slug), url=f'https://theresanaiforthat.com/ai/{slug}/',
                        source_page=page_url, slug=slug))
    return out

def parse_saashub_new(text, page_url):
    """saashub.com/new：What makes X unique? → /slug"""
    out = []; seen = set()
    skip = {'new', 'submit', 'pricing', 'startups', 'featured-products', 'latest', 'login',
            'register', 'categories', 'about', 'experts', 'blog', 'compare', 'newsletter',
            'community', 'eu', 'product-graveyard', 'status-pages', 'funding'}
    # 名称可能夹着标签：What makes <span>X</span> unique?
    for m in re.finditer(
        r'href="(/[a-z0-9-]+)"[^>]*>\s*What makes\s+([\s\S]*?)\s+unique\?', text, re.I):
        path = m.group(1)
        name = clean_name(re.sub(r'<[^>]+>', '', m.group(2)))
        slug = path.strip('/')
        if slug in skip: continue
        if is_junk_name(name):
            name = slug_to_name(slug)
        if is_junk_name(name): continue
        if path in seen: continue
        seen.add(path)
        out.append(dict(name=name, url=abs_url(page_url, path), source_page=page_url, slug=slug))
    return out

def parse_sitemap_tools(text, page_url, keep_re, max_items=400, recent_days=14):
    """工具 sitemap：用 keep_re 抽 slug；若有 lastmod 则优先近期。"""
    out = []
    pairs = re.findall(r'<loc>\s*(.*?)\s*</loc>(?:\s*<lastmod>\s*(.*?)\s*</lastmod>)?', text, re.S | re.I)
    kre = re.compile(keep_re, re.I)
    cutoff = None
    try:
        cutoff = (now() - __import__('datetime').timedelta(days=recent_days)).strftime('%Y-%m-%d')
    except Exception:
        cutoff = None
    recent, all_ok = [], []
    for loc, lm in pairs:
        loc = html.unescape(loc.strip())
        path = urlparse(loc).path
        m = kre.search(path)
        if not m: continue
        slug = m.group(1) if m.lastindex else ''
        if not slug or slug in ('page', 'new', 'all'): continue
        name = slug_to_name(slug)
        if is_junk_name(name): continue
        item = dict(name=name, url=loc.split('?')[0], source_page=page_url, slug=slug, lastmod=(lm or '').strip()[:10])
        all_ok.append(item)
        if cutoff and item['lastmod'] and item['lastmod'] >= cutoff:
            recent.append(item)
    chosen = recent if recent else all_ok[:max_items]
    # if using all (no lastmod filter hit), still cap
    return chosen[:max_items]

# ---- site config --------------------------------------------------------

# 监控名单不放在仓库里：写在工作目录 watchlist.json 的 "paid_nav" 下（格式见 watchlist.example.json）。
# 每项：enabled、label、listing_pages / feeds / sitemaps（三种入口任选）、keep / sitemap_keep（第 1 组是工具 slug）、
#       sitemap_recent_days、exclude_slugs、parser = anchor_keep / rss / sitemap / toolify_new / taaft_new / saashub_new
WATCHLIST = os.environ.get('NEWTERM_WATCHLIST') or os.path.join(D, 'watchlist.json')
SITES = {k: v for k, v in (load_json(WATCHLIST, {}).get('paid_nav') or {}).items() if not k.startswith('_')}
for _c in SITES.values():
    if 'exclude_slugs' in _c: _c['exclude_slugs'] = set(_c['exclude_slugs'])

def fetch_candidates(domain, cfg, log, deadline):
    items = []
    stats = dict(ok=False, urls_fetched=0, errors=[], parser=cfg.get('parser'))
    pages = list(cfg.get('listing_pages') or []) + list(cfg.get('feeds') or []) + list(cfg.get('sitemaps') or [])
    for url in pages:
        if time.time() > deadline:
            stats['errors'].append('deadline'); break
        try:
            code, text, _ = _get(url, timeout=40)
            stats['urls_fetched'] += 1
        except Exception as e:
            stats['errors'].append(f'{url}: {type(e).__name__}: {e}')
            log.append(f'{domain}: 网络错误 {url} {type(e).__name__}')
            continue
        if code != 200 or not text or len(text) < 200:
            stats['errors'].append(f'{url}: http {code} n={len(text) if text else 0}')
            log.append(f'{domain}: http {code} {url}')
            continue
        # soft CF challenge
        if 'Just a moment...' in text[:800] and len(text) < 20000:
            stats['errors'].append(f'{url}: cloudflare challenge')
            log.append(f'{domain}: CF challenge {url}')
            continue
        parser = cfg.get('parser')
        batch = []
        if url in (cfg.get('feeds') or []) or parser == 'rss' and url in pages and 'feed' in url:
            batch = parse_rss_items(text, url)
        elif url in (cfg.get('sitemaps') or []) or parser == 'sitemap' and url.endswith('.xml'):
            batch = parse_sitemap_tools(
                text, url,
                keep_re=cfg.get('sitemap_keep') or cfg.get('keep') or r'/([a-z0-9-]+)/?$',
                recent_days=int(cfg.get('sitemap_recent_days') or 14),
            )
        elif parser == 'toolify_new':
            batch = parse_toolify_new(text, url)
        elif parser == 'taaft_new':
            batch = parse_taaft_new(text, url)
        elif parser == 'saashub_new':
            batch = parse_saashub_new(text, url)
        elif parser == 'anchor_keep':
            batch = parse_anchor_keep(text, url, cfg['keep'])
            excl = set(cfg.get('exclude_slugs') or [])
            if excl:
                batch = [x for x in batch if (x.get('slug') or '') not in excl]
        else:
            log.append(f'{domain}: 未知 parser {parser} @ {url}')
        for x in batch:
            x['domain'] = domain
        items.extend(batch)
        log.append(f'{domain}: {url} → {len(batch)} 条')
        time.sleep(0.25)
    # 同 URL 合并：优先更像展示名的锚文本，避免空 a 先写成 slug 名
    by_url = collections.OrderedDict()
    for it in items:
        name = clean_name(it.get('name'))
        if is_junk_name(name): continue
        it['name'] = name
        uk = (it.get('url') or '').rstrip('/').lower() or ('name:' + key(name))
        old = by_url.get(uk)
        if old is None:
            by_url[uk] = it
            continue
        def _score(n):
            s = 0
            if ' ' in n: s += 2
            if any(c.isupper() for c in n[1:]): s += 1
            if n.lower() != n and n.upper() != n: s += 1
            s += min(len(n), 40) / 40.0
            return s
        if _score(name) > _score(old['name']):
            by_url[uk] = it
    items = list(by_url.values())
    stats['ok'] = stats['urls_fetched'] > 0 and len(stats['errors']) < stats['urls_fetched']
    if items:
        stats['ok'] = True
    stats['raw_count'] = len(items)
    return items, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-sec', type=int, default=int(os.environ.get('RADAR_PAID_NAV_MAX_SEC', 480)))
    ap.add_argument('--domain', default='', help='只跑一个域名（调试）')
    ap.add_argument('--emit-baseline', action='store_true',
                    help='首见也进 first_time_candidates（默认：域内首次跑只建基线）')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    deadline = time.time() + a.max_sec
    log = []; stamp = nows()

    sites = SITES
    if not SITES:
        log.append(f'没有监控名单：在 {WATCHLIST} 的 "paid_nav" 下填导航站（格式见 watchlist.example.json），这次跳过')
    if a.domain:
        d = a.domain.lower().strip()
        if d not in SITES:
            print(f'未知域名 {d}；已知: {", ".join(SITES)}')
            sys.exit(2)
        sites = {d: SITES[d]}

    seen = load_json(SEENF, {})
    idx = known_index()
    per_domain = {}
    all_items = []
    new_keys = []

    for domain, cfg in sites.items():
        if not cfg.get('enabled', True):
            per_domain[domain] = dict(ok=False, skipped=True, reason='disabled')
            continue
        if time.time() > deadline:
            per_domain[domain] = dict(ok=False, error='deadline')
            log.append(f'{domain}: 超时跳过')
            continue
        items, stats = fetch_candidates(domain, cfg, log, deadline)
        # 该域是否已有 seen 记录（无则本轮当基线）
        domain_had_seen = any(str(k).startswith(domain + '|') for k in seen)
        baseline = (not domain_had_seen) and (not a.emit_baseline)
        first_in_domain = []
        for it in items:
            name = it['name']
            ck = f"{domain}|{key(name)}"
            junk = is_junk_name(name)
            s = seen.get(ck)
            if s is None:
                kn = None if junk else match_known(name, idx)
                s = seen[ck] = dict(
                    name=name, url=it.get('url') or '', domain=domain,
                    first_seen=stamp, source_page=it.get('source_page') or '',
                    known=(dict(src=kn[0], as_=kn[1], date=kn[2]) if kn else None),
                    new_to_us=(not kn and not junk), junk=junk,
                    runs=0, sightings=0, baseline=baseline,
                )
                if not baseline and not junk:
                    new_keys.append(ck)
                    first_in_domain.append(ck)
                elif baseline and not junk:
                    # 基线写入 seen，不算 first_time 候选
                    pass
            s['runs'] += 1; s['sightings'] += 1; s['last_seen'] = stamp
            if it.get('url'): s['url'] = it['url']
            if it.get('source_page'): s['source_page'] = it['source_page']
            all_items.append(it)
        stats['baseline'] = baseline
        stats['first_new'] = len(first_in_domain)
        per_domain[domain] = stats
        print(f"paid_nav/{domain}: ok={stats.get('ok')} fetched={stats.get('urls_fetched')} "
              f"raw={stats.get('raw_count', 0)} baseline={baseline} first_new={stats.get('first_new')} "
              f"err={stats.get('errors')[:2] if stats.get('errors') else []}")

    save_json(SEENF, seen)

    def brief(ck):
        s = seen[ck]
        return dict(
            name=s['name'], url=s.get('url'), domain=s.get('domain'),
            source_page=s.get('source_page'), new_to_us=s.get('new_to_us', False),
            known=s.get('known'), junk=s.get('junk', False),
        )

    first_new = [brief(k) for k in new_keys if seen[k].get('new_to_us')]
    first_known = [brief(k) for k in new_keys if not seen[k].get('new_to_us') and not seen[k].get('junk')]

    out = dict(
        at=stamp,
        log=log,
        cost_usd=0,
        domains=per_domain,
        enabled=sorted(SITES.keys()),
        first_time_candidates=first_new,
        first_time_known=first_known,
        raw_samples=[dict(name=x['name'], url=x.get('url'), domain=x.get('domain'),
                          source_page=x.get('source_page')) for x in all_items[:30]],
        totals=dict(
            domains_ok=sum(1 for v in per_domain.values() if v.get('ok')),
            domains_tried=len(per_domain),
            raw=len(all_items),
            first_time=len(first_new),
            seen_size=len(seen),
        ),
    )
    # 老词新站：对本轮 first_time 候选做后处理（不改 seen、不调 Trends）
    try:
        from radar_oldword_newsites import attach_to_paid_nav_payload
        attach_to_paid_nav_payload(out)
    except Exception as e:
        out['oldword_newsites'] = []
        out['oldword_newsites_model'] = []
        tot = out.setdefault('totals', {})
        tot['oldword_newsites'] = 0
        tot['oldword_newsites_model'] = 0
        tot['oldword_newsites_dropped'] = 0
        out.setdefault('log', []).append(f'oldword_newsites 失败: {type(e).__name__}: {e}')
        print(f'paid_nav/oldword_newsites: FAIL {type(e).__name__}: {e}')

    save_json(os.path.join(a.out, 'radar_paid_nav.json'), out)
    print(f"paid_nav: {out['totals']['domains_ok']}/{out['totals']['domains_tried']} 域成功, "
          f"raw {out['totals']['raw']}, 首次候选 {len(first_new)}（已知 {len(first_known)}）, "
          f"老词新站 demand={out['totals'].get('oldword_newsites', 0)} "
          f"model={out['totals'].get('oldword_newsites_model', 0)}, seen={len(seen)}")
    for l in log[:40]:
        print(' ', l)


if __name__ == '__main__':
    main()
