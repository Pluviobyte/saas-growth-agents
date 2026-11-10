#!/usr/bin/env python3
"""Product Hunt 新品雷达（一手源，抓到就进播报候选）。
用法: python3 radar_producthunt.py --out <目录> [--max-sec 300]

不登录：读公开 Atom 源 https://www.producthunt.com/feed（近期上架，约 50 条）。
可选：若环境变量 PRODUCTHUNT_TOKEN 存在，再走官方 GraphQL 补今日/近几日帖（失败不影响 feed）。
对照 pushed.json / tiktok_pool.json / radar/producthunt_seen.json 去重，记 first_seen。

结果: <out>/radar_producthunt.json；累计库 radar/producthunt_seen.json。"""
import os, sys, re, time, html, argparse, collections
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
from radar_common import *

try:
    from curl_cffi import requests as creq
    def _get(url, headers=None, timeout=30):
        r = creq.get(url, impersonate='chrome131', headers=headers or {}, timeout=timeout, allow_redirects=True)
        return r.status_code, r.text, dict(r.headers)
    def _post(url, json_body, headers=None, timeout=30):
        r = creq.post(url, impersonate='chrome131', json=json_body, headers=headers or {}, timeout=timeout)
        return r.status_code, r.text
except Exception:
    import requests as req
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36'
    def _get(url, headers=None, timeout=30):
        h = {'User-Agent': UA}; h.update(headers or {})
        r = req.get(url, headers=h, timeout=timeout, allow_redirects=True)
        return r.status_code, r.text, dict(r.headers)
    def _post(url, json_body, headers=None, timeout=30):
        h = {'User-Agent': UA, 'Content-Type': 'application/json', 'Accept': 'application/json'}
        h.update(headers or {})
        r = req.post(url, json=json_body, headers=h, timeout=timeout)
        return r.status_code, r.text

SEENF = os.path.join(RD, 'producthunt_seen.json')
FEED = 'https://www.producthunt.com/feed'
GQL = 'https://api.producthunt.com/v2/api/graphql'

# 太泛的产品名不当搜索候选（仍记 seen）
JUNK_NAME = set('product hunt producthunt ai app tools platform software'.split())

def parse_feed(xml):
    """Atom entry -> list of dicts"""
    out = []
    for e in re.findall(r'<entry>(.*?)</entry>', xml, re.S):
        g = lambda p: (re.search(p, e, re.S) or [None, ''])[1]
        title = html.unescape(html.unescape(g(r'<title(?:[^>]*)>(.*?)</title>'))).strip()
        url = g(r'<link[^>]*rel="alternate"[^>]*href="(.*?)"') or g(r'<link[^>]*href="(.*?)"')
        published = g(r'<published>(.*?)</published>')
        updated = g(r'<updated>(.*?)</updated>')
        eid = g(r'<id>(.*?)</id>')
        author = html.unescape(g(r'<name>(.*?)</name>')).strip()
        content = html.unescape(g(r'<content[^>]*>(.*?)</content>'))
        # 第一段 <p> 当 tagline
        tagline = ''
        m = re.search(r'<p>\s*(.*?)\s*</p>', content, re.S)
        if m:
            tagline = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            tagline = html.unescape(tagline)
        # post id：tag:...Post/1288429 或 /r/p/1288429
        pid = ''
        m = re.search(r'Post/(\d+)', eid) or re.search(r'/r/p/(\d+)', content) or re.search(r'/posts/(\d+)', url)
        if m: pid = m.group(1)
        if not title: continue
        out.append(dict(
            name=title, tagline=tagline, url=url or f'https://www.producthunt.com/',
            published=published, updated=updated, author=author, post_id=pid,
            source='atom_feed',
        ))
    return out

