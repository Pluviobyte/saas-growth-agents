#!/usr/bin/env python3
"""CapCut 热门模板雷达（一手源，抓到就进播报候选）。
用法: python3 radar_capcut.py --out <目录> [--max-sec 600] [--cats a,b,c]

不登录：拉公开模板目录页 https://www.capcut.com/template 及分类页，
从 /template-detail/<slug>/<id> 链接抽模板名，对照 pushed.json / tiktok_pool.json /
radar/capcut_seen.json 去重，记 first_seen。

结果: <out>/radar_capcut.json；累计库 radar/capcut_seen.json。
若 CapCut 全挡，写出空 first_time_candidates + log 原因（不抛致命错）。"""
import os, sys, re, time, argparse, collections, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
from radar_common import *

try:
    from curl_cffi import requests as creq
    def _get(url, timeout=30):
        r = creq.get(url, impersonate='chrome131', timeout=timeout, allow_redirects=True)
        return r.status_code, r.text
except Exception:
    import requests as req
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36'
    def _get(url, timeout=30):
        r = req.get(url, headers={'User-Agent': UA}, timeout=timeout, allow_redirects=True)
        return r.status_code, r.text

SEENF = os.path.join(RD, 'capcut_seen.json')
BASE = 'https://www.capcut.com'
# 主目录 + 公开分类（来自 /template 页导航）
DEFAULT_CATS = ['', 'social', 'effects', 'editors-pick', 'holiday', 'business',
                'anniversary', 'calendar', 'industry', 'record', 'insights', 'others']
# 从 URL slug 里丢掉的噪音词（保留梗/产品名）
SLUG_FILLER = set("""
fyp foryou foryoupage fypage viral viralcapcut capcut template templates templatetouse
trend trends newtrend meme memes funny funnyvideo edit edits editing transition transitions
filter filters effect effects ai tiktok instagram reels shorts video videos free touse
usecreds pressstart clips clip recap preview edition subscribe glowreveal vacationmoments
creds needed no to use protemplateid cinematicvideo cinematic photocollage recaptrend
""".split())
# 整段 slug / 清洗后名字太泛、不当候选
JUNK_SLUG = set("""
trend viral foryou foryou-viral foryou-trend fyp-trend-viral-capcut zptfyp-fyp
subscribe effects effect fixed enjoy issi ihtx free-to-use free-to-use-template-no-creds-needed
green-screen preview
""".split())
JUNK_NAME = set("""
subscribe effects effect fixed enjoy issi ihtx free use to use green screen
preview edition template templates viral trend trends fyp foryou
travel slide daily day vlog life teamwork workshop seminar business training
social help blur watermark shortvideo contentcreators capcutcreators
""".split())

def cat_url(cat):
    return f'{BASE}/template/{cat}' if cat else f'{BASE}/template'

def clean_slug(slug):
    s = urllib.parse.unquote(slug or '')
    s = re.sub(r'[%＋]+', ' ', s)
    s = s.replace('_', '-').replace('—', '-').replace('–', '-')
    words = [w for w in re.split(r'[-/\s]+', s) if w]
    kept = [w for w in words if w.lower() not in SLUG_FILLER and not re.fullmatch(r'\d+', w) and len(w) > 1]
    # 不要回退到 filler；太空就返回空，交给 junk 过滤
    name = re.sub(r'\s+', ' ', ' '.join(kept).strip())
    return name[:80]

def extract_details(html):
    """返回 [(slug, template_id, url)] 去重保序"""
    out, seen = [], set()
    for slug, tid in re.findall(r'https?://(?:www\.)?capcut\.com/template-detail/([^/"\'?\s]+)/(\d+)', html):
        slug = urllib.parse.unquote(slug)
        if tid in seen: continue
        seen.add(tid)
        url = f'{BASE}/template-detail/{urllib.parse.quote(slug, safe="")}/{tid}'
        out.append((slug, tid, url))
    # 相对路径兜底
    for slug, tid in re.findall(r'/template-detail/([^/"\'?\s]+)/(\d+)', html):
        slug = urllib.parse.unquote(slug)
        if tid in seen: continue
        seen.add(tid)
        url = f'{BASE}/template-detail/{urllib.parse.quote(slug, safe="")}/{tid}'
        out.append((slug, tid, url))
    return out

