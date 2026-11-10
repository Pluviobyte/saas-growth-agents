#!/usr/bin/env python3
"""Reddit 雷达（只采集，不进播报）。
用法: python3 radar_reddit.py --out <目录> [--subs a,b,c] [--feed rising|new] [--max-sec 900]
Reddit 对本机的 .json 接口返回 403 / 跳登录，所以走公开 RSS（www.reddit.com/r/<sub>/<feed>/.rss）。
不登录的 RSS 限速约每分钟 1 次：按响应头 x-ratelimit-reset 等待，429 时退避重试一次；超总时长就停。
从帖子标题里抽可能的新产品 / 模型 / 游戏 / 梗名，对照 pushed.json、tiktok_pool.json 和 radar/reddit_seen.json 去重，记 first_seen。
结果: <out>/radar_reddit.json；累计库 radar/reddit_seen.json。"""
import os, sys, re, json, time, html, argparse, collections
import requests
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
from radar_common import *

UA = 'linux:newterm-radar:v0.2 (collection-only keyword research)'
SUBS = ['aivideo', 'StableDiffusion', 'LocalLLaMA', 'singularity', 'ChatGPT', 'OpenAI', 'ClaudeAI',
        'WebGames', 'IndieGaming', 'TikTokCringe', 'memes']
SEENF = os.path.join(RD, 'reddit_seen.json')
STOP = set("""i a an the my our your this that these those it its is are was were be been am do does did have has had
we you they he she him her them me us of in on at to for from with by and or but not no yes so if then than as just
what why how when where who which new old first last best top any all some more most very really still now today
ai llm llms gpu gpus cpu ram vram api app apps ui ux os pc mac ios android tl dr tldr psa til eli5 imo imho lol lmao
omg wtf fyi faq ama oc nsfw usa us uk eu ceo cto vs pro max mini ultra plus free open source model models update
anyone someone everyone can could would should will may might must here there help question discussion meme memes
video videos image images game games demo trailer steam reddit youtube tiktok twitter x hd 4k 8k 1080p q a
paper exclusive released release solve tested boosts invests ex online today tomorrow yesterday utc gmt mb gb tb tok fps sota
open-source cpu-only cfg lora moe tts stt hbm sec psi rtx gguf workflow workflows node nodes edit turbo dev pst est""".split())
MONTHS = set("jan feb mar apr may jun jul aug sep sept oct nov dec january february march april june july august september october november december monday tuesday wednesday thursday friday saturday sunday".split())
JUNK = re.compile(r"^(?:\d+(?:st|nd|rd|th|mp|min|mins|k|fps|gb|mb|tb|hz|%)|20\d\d|\d+[:/]\d+)$", re.I)
SIZE = re.compile(r"^(?:a?\d+(?:\.\d+)?[bmk]|\d+(?:\.\d+)?-?bit)$", re.I)
EVERGREEN = set('iphone ipad macbook airpods playstation xbox nintendo switch chatgpt openai claude anthropic gemini google gpt grok xai meta llama deepseek qwen mistral nvidia apple microsoft sora midjourney stable diffusion flux comfyui kling veo runway suno elon musk trump'.split())
VER = re.compile(r'^(?:v?\d+(?:\.\d+)*[a-z]?|\d+[bkmt]|a\d+(?:\.\d+)?b)$', re.I)

def fetch(sub, feed, deadline, log):
    url = f'https://www.reddit.com/r/{sub}/{feed}/.rss?limit=50'
    for attempt in range(2):
        if time.time() > deadline: log.append(f'{sub}: 超出总时长，跳过'); return None, 0
        try: r = requests.get(url, headers={'User-Agent': UA}, timeout=30)
        except Exception as e: log.append(f'{sub}: 网络错误 {type(e).__name__}'); return None, 5
        reset = int(float(r.headers.get('x-ratelimit-reset') or 60))
        remain = float(r.headers.get('x-ratelimit-remaining') or 0)
        wait = 0 if remain >= 1 else min(reset + 1, 75)
        if r.status_code == 200: return r.text, wait
        if r.status_code == 429 and attempt == 0:
            time.sleep(min(reset + 2, 75)); continue
        log.append(f'{sub}: http {r.status_code}'); return None, wait
    return None, 60