def fetch_graphql_recent(token, log, limit=30):
    """官方 API（需 token）；失败返回 []。"""
    if not token: return []
    q = '''query ($first: Int) {
      posts(first: $first, order: NEWEST) {
        edges { node { id name tagline url votesCount createdAt
          topics { edges { node { name } } } } }
      }
    }'''
    try:
        code, text = _post(GQL, {'query': q, 'variables': {'first': limit}},
                           headers={'Authorization': f'Bearer {token}',
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json'})
    except Exception as e:
        log.append(f'graphql: 网络错误 {type(e).__name__}'); return []
    if code != 200:
        log.append(f'graphql: http {code} {text[:160]}'); return []
    try:
        import json as _json
        data = _json.loads(text)
    except Exception as e:
        log.append(f'graphql: JSON 解析失败 {e}'); return []
    if data.get('errors'):
        log.append(f'graphql: {str(data["errors"])[:200]}'); return []
    out = []
    for edge in (((data.get('data') or {}).get('posts') or {}).get('edges') or []):
        n = edge.get('node') or {}
        topics = [t['node']['name'] for t in ((n.get('topics') or {}).get('edges') or []) if t.get('node')]
        out.append(dict(
            name=n.get('name') or '', tagline=n.get('tagline') or '',
            url=n.get('url') or '', published=n.get('createdAt') or '',
            updated=n.get('createdAt') or '', author='', post_id=str(n.get('id') or ''),
            votes=n.get('votesCount'), topics=topics, source='graphql',
        ))
    return [x for x in out if x['name']]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-sec', type=int, default=int(os.environ.get('RADAR_PH_MAX_SEC', 300)))
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    deadline = time.time() + a.max_sec; log = []; stamp = nows()
    posts = []; feed_ok = False

    if time.time() <= deadline:
        try:
            code, text, _ = _get(FEED, timeout=30)
            if code == 200 and '<entry>' in text:
                posts = parse_feed(text); feed_ok = True
            else:
                log.append(f'feed: http {code} 或无 entry')
        except Exception as e:
            log.append(f'feed: 网络错误 {type(e).__name__}: {e}')

    token = os.environ.get('PRODUCTHUNT_TOKEN') or os.environ.get('PH_API_TOKEN') or ''
    gql_posts = []
    if token and time.time() <= deadline:
        gql_posts = fetch_graphql_recent(token, log)
        log.append(f'graphql: 拿到 {len(gql_posts)} 条')
    elif not token:
        log.append('未设置 PRODUCTHUNT_TOKEN，仅用公开 Atom feed')

    # 合并：同一 post_id / 同名优先保留 votes/topics 更全的
    by_key = collections.OrderedDict()
    for p in posts + gql_posts:
        ck = p.get('post_id') or key(p['name'])
        if not ck: continue
        old = by_key.get(ck)
        if old is None:
            by_key[ck] = p
        else:
            # 合并字段
            for f in ('tagline', 'url', 'published', 'votes', 'topics', 'author'):
                if p.get(f) and not old.get(f): old[f] = p[f]
            if p.get('source') == 'graphql': old['source'] = 'graphql+feed' if old.get('source') == 'atom_feed' else p['source']

    seen = load_json(SEENF, {}); idx = known_index()
    new_keys = []
    for ck, p in by_key.items():
        name = (p.get('name') or '').strip()
        junk = key(name) in {key(x) for x in JUNK_NAME} or len(key(name)) < 2
        s = seen.get(ck)
        if s is None:
            kn = None if junk else match_known(name, idx)
            s = seen[ck] = dict(
                name=name, tagline=p.get('tagline') or '', url=p.get('url') or '',
                post_id=p.get('post_id') or '', first_seen=stamp,
                published=p.get('published') or '', author=p.get('author') or '',
                topics=p.get('topics') or [], votes=p.get('votes'),
                known=(dict(src=kn[0], as_=kn[1], date=kn[2]) if kn else None),
                new_to_us=(not kn and not junk), junk=junk,
                source=p.get('source'), runs=0, sightings=0,
            )
            new_keys.append(ck)
        s['runs'] += 1; s['sightings'] += 1; s['last_seen'] = stamp
        if p.get('tagline'): s['tagline'] = p['tagline']
        if p.get('url'): s['url'] = p['url']
        if p.get('votes') is not None: s['votes'] = p['votes']
        if p.get('topics'): s['topics'] = p['topics']
        s['published'] = p.get('published') or s.get('published')

    save_json(SEENF, seen)

    def brief(ck):
        s = seen[ck]
        return dict(name=s['name'], tagline=s.get('tagline'), url=s.get('url'),
                    post_id=s.get('post_id'), published=s.get('published'),
                    votes=s.get('votes'), topics=s.get('topics') or [],
                    new_to_us=s.get('new_to_us', False), known=s.get('known'),
                    source=s.get('source'), junk=s.get('junk', False))

    first_new = [brief(k) for k in new_keys if seen[k].get('new_to_us')]
    first_known = [brief(k) for k in new_keys if not seen[k].get('new_to_us') and not seen[k].get('junk')]
    recurring = [brief(k) for k in by_key if k not in new_keys and seen[k].get('new_to_us')][:50]

    out = dict(
        at=stamp, feed_ok=feed_ok, posts=len(by_key),
        log=log, cost_usd=0,
        first_time_candidates=first_new,
        first_time_known=first_known,
        recurring=recurring,
        raw_samples=[dict(name=p['name'], tagline=p.get('tagline'), url=p.get('url'),
                          published=p.get('published'), post_id=p.get('post_id'),
                          votes=p.get('votes'), source=p.get('source'))
                     for p in list(by_key.values())[:20]],
    )
    save_json(os.path.join(a.out, 'radar_producthunt.json'), out)
    print(f"producthunt: feed_ok={feed_ok}, {len(by_key)} 个产品, 首次候选 {len(first_new)}（已知 {len(first_known)}）")
    for l in log: print(' ', l)

if __name__ == '__main__':
    main()