def fetch_cat(cat, deadline, log):
    if time.time() > deadline:
        log.append(f'{cat or "main"}: 超出总时长，跳过'); return cat, None, []
    url = cat_url(cat)
    try:
        code, text = _get(url, timeout=35)
    except Exception as e:
        log.append(f'{cat or "main"}: 网络错误 {type(e).__name__}: {e}'); return cat, None, []
    if code != 200:
        log.append(f'{cat or "main"}: http {code}'); return cat, code, []
    items = extract_details(text)
    if not items:
        # 可能是空壳 SPA：记一下
        log.append(f'{cat or "main"}: 200 但未解析到 template-detail 链接')
    return cat, code, items

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--cats', default=','.join(DEFAULT_CATS))
    ap.add_argument('--max-sec', type=int, default=int(os.environ.get('RADAR_CAPCUT_MAX_SEC', 600)))
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    deadline = time.time() + a.max_sec; log = []; stamp = nows()
    cats = [c.strip() for c in a.cats.split(',')]
    # 空字符串表示主页；保留顺序去重
    seen_c, ordered = set(), []
    for c in cats:
        if c in seen_c: continue
        seen_c.add(c); ordered.append(c)

    cat_out = {}; all_items = []  # (slug, tid, url, cat)
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        futs = {ex.submit(fetch_cat, c, deadline, log): c for c in ordered}
        for fut in as_completed(futs):
            cat, code, items = fut.result()
            cat_out[cat or 'main'] = dict(ok=code == 200, http=code, templates=len(items), url=cat_url(cat))
            for slug, tid, url in items:
                all_items.append((slug, tid, url, cat or 'main'))

    # 按 template id 聚合
    agg = collections.OrderedDict()
    for slug, tid, url, cat in all_items:
        e = agg.setdefault(tid, dict(slug=slug, tid=tid, url=url, cats=set(), name=clean_slug(slug)))
        e['cats'].add(cat)
        # 更长的 slug 往往信息更多，用来刷新 name
        if len(slug) > len(e['slug']):
            e['slug'] = slug; e['url'] = url; e['name'] = clean_slug(slug)

    seen = load_json(SEENF, {}); idx = known_index()
    new_ids = []
    for tid, e in agg.items():
        name = (e.get('name') or '').strip()
        # 过泛 / 洗空的 slug 不当候选名（仍记入 seen，避免反复刷）
        junk = (
            (not name)
            or key(name) in {key(x) for x in JUNK_SLUG}
            or key(name) in {key(x) for x in JUNK_NAME}
            or len(key(name)) < 4
            or (len(name.split()) == 1 and len(name) <= 4)
            or re.fullmatch(r'[\d\s.]+', name) is not None
        )
        s = seen.get(tid)
        if s is None:
            kn = None if junk else match_known(name, idx)
            s = seen[tid] = dict(
                name=name, slug=e['slug'], tid=tid, url=e['url'],
                first_seen=stamp, cats=sorted(e['cats']),
                known=(dict(src=kn[0], as_=kn[1], date=kn[2]) if kn else None),
                new_to_us=(not kn and not junk), junk=junk,
                runs=0, sightings=0,
            )
            new_ids.append(tid)
        s['runs'] += 1; s['sightings'] += 1; s['last_seen'] = stamp
        s['cats'] = sorted(set(s.get('cats', [])) | e['cats'])
        s['url'] = e['url']; s['slug'] = e['slug']
        if name and not s.get('junk'): s['name'] = name

    save_json(SEENF, seen)

    def brief(tid):
        s = seen[tid]
        return dict(name=s['name'], slug=s.get('slug'), tid=tid, url=s.get('url'),
                    new_to_us=s.get('new_to_us', False), known=s.get('known'),
                    cats=s.get('cats', []), junk=s.get('junk', False))

    first_new = [brief(t) for t in new_ids if seen[t].get('new_to_us')]
    first_known = [brief(t) for t in new_ids if not seen[t].get('new_to_us') and not seen[t].get('junk')]
    recurring = [brief(t) for t, e in agg.items() if t not in new_ids and seen[t].get('new_to_us')][:50]

    blocked = all(not v.get('ok') for v in cat_out.values()) if cat_out else True
    if blocked:
        log.append('全部目录页失败：可能被风控/地区限制。下一步可用浏览器登录态或 HAR 抓 edit-api 模板 feed。')
    if not agg and not blocked:
        log.append('目录页可访问但无 template-detail：页面结构可能已变。')

    out = dict(
        at=stamp, source='capcut_web_template_pages', cats=cat_out,
        templates=len(agg), log=log, cost_usd=0, blocked=blocked,
        first_time_candidates=first_new,
        first_time_known=first_known,
        recurring=recurring,
        raw_samples=[{'name': brief(t)['name'], 'slug': agg[t]['slug'], 'tid': t, 'url': agg[t]['url'],
                     'cats': sorted(agg[t]['cats'])} for t in list(agg)[:30]],
    )
    save_json(os.path.join(a.out, 'radar_capcut.json'), out)
    ok = sum(1 for v in cat_out.values() if v.get('ok'))
    print(f"capcut: {ok}/{len(cat_out)} 个目录页拿到, {len(agg)} 个模板, 首次候选 {len(first_new)}（已知 {len(first_known)}）")
    for l in log: print(' ', l)

if __name__ == '__main__':
    main()
