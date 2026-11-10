#!/usr/bin/env python3
"""把 <目录>/radar_*.json 汇总成 <目录>/radar.md（雷达汇总）。用法: python3 radar_md.py <目录>"""
import os, sys, json
d = sys.argv[1]
def lj(n):
    try: return json.load(open(os.path.join(d, n)))
    except Exception: return None
L = [f'# 雷达汇总', f'目录：{d}', '']
s = lj('radar_sitemaps.json')
L.append('## 一、模板站 sitemap')
if not s: L.append('- 本轮没跑成（看 radar_sitemaps.log）')
else:
    L.append(f"- 时间 {s['at']}（北京时间），打分花费 ${s.get('cost_usd', 0)}")
    for site, v in s['sites'].items():
        tp = {'meme': '梗', 'ai': 'AI', 'event': '游戏活动'}.get(v.get('type', 'meme'), '')
        if v.get('ok'): L.append(f"- {site}（{tp}）：共 {v['total_urls']} 个网址，" + ('首次建基线，不出候选' if v.get('baseline') else f"比上次新增 {v['new_urls']} 个"))
        else: L.append(f"- {site}：失败 {v.get('error', '')}")
    new = [c for c in s['new_candidates'] if c['new_to_us']]
    L.append(f"- 本轮新出现的候选 {len(s['new_candidates'])} 个，其中我们没记过的 {len(new)} 个：")
    for c in new:
        sites = '、'.join(f"{k}（{v.get('published') or v.get('lastmod') or '无日期'}）" for k, v in c['sites'].items())
        sc = c.get('score')
        scs = f"；热度（取较高的写法 {sc['term']}）7天均值 {sc['ratio_7d']}× / 近24h {sc['last24_ratio']}× GPTs" if sc else ''
        tp = '/'.join({'meme': '梗', 'ai': 'AI', 'event': '游戏活动'}.get(x, x) for x in c.get('types', ['meme']))
        hl = f"（标题：{c['headline']}）" if c.get('headline') and c['headline'] != c['name'] else ''
        L.append(f"  - [{tp}] {c['name']}{hl}：{sites}{scs}")
    old = [c for c in s['new_candidates'] if not c['new_to_us']]
    if old: L.append('- 已记过的（新页面对应老梗）：' + '、'.join(f"{c['name']}→{c['known']['as_']}" for c in old))
    for l in s.get('log', []): L.append(f'- 备注：{l}')

L.append(''); L.append('## 二、Reddit')
r = lj('radar_reddit.json')
if not r: L.append('- 本轮没跑成或还在跑（看 radar_reddit.log）')
else:
    ok = sum(1 for v in r['subs'].values() if v['ok'])
    L.append(f"- 时间 {r['at']}，{ok}/{len(r['subs'])} 个版块拿到（{r['feed']} RSS），共 {r['posts']} 帖，花费 $0")
    bad = [k for k, v in r['subs'].items() if not v['ok']]
    if bad: L.append('- 没拿到：' + '、'.join(bad))
    L.append(f"- 首次出现、我们没记过的候选 {len(r['first_time_candidates'])} 个（机器抽取，噪音较多）：")
    for c in r['first_time_candidates'][:40]:
        L.append(f"  - {c['name']}（r/{'、r/'.join(c['subs'])}）例：{c['example']['title'][:90]}")
    if r['first_time_known']: L.append('- 首次在 Reddit 出现但已记过：' + '、'.join(f"{c['name']}→{c['known']['as_']}" for c in r['first_time_known'][:20]))
    for l in r.get('log', []): L.append(f'- 备注：{l}')

L.append(''); L.append('## 三、CapCut 模板')
c = lj('radar_capcut.json')
if not c: L.append('- 本轮没跑成或还在跑（看 radar_capcut.log）')
else:
    ok = sum(1 for v in c.get('cats', {}).values() if v.get('ok'))
    L.append(f"- 时间 {c['at']}，{ok}/{len(c.get('cats', {}))} 个目录页拿到，共 {c.get('templates', 0)} 个模板，花费 $0")
    if c.get('blocked'): L.append('- ⚠ 全部目录页失败（可能风控）；见备注')
    L.append(f"- 首次出现、我们没记过的候选 {len(c.get('first_time_candidates', []))} 个：")
    for x in c.get('first_time_candidates', [])[:40]:
        cats = '、'.join(x.get('cats') or [])
        L.append(f"  - {x['name']}（slug: {x.get('slug', '')}；{cats}）{x.get('url', '')}")
    if c.get('first_time_known'):
        L.append('- 首次在 CapCut 出现但已记过：' + '、'.join(f"{x['name']}→{x['known']['as_']}" for x in c['first_time_known'][:20] if x.get('known')))
    for l in c.get('log', []): L.append(f'- 备注：{l}')