def entries(xml, sub):
    out = []
    for e in re.findall(r'<entry>(.*?)</entry>', xml, re.S):
        g = lambda p: (re.search(p, e, re.S) or [None, ''])[1]
        content = html.unescape(g(r'<content type="html">(.*?)</content>'))
        out.append(dict(sub=sub, title=html.unescape(html.unescape(g(r'<title>(.*?)</title>'))).strip(),
                        url=g(r'<link href="(.*?)"'), published=g(r'<published>(.*?)</published>'),
                        author=g(r'<name>(.*?)</name>'),
                        links=sorted(set(re.findall(r'href="(https?://[^"]+)"', content)))[:10]))
    return out

def is_namey(tok):
    return bool(re.match(r'^[A-Za-z0-9][\w.\-+/]*$', tok) and (tok[0].isupper() or tok[0].isdigit() or re.search(r'[A-Z]', tok[1:]) is not None)) and tok.lower() not in STOP or bool(VER.match(tok))

def extract(post):
    """返回 [(名字, 类型线索)]"""
    found = []
    for l in post['links']:
        m = re.match(r'https?://huggingface\.co/([\w.\-]+)/([\w.\-]+)', l)
        if m and m.group(1) not in ('datasets', 'spaces', 'docs', 'blog', 'papers'): found.append((m.group(2).replace('-', ' '), 'hf_model'))
        m = re.match(r'https?://([\w\-]+)\.itch\.io/([\w\-]+)', l)
        if m: found.append((m.group(2).replace('-', ' '), 'itch_game'))
        m = re.match(r'https?://store\.steampowered\.com/app/\d+/([\w]+)', l)
        if m: found.append((m.group(1).replace('_', ' '), 'steam_game'))
    t = re.sub(r'[\[\]()"“”«»!?,;:|]', ' ', post['title'])
    m = re.search(r'https?://huggingface\.co/([\w.\-]+)/([\w.\-]+)', post['title'])
    if m: found.append((m.group(2).replace('-', ' '), 'hf_model'))
    toks = t.split()
    run = []
    def flush():
        if not run: return
        words = [w.strip('.-') for w in run]
        words = [w for w in words if w]
        while words and words[0].lower() in STOP: words.pop(0)
        while words and (words[-1].lower() in STOP or SIZE.match(words[-1])) and len(words) > 1: words.pop()
        if words and words[-1].lower() in STOP: words.pop()
        if any(w.lower() in MONTHS or JUNK.match(w) for w in words): words = []
        if words and all(len(w) <= 4 and (w.isupper() or VER.match(w)) for w in words): words = []
        if words and len(words) <= 5 and not all(VER.match(w) for w in words):
            has_ver = any(VER.match(w) for w in words) and any(re.search('[a-z]', w, re.I) and not VER.match(w) for w in words)
            camel = any(re.search(r'[a-z][A-Z]|[A-Za-z]\d|\d[A-Za-z]{2,}', w) for w in words)
            caps = any(re.match(r'^[A-Z]{3,}$', w) and w.lower() not in STOP for w in words)
            low = {w.lower() for w in words}
            only_evergreen = low <= EVERGREEN | STOP
            if (has_ver or camel or (caps and len(words) >= 2)) and not (only_evergreen and not has_ver):
                found.append((' '.join(words), 'title'))
        run.clear()
    for i, tok in enumerate(toks):
        if is_namey(tok) and not (i == 0 and tok.lower() in STOP): run.append(tok)
        else: flush()
    flush()
    if post['sub'] in ('WebGames', 'IndieGaming'):
        m = re.match(r'^\s*([A-Z][\w\'’ ]{2,40}?)\s+(?:[-–—|:])\s', post['title'])
        if m and len(m.group(1).split()) <= 5: found.append((m.group(1).strip(), 'game_title'))
    keys = [key(n) for n, _ in found]
    found = [(n, k) for (n, k), kk in zip(found, keys) if not any(o != kk and len(o) >= 4 and o in kk for o in keys)]
    seen, out = set(), []
    for n, k in found:
        kk = key(n)
        if len(kk) >= 3 and kk not in seen and not kk.isdigit(): seen.add(kk); out.append((n, k))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--subs', default=','.join(SUBS))
    ap.add_argument('--from-raw', default=None, help='调试用：用已存 radar_reddit.json 的帖子重新抽词，不联网');
    ap.add_argument('--feed', default='rising'); ap.add_argument('--max-sec', type=int, default=int(os.environ.get('RADAR_REDDIT_MAX_SEC', 900)))
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    deadline = time.time() + a.max_sec; log = []; posts = []; subs_out = {}
    if a.from_raw:
        r0 = json.load(open(a.from_raw)); posts = r0['raw_posts']; subs_out = r0['subs']
    for i, sub in enumerate([] if a.from_raw else a.subs.split(',')):
        xml, wait = fetch(sub, a.feed, deadline, log)
        es = entries(xml, sub) if xml else []
        subs_out[sub] = dict(ok=xml is not None, posts=len(es)); posts += es
        if i < len(a.subs.split(',')) - 1 and time.time() + wait < deadline: time.sleep(max(wait, 3))
    seen = load_json(SEENF, {}); idx = known_index(); stamp = nows()
    agg = collections.OrderedDict()
    for p in posts:
        for n, kind in extract(p):
            ck = key(n)
            e = agg.setdefault(ck, dict(name=n, kinds=set(), subs=set(), posts=[]))
            e['kinds'].add(kind); e['subs'].add(p['sub'])
            if len(e['posts']) < 3: e['posts'].append(dict(title=p['title'][:140], url=p['url'], published=p['published']))
    new = []
    for ck, e in agg.items():
        s = seen.get(ck)
        if s is None:
            kn = match_known(e['name'], idx)
            s = seen[ck] = dict(name=e['name'], first_seen=stamp, kinds=sorted(e['kinds']), subs=sorted(e['subs']),
                                known=(dict(src=kn[0], as_=kn[1], date=kn[2]) if kn else None), new_to_us=not kn,
                                runs=0, mentions=0, example=e['posts'][0])
            new.append(ck)
        s['runs'] += 1; s['mentions'] += len(e['posts']); s['last_seen'] = stamp
        s['subs'] = sorted(set(s['subs']) | e['subs']); s['kinds'] = sorted(set(s['kinds']) | e['kinds'])
    save_json(SEENF, seen)
    def brief(ck):
        s = seen[ck]; return dict(name=s['name'], new_to_us=s['new_to_us'], known=s['known'], kinds=s['kinds'], subs=s['subs'],
                                  mentions_this_run=len(agg[ck]['posts']), example=s['example'])
    out = dict(at=stamp, feed=a.feed, subs=subs_out, posts=len(posts), log=log, cost_usd=0,
               first_time_candidates=[brief(ck) for ck in new if seen[ck]['new_to_us']],
               first_time_known=[brief(ck) for ck in new if not seen[ck]['new_to_us']],
               recurring=[brief(ck) for ck in agg if ck not in new and seen[ck]['new_to_us']][:50],
               raw_posts=posts)
    save_json(os.path.join(a.out, 'radar_reddit.json'), out)
    ok = sum(1 for v in subs_out.values() if v['ok'])
    print(f"reddit: {ok}/{len(subs_out)} 个版块拿到, {len(posts)} 帖, 首次出现候选 {len(out['first_time_candidates'])}（已知词 {len(out['first_time_known'])}）")
    for l in log: print(' ', l)

if __name__ == '__main__':
    main()
