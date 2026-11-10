#!/usr/bin/env python3
"""GitHub Trending 雷达（一手源，抓到就进播报候选）。
用法: python3 radar_github_trending.py --out <目录> [--max-sec 180]

主路径：公开 HTML https://github.com/trending?since=daily
  （overall + python / typescript / javascript；curl_cffi chrome impersonate）
回退：GitHub Search API（可选 GH_TOKEN 提高限额）——近 1 天高星新建/热库，非真正 Trending 榜。
对照 pushed.json / tiktok_pool.json / radar/github_trending_seen.json 去重，记 first_seen。

结果: <out>/radar_github_trending.json；累计库 radar/github_trending_seen.json。"""
import os, sys, re, time, html, argparse, collections
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
from radar_common import *

try:
    from curl_cffi import requests as creq
    def _get(url, headers=None, timeout=30):
        r = creq.get(url, impersonate='chrome131', headers=headers or {}, timeout=timeout, allow_redirects=True)
        return r.status_code, r.text, dict(r.headers)
except Exception:
    import requests as req
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36'
    def _get(url, headers=None, timeout=30):
        h = {'User-Agent': UA}; h.update(headers or {})
        r = req.get(url, headers=h, timeout=timeout, allow_redirects=True)
        return r.status_code, r.text, dict(r.headers)

SEENF = os.path.join(RD, 'github_trending_seen.json')
BASE = 'https://github.com/trending'
# language 空串 = overall
LANGS = ['', 'python', 'typescript', 'javascript']
JUNK_NAME = set('github trending demo test example hello world awesome list templates'.split())

def _num(s):
    try: return int(re.sub(r'[^\d]', '', s or '') or 0)
    except Exception: return 0

def parse_trending_html(page, page_lang=''):
    """解析 Trending 页 article.Box-row -> list of dicts"""
    out = []
    for block in re.findall(r'<article class="Box-row">([\s\S]*?)</article>', page):
        hm = re.search(r'<h2[^>]*>\s*<a[^>]*href="(/[^"\s]+)"', block)
        if not hm: continue
        path = hm.group(1).strip('/')
        parts = path.split('/')
        if len(parts) < 2: continue
        full_name = f'{parts[0]}/{parts[1]}'
        repo = parts[1]
        # 描述
        dm = re.search(r'<p class="col-9[^"]*"[^>]*>([\s\S]*?)</p>', block)
        desc = ''
        if dm:
            desc = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', dm.group(1))).strip())
        # 语言
        lm = re.search(r'itemprop="programmingLanguage">([^<]+)', block)
        lang = (lm.group(1).strip() if lm else '') or page_lang or ''
        # 今日星 / 总星
        stm = re.search(r'([\d,]+)\s+stars?\s+today', block, re.I)
        stars_today = _num(stm.group(1) if stm else '0')
        tsm = re.search(r'href="[^"]*/stargazers"[^>]*>\s*(?:<svg[\s\S]*?</svg>\s*)?([\d,]+)', block)
        stars = _num(tsm.group(1) if tsm else '0')
        # 可搜词：仓库名，连字符转空格（与 newterm.src_github 一致）
        term = re.sub(r'[-_]+', ' ', repo).strip()
        out.append(dict(
            full_name=full_name, name=term, repo=repo, owner=parts[0],
            description=desc, language=lang, stars=stars, stars_today=stars_today,
            url=f'https://github.com/{full_name}',
            source='trending_html', page_lang=page_lang or 'overall',
        ))
    return out

def fetch_html_pages(log, deadline):
    repos = []; ok_pages = 0
    for lang in LANGS:
        if time.time() > deadline: break
        url = f'{BASE}/{lang}?since=daily' if lang else f'{BASE}?since=daily'
        label = lang or 'overall'
        try:
            code, text, _ = _get(url, timeout=30)
            if code == 200 and 'Box-row' in text:
                items = parse_trending_html(text, page_lang=lang)
                repos.extend(items); ok_pages += 1
                log.append(f'html/{label}: {len(items)} 条')
            else:
                log.append(f'html/{label}: http {code} 或无 Box-row')
        except Exception as e:
            log.append(f'html/{label}: 网络错误 {type(e).__name__}: {e}')
        time.sleep(0.4)
    return repos, ok_pages

def fetch_api_fallback(log, deadline, per_page=30):
    """Search API 回退：近 1 天按星排序（不是真正 Trending，仅兜底）。"""
    import requests as req
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'newterm-radar'}
    if token: headers['Authorization'] = f'Bearer {token}'
    since = (now() - dt.timedelta(days=1)).strftime('%Y-%m-%d')
    if time.time() > deadline: return []
    try:
        r = req.get('https://api.github.com/search/repositories',
                    params=dict(q=f'created:>{since}', sort='stars', order='desc', per_page=per_page),
                    headers=headers, timeout=30)
        if r.status_code != 200:
            log.append(f'api_fallback: http {r.status_code} {r.text[:120]}'); return []
        out = []
        for it in r.json().get('items') or []:
            full = it.get('full_name') or ''
            if '/' not in full: continue
            owner, repo = full.split('/', 1)
            term = re.sub(r'[-_]+', ' ', repo).strip()
            out.append(dict(
                full_name=full, name=term, repo=repo, owner=owner,
                description=(it.get('description') or '')[:300],
                language=it.get('language') or '',
                stars=it.get('stargazers_count') or 0, stars_today=0,
                url=it.get('html_url') or f'https://github.com/{full}',
                source='search_api', page_lang='api',
            ))
        log.append(f'api_fallback: 拿到 {len(out)} 条（created:>{since}）')
        return out
    except Exception as e:
        log.append(f'api_fallback: 失败 {type(e).__name__}: {e}'); return []