L.append(''); L.append('## 四、Product Hunt')
p = lj('radar_producthunt.json')
if not p: L.append('- 本轮没跑成或还在跑（看 radar_producthunt.log）')
else:
    L.append(f"- 时间 {p['at']}，feed_ok={p.get('feed_ok')}，共 {p.get('posts', 0)} 个产品，花费 $0")
    L.append(f"- 首次出现、我们没记过的候选 {len(p.get('first_time_candidates', []))} 个：")
    for x in p.get('first_time_candidates', [])[:40]:
        tl = f"：{x['tagline'][:80]}" if x.get('tagline') else ''
        votes = f"，{x['votes']} votes" if x.get('votes') is not None else ''
        L.append(f"  - {x['name']}{tl}{votes} {x.get('url', '')}")
    if p.get('first_time_known'):
        L.append('- 首次在 PH 出现但已记过：' + '、'.join(f"{x['name']}→{x['known']['as_']}" for x in p['first_time_known'][:20] if x.get('known')))
    for l in p.get('log', []): L.append(f'- 备注：{l}')


L.append(''); L.append('## 五、GitHub Trending')
g = lj('radar_github_trending.json')
if not g: L.append('- 本轮没跑成或还在跑（看 radar_github_trending.log）')
else:
    L.append(f"- 时间 {g['at']}，path={g.get('path')}，html_ok={g.get('html_ok')}，共 {g.get('repos', 0)} 个仓库，花费 $0")
    L.append(f"- 首次出现、我们没记过的候选 {len(g.get('first_time_candidates', []))} 个：")
    for x in g.get('first_time_candidates', [])[:40]:
        desc = f"：{(x.get('description') or '')[:80]}" if x.get('description') else ''
        st = f"，今日 +{x['stars_today']}★" if x.get('stars_today') else ''
        lang = f"（{x['language']}）" if x.get('language') else ''
        L.append(f"  - {x.get('full_name') or x['name']}{lang}{desc}{st} {x.get('url', '')}")
    if g.get('first_time_known'):
        L.append('- 首次在 Trending 出现但已记过：' + '、'.join(f"{x.get('full_name') or x['name']}→{x['known']['as_']}" for x in g['first_time_known'][:20] if x.get('known')))
    for l in g.get('log', []): L.append(f'- 备注：{l}')



L.append(''); L.append('## 六、付费导航新上架')
pn = lj('radar_paid_nav.json')
if not pn: L.append('- 本轮没跑成或还在跑（看 radar_paid_nav.log）')
else:
    tot = pn.get('totals') or {}
    L.append(f"- 时间 {pn.get('at')}，域成功 {tot.get('domains_ok', 0)}/{tot.get('domains_tried', 0)}，raw {tot.get('raw', 0)}，花费 $0")
    for dom, st in (pn.get('domains') or {}).items():
        if st.get('ok'):
            bl = '，首次建基线' if st.get('baseline') else f"，本轮新候选 {st.get('first_new', 0)}"
            L.append(f"- {dom}：抓取 {st.get('urls_fetched', 0)} URL，raw {st.get('raw_count', 0)}{bl}")
        else:
            err = (st.get('errors') or [st.get('error') or '失败'])[:1]
            L.append(f"- {dom}：失败 {err[0] if err else ''}")
    L.append(f"- 首次出现、我们没记过的候选 {len(pn.get('first_time_candidates', []))} 个：")
    for x in pn.get('first_time_candidates', [])[:40]:
        L.append(f"  - {x['name']}（{x.get('domain','')}）{x.get('url', '')}")
    if pn.get('first_time_known'):
        L.append('- 首次在付费导航出现但已记过：' + '、'.join(
            f"{x['name']}→{x['known']['as_']}" for x in pn['first_time_known'][:20] if x.get('known')))
    # 老词新站（付费导航新上架子节）：需求词主列表 + 模型壳辅节
    L.append('- **老词新站**（需求/能力场景词；导航新上架对准监控池老词；一手源不看 Trends）：')
    ows = pn.get('oldword_newsites') or []
    if not ows:
        L.append('  - 无')
    else:
        for x in ows[:40]:
            pd = x.get('product_domain') or '（无域线索）'
            L.append(
                f"  - {x.get('name')} → 老词「{x.get('matched_term')}」· 产品域 {pd} · "
                f"导航 {x.get('nav_domain') or ''} {x.get('url') or ''}"
            )
    owm = pn.get('oldword_newsites_model') or []
    if owm:
        L.append('- **模型壳站（辅）**（模型名+版本壳；降权，有才写）：')
        for x in owm[:40]:
            pd = x.get('product_domain') or '（无域线索）'
            L.append(
                f"  - {x.get('name')} → 模型词「{x.get('matched_term')}」· 产品域 {pd} · "
                f"导航 {x.get('nav_domain') or ''} {x.get('url') or ''}"
            )
    for l in pn.get('log', [])[:20]:
        L.append(f'- 备注：{l}')

t = lj('tiktok.json')
if t and os.path.basename(d.rstrip('/')).split('_')[-1].startswith('night'):
    L.append(''); L.append('## 七、TikTok（夜间只采集，不打分）')
    L.append(f"- 结果见 {os.path.join(d, 'tiktok.json')}")
open(os.path.join(d, 'radar.md'), 'w').write('\n'.join(L) + '\n')
print('\n'.join(L))
