#!/usr/bin/env python3
"""拉哥飞新词服务批次：python3 gefei_api.py [--days 1] [--min 0.2]
令牌从 .env 的 GEFEI_API_KEY 读（wc_mcp_ 开头，在 https://seo.web.cafe/api/ 登录后生成）。
存 gefei_<batch_id>.json（已存在的批次跳过），打印最新批次 heat_ratio>=min 的词。"""
import os, sys, json, time, datetime as dt, requests
D = os.path.dirname(os.path.abspath(__file__)); BASE = 'https://seo.web.cafe/api/v1'
def key():
    k = os.environ.get('GEFEI_API_KEY')
    p = os.path.join(D, '.env')
    if not k and os.path.exists(p):
        for l in open(p):
            if l.strip().startswith('GEFEI_API_KEY='): k = l.split('=', 1)[1].strip().strip('"\'')
    if not k: sys.exit('缺少 GEFEI_API_KEY（写进本目录的 .env）')
    return k
S = requests.Session()
def get(path, params=None):
    for i in range(5):
        r = S.get(BASE + path, params=params, headers={'Authorization': f'Bearer {key()}'}, timeout=30)
        if r.status_code == 429:
            time.sleep(int(r.headers.get('Retry-After') or 20) + 2); continue
        j = r.json()
        if not j.get('ok'): sys.exit(f"{path} -> HTTP {r.status_code} {j.get('code')}: {j.get('error')}")
        return j['data']
    sys.exit(f'{path} 多次 429')
def main():
    a = sys.argv; days = int(a[a.index('--days')+1]) if '--days' in a else 1
    mn = float(a[a.index('--min')+1]) if '--min' in a else 0.2
    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime('%Y-%m-%d')
    bl, page = [], 1
    while True:
        d = get('/keywords/batches', {'page': page}); items = d.get('items') or d.get('batches') or []
        new = [b for b in items if (b.get('finished_at') or '')[:10] >= since]; bl += new
        if not d.get('has_more') or len(new) < len(items): break
        page += 1; time.sleep(2)
    if not bl:   # 当天没新批次也至少拿最新一批
        bl = (d.get('items') or d.get('batches') or [])[:1]
    for b in bl:
        f = os.path.join(D, f"gefei_{b['id']}.json")
        if os.path.exists(f): continue
        time.sleep(2); data = get(f"/keywords/batches/{b['id']}")
        json.dump(dict(batch=b, data=data), open(f, 'w'), ensure_ascii=False, indent=1); print('saved', f)
    if bl:
        kws = json.load(open(os.path.join(D, f"gefei_{bl[0]['id']}.json")))['data']
        kws = kws.get('keywords') or kws.get('items') or []
        print(f"最新批次 {bl[0]['id']} 共 {len(kws)} 词，heat_ratio>={mn}:")
        for k in sorted(kws, key=lambda k: -(k.get('heat_ratio') or 0)):
            if (k.get('heat_ratio') or 0) >= mn:
                print(f"  {k['keyword']}  GPTs×{k['heat_ratio']}  {k.get('kind')}/{k.get('category')}  {k.get('trend_now')}  {k.get('verdict')}")
if __name__ == '__main__': main()