def merge_repos(items):
    """按 full_name 合并；保留 stars_today 更高 / 描述更全的。"""
    by = collections.OrderedDict()
    for p in items:
        ck = (p.get('full_name') or '').lower()
        if not ck: continue
        old = by.get(ck)
        if old is None:
            by[ck] = p; continue
        if (p.get('stars_today') or 0) > (old.get('stars_today') or 0):
            old['stars_today'] = p['stars_today']
        if (p.get('stars') or 0) > (old.get('stars') or 0):
            old['stars'] = p['stars']
        if p.get('description') and not old.get('description'):
            old['description'] = p['description']
        if p.get('language') and not old.get('language'):
            old['language'] = p['language']
        # 记录出现过的语言页
        pages = set(old.get('pages') or [old.get('page_lang')])
        pages.add(p.get('page_lang') or '')
        old['pages'] = sorted(x for x in pages if x)
        if p.get('source') == 'trending_html' and old.get('source') != 'trending_html':
            old['source'] = 'trending_html'
    for v in by.values():
        if 'pages' not in v:
            v['pages'] = [v.get('page_lang')] if v.get('page_lang') else []
    return by

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-sec', type=int, default=int(os.environ.get('RADAR_GH_TREND_MAX_SEC', 180)))
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    deadline = time.time() + a.max_sec; log = []; stamp = nows()

    repos, ok_pages = fetch_html_pages(log, deadline)
    html_ok = ok_pages > 0
    path_used = 'html' if html_ok else 'none'
    if not html_ok:
        log.append('HTML Trending 全部失败，尝试 Search API 回退')
        repos = fetch_api_fallback(log, deadline)
        path_used = 'api_fallback' if repos else 'failed'

    by_key = merge_repos(repos)
    seen = load_json(SEENF, {}); idx = known_index()
    new_keys = []
    for ck, p in by_key.items():
        name = (p.get('name') or '').strip()
        full = p.get('full_name') or ''
        junk = key(name) in {key(x) for x in JUNK_NAME} or len(key(name)) < 2
        s = seen.get(ck)
        if s is None:
            kn = None if junk else match_known(name, idx)
            if kn is None and not junk and full:
                kn = match_known(full.replace('/', ' '), idx)
            s = seen[ck] = dict(
                full_name=full, name=name, repo=p.get('repo') or '', owner=p.get('owner') or '',
                description=p.get('description') or '', language=p.get('language') or '',
                url=p.get('url') or '', stars=p.get('stars') or 0,
                stars_today=p.get('stars_today') or 0, pages=p.get('pages') or [],
                first_seen=stamp,
                known=(dict(src=kn[0], as_=kn[1], date=kn[2]) if kn else None),
                new_to_us=(not kn and not junk), junk=junk,
                source=p.get('source'), runs=0, sightings=0,
            )
            new_keys.append(ck)
        s['runs'] += 1; s['sightings'] += 1; s['last_seen'] = stamp
        if p.get('description'): s['description'] = p['description']
        if p.get('url'): s['url'] = p['url']
        if p.get('language'): s['language'] = p['language']
        if p.get('stars'): s['stars'] = p['stars']
        if p.get('stars_today') is not None: s['stars_today'] = p['stars_today']
        if p.get('pages'): s['pages'] = p['pages']

    save_json(SEENF, seen)

    def brief(ck):
        s = seen[ck]
        return dict(
            full_name=s.get('full_name'), name=s['name'], description=s.get('description'),
            language=s.get('language'), url=s.get('url'), stars=s.get('stars'),
            stars_today=s.get('stars_today'), pages=s.get('pages') or [],
            new_to_us=s.get('new_to_us', False), known=s.get('known'),
            source=s.get('source'), junk=s.get('junk', False),
        )

    first_new = [brief(k) for k in new_keys if seen[k].get('new_to_us')]
    first_known = [brief(k) for k in new_keys if not seen[k].get('new_to_us') and not seen[k].get('junk')]
    recurring = [brief(k) for k in by_key if k not in new_keys and seen[k].get('new_to_us')][:50]

    out = dict(
        at=stamp, html_ok=html_ok, path=path_used, pages_ok=ok_pages,
        repos=len(by_key), log=log, cost_usd=0,
        first_time_candidates=first_new,
        first_time_known=first_known,
        recurring=recurring,
        raw_samples=[dict(full_name=p['full_name'], name=p['name'], description=p.get('description'),
                          language=p.get('language'), stars=p.get('stars'),
                          stars_today=p.get('stars_today'), url=p.get('url'),
                          source=p.get('source'), pages=p.get('pages'))
                     for p in list(by_key.values())[:20]],
    )
    save_json(os.path.join(a.out, 'radar_github_trending.json'), out)
    print(f"github_trending: path={path_used}, html_ok={html_ok}, {len(by_key)} 个仓库, "
          f"首次候选 {len(first_new)}（已知 {len(first_known)}）")
    for l in log: print(' ', l)

if __name__ == '__main__':
    main()
