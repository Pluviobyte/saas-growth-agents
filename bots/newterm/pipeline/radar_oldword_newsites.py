#!/usr/bin/env python3
"""老词新站：在付费导航本轮候选上做后处理（无 AIsa/Trends 调用）。

老词 = pushed / keyword_domain_shells / 可选 cache 里、词龄大致 ≥2025-05 的监控池词。
新站 = 导航 newly listed 工具，且产品域名/产品名明显对准该老词（壳站），非纯品牌 SaaS。
只发现，不提交付费。

分类（2026-11-03 口径纠正）：
- demand：需求/能力场景词（image to video、vocal remover…）→ 主列表 oldword_newsites
- model：模型名+版本壳（模型名 + 版本号）→ 辅列表 oldword_newsites_model
- other：纯品牌域串等 → 不进主/辅列表（可记 dropped）
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.parse import urlparse

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from radar_common import RD, load_json, save_json, norm, key, nows

OLDWORD_MIN_DATE = "2025-05-01"

# 展示名 / slug 末尾常见 TLD（用于从 Headoffis Com、agentgrid-io 还原产品域）
# 名字里已带点的 TLD（BulkImg.ai、foo.online）
TLD_LABELS_DOTTED = (
    "com", "ai", "io", "app", "net", "dev", "gg", "co", "org", "me", "so",
    "xyz", "info", "tech", "tools", "video", "online", "pro", "site", "cloud",
)
# 从「Headoffis Com」/ slug「agentgrid-io」推断时只用短可信 TLD（避免 Online/Video 英文词）
TLD_LABELS_INFER = (
    "com", "ai", "io", "app", "net", "dev", "gg", "co", "org", "me", "so",
    "xyz", "info", "tech", "tools", "pro",
)
TLD_LABELS = TLD_LABELS_DOTTED  # 兼容旧引用

# 单 token 命中后允许残留的壳站后缀（compact）
FILLER_SUFFIXES = (
    "ai", "app", "io", "com", "net", "dev", "gg", "hq", "pro", "lab", "labs",
    "tool", "tools", "online", "video", "videos", "free", "generator", "maker",
    "studio", "hub", "site", "web", "app", "bot", "gpt",
)

# 短 evergreen / 办事词黑名单（整词或明显短语，不进老词表）
EVERGREEN_BLACKLIST_RE = re.compile(
    r"^(how\s+to|near\s+me|.*\bcalculator\b|.*\bmeaning\b|.*\bdefinition\b|"
    r".*\bwikipedia\b|.*\bweather\b|.*\btranslate\b|.*\bconverter\b|"
    r"what\s+is|where\s+is|best\s+.*\s+near\s+me)$",
    re.I,
)
EVERGREEN_EXACT = {
    "ai", "video", "videos", "meme", "memes", "tiktok", "filter", "trend",
    "trends", "template", "templates", "generator", "free", "online", "app",
    "tool", "tools", "download", "login", "price", "pricing",
}

NAV_BRAND_DOMAINS = {
    "toolify.ai", "gptdemo.net", "aixploria.com", "bestaito.com", "creati.ai",
    "theresanaiforthat.com", "topai.tools", "dang.ai", "betalist.com",
    "saashub.com", "uneed.best", "fazier.com", "alternativeto.net",
    "startupfa.me", "twelve.tools", "bestfreeaiwebsites.com",
}

# 导航详情页常见 path → slug
SLUG_PATH_RE = re.compile(
    r"/(?:t|tool|ai-tools|startups|ai|gpt|product|products)/([a-z0-9][a-z0-9-]*)/?",
    re.I,
)
NAME_TLD_RE = re.compile(
    r"(?i)\b([a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.(?:" + "|".join(TLD_LABELS_DOTTED) + r"))\b"
)
NAME_SPACE_TLD_RE = re.compile(
    r"(?i)^([a-z0-9][a-z0-9-]*)\s*\.?\s+(" + "|".join(TLD_LABELS_INFER) + r")$"
)


# ---------- 需求词 / 模型壳 分类 ----------
# 模型品牌+可选版本（compact 上匹配；也覆盖带版本号的写法）
MODEL_TERM_RE = re.compile(
    r"(?:"
    r"veo\d*|kling\d*|seedance\d*|flux\d*|sora\d*|"
    r"runway(?:gen)?\d*|midjourney|nanobanana\d*|"
    r"hunyuan\d*|hailuo\d*|lumadream|pika\d*|minimax\w*|"
    r"claudecode|claude(?:opus|sonnet|haiku)\d*|"
    r"ideogram\d*|stablediffusion|dalle\d*|imagen\d*|gptimage\d*|"
    r"luma(?:ai|dream)?\d*|gen-?3|gen-?4"
    r")"
)
# 空格写法补充（nano banana、luma dream、claude code）
MODEL_SPACED_RE = re.compile(
    r"(?i)\b(?:"
    r"nano\s*banana|luma\s*dream|claude\s*code|"
    r"veo\s*\d*|kling\s*\d*|seedance(?:\s*[\d.]+)?|"
    r"flux\s*\d*|sora\s*\d*|runway\s*gen\s*\d*|"
    r"midjourney|hunyuan|hailuo|pika\s*\d*|minimax|"
    r"stable\s*diffusion|dall-?e\s*\d*|imagen\s*\d*"
    r")\b"
)

# 能力/场景 hint（在 compact 或原文小写里找）；维护时可加反例见 DEMAND_NEGATIVE
DEMAND_HINTS = (
    "remove", "remover", "enhance", "enhancer", "upscale", "upscaler", "upscaling",
    "summarize", "summarizer", "summary", "generator", "tovideo", "toimage",
    "imagetovideo", "videotoimage", "videoto", "texttovideo", "texttoimage",
    "image to video", "video to image", "text to video", "text to image",
    "to video", "to image", "clothes", "aicloth", "clotheschange", "outfit",
    "tryon", "try on", "vocal", "background", "bgremove", "backgroundremove",
    "outpaint", "inpaint", "faceswap", "face swap", "voiceclone", "voice clone",
    "transcript", "transcribe", "downloader", "watermark", "photoenhance",
    "voiceover", "dubbing", "lipsync", "lip sync", "headshot", "restore",
    "colorize", "denoise", "humanize", "animation", "enlarge", "uncensor",
    "faceenhance", "objectremove", "karaoke", "stemsplit", "splitvocal",
    "bg removal", "background removal", "photo enhancer", "vocal remover",
    "ai clothes", "summarize youtube", "youtube summary", "youtube summar",
    # deep 2026-11-03: scene / JTBD expansions that found nav+RDAP hits
    "hairstyle", "hair color", "haircolor", "changehair", "buzzcut", "longhair",
    "genderswap", "gender swap", "headswap", "head swap",
    "tattoo", "inkspo", "voicecloner", "voice clone", "texttospeech", "tts",
    "podcast", "lyricvideo", "lyric video", "removebg", "remove bg",
    "videoupscale", "video upscale", "videoenhancer", "video enhancer",
    "photoenhancer", "readpdf", "pdf aloud", "pdf2mp3", "pdf to video", "pdftovideo",
    "imageto3d", "image to 3d", "to3d", "phototovideo", "photo to video", "picvideo",
    "stemsplitter", "stem split", "virtualtry", "virtual try", "tryon",
    "videoextend", "video extender", "ugcvideo", "ugc video", "faceless",
    "datingphoto", "dating photo", "babygenerator", "baby generator", "pettalk", "pet talk",
    "cartoonize", "animefy", "unblur", "objectremover", "object remover",
    "watermarkremover", "watermark remover", "tapedit", "photo editor",
    "floorplan", "roomdesign", "room design", "virtual staging", "staging",
    "mockup", "thumbnail", "meme", "gif maker", "passport", "id photo",
    "paraphras", "aidetector", "ai detector", "content detector", "chatpdf",
    "mindmap", "flashcard", "aitutor", "mejorarcalidad", "mejorar",
    "airsong", "songmaker", "musictool", "coversong", "ai cover", "singing",
    "talkinghead", "talking head", "talkingphoto", "avatar", "headshotgenerator",
    "bulkimg", "bulk image", "imagetext", "pictext", "logoanimation", "logo animation",
    "aidance", "ai dance", "rapvideo", "ai rap", "captions", "autodub", "videodubber",
    "humanizer", "gpthumanizer", "ai2human", "a2human",
)
# 仅有这些 filler、又无其它 hint 时不算需求
DEMAND_NEGATIVE_ONLY = {
    "free", "online", "ai", "app", "com", "io", "net", "dev", "tool", "tools",
    "pro", "hub", "lab", "labs", "studio", "site", "web", "bot", "gpt", "hq",
}


def classify_kind(matched_term: str, product_domain: str = "", name: str = "") -> str:
    """demand | model | other。先模型，再需求；纯品牌域串 → other。"""
    term = (matched_term or "").strip()
    dom = (product_domain or "").strip()
    nm = (name or "").strip()
    spaced = " ".join(x for x in (term, dom, nm) if x).lower()
    term_c = compact(term)
    dom_c = compact(dom.split(".")[0] if dom else "")  # registrable-ish
    all_c = compact(spaced)

    # 模型：看 matched_term / product 主标签
    for blob, cblob in ((term, term_c), (dom, compact(dom)), (nm, compact(nm))):
        if not blob:
            continue
        if MODEL_SPACED_RE.search(blob) or (cblob and MODEL_TERM_RE.search(cblob)):
            return "model"

    # 需求：hint 落在 term / domain / name
    for hint in DEMAND_HINTS:
        h = hint.lower().strip()
        if not h:
            continue
        hc = compact(h)
        if " " in h:
            if h in spaced:
                return "demand"
            if hc and hc in all_c:
                return "demand"
        else:
            if hc and (hc in term_c or hc in all_c or hc in dom_c):
                return "demand"

    return "other"


def compact(s: str) -> str:
    return "".join(norm(s))


def is_evergreen(term: str) -> bool:
    t = (term or "").strip().lower()
    if not t:
        return True
    if t in EVERGREEN_EXACT:
        return True
    if EVERGREEN_BLACKLIST_RE.match(t):
        return True
    if len(compact(t)) < 4:
        return True
    return False


def load_oldword_lexicon(include_cache: bool = True):
    """返回 list[{term, compact, tokens, earliest, sources}]；无外部 API。"""
    by_c = {}

    def add(term, earliest="", source=""):
        term = (term or "").strip()
        if not term or is_evergreen(term):
            return
        c = compact(term)
        if len(c) < 4:
            return
        # 词龄：有日期则必须 ≥ OLDWORD_MIN_DATE；无日期保留（监控池）
        if earliest and earliest[:10] < OLDWORD_MIN_DATE:
            return
        cur = by_c.get(c)
        if cur is None:
            by_c[c] = {
                "term": term,
                "compact": c,
                "tokens": norm(term),
                "earliest": (earliest or "")[:10],
                "sources": [source] if source else [],
            }
        else:
            if source and source not in cur["sources"]:
                cur["sources"].append(source)
            if earliest and (not cur["earliest"] or earliest[:10] < cur["earliest"]):
                cur["earliest"] = earliest[:10]
                # 保留更早那条的展示写法若当前像域名噪音
                if "." not in term and "." in cur["term"]:
                    cur["term"] = term

    pushed = load_json(os.path.join(D, "pushed.json"), {})
    for k, dates in pushed.items():
        earliest = ""
        if isinstance(dates, list) and dates:
            earliest = min(str(x)[:10] for x in dates if x)
        elif isinstance(dates, str):
            earliest = dates[:10]
        add(k, earliest, "pushed")

    shells = load_json(os.path.join(RD, "keyword_domain_shells.json"), {})
    for it in shells.get("items") or []:
        add(it.get("term") or "", it.get("first_seen") or "", "shells")
        # 壳站域名本身也常是对准词（agentgrid.io 类）
        dom = (it.get("domain") or "").strip().lower()
        if dom and "." in dom:
            add(dom, it.get("first_seen") or "", "shells_domain")

    if include_cache:
        cache = load_json(os.path.join(D, "cache.json"), {})
        # cache: {date: {term: {... first: 'YYYY-MM-DD'}}}
        if isinstance(cache, dict):
            for _day, bucket in cache.items():
                if not isinstance(bucket, dict):
                    continue
                for term, meta in bucket.items():
                    if not isinstance(meta, dict):
                        continue
                    first = str(meta.get("first") or "")[:10]
                    add(term, first, "cache")

    exclude_owner = set(
        (x or "").strip().lower()
        for x in (shells.get("exclude_owner_sites") or [])
    )
    return list(by_c.values()), exclude_owner


_SLUG_STOP = {
    "video", "videos", "image", "images", "photo", "to", "for", "the", "and", "with",
    "free", "best", "new", "tool", "tools", "generator", "maker", "from", "into",
    "your", "my", "online", "download",
}

def _slug_base_looks_like_domain(base: str) -> bool:
    """拒绝 dang/creati 式长描述 slug（some-meme-video-ai-image-to-video）。"""
    parts = [p for p in (base or "").split("-") if p]
    if not parts or len(parts) > 3:
        return False
    if len(compact(base)) > 28:
        return False
    if sum(1 for p in parts if p in _SLUG_STOP) >= 2:
        return False
    # 版本号段允许：model-2-5
    return True

def _slug_to_product_domains(slug: str):
    """agentgrid-io → agentgrid.io；model-2-5-io → model-2-5.io / model25.io。"""
    out = []
    slug = (slug or "").strip("-").lower()
    if not slug:
        return out
    for tld in TLD_LABELS_INFER:
        suf = "-" + tld
        if slug.endswith(suf) and len(slug) > len(suf):
            base = slug[: -len(suf)]
            if base and _slug_base_looks_like_domain(base):
                out.append(f"{base}.{tld}")
                out.append(f"{base.replace('-', '')}.{tld}")
            break
    return out


def extract_product_clues(name: str, url: str):
    """从展示名 + 导航详情 URL 抽产品域线索（不是导航站 domain 字段）。"""
    clues = []  # list of {product_domain, registrable, compact, via}
    seen = set()

    def push(dom: str, via: str):
        dom = (dom or "").strip().lower().rstrip(".")
        if not dom or "." not in dom:
            return
        # 丢掉导航站自己
        if dom in NAV_BRAND_DOMAINS or any(dom.endswith("." + n) for n in NAV_BRAND_DOMAINS):
            return
        host = dom.split("/")[0]
        labels = host.split(".")
        if len(labels) < 2:
            return
        tld = labels[-1]
        if tld not in TLD_LABELS_DOTTED and len(tld) > 4:
            return
        registrable = ".".join(labels[:-1])  # 简化：去掉最后一截当 TLD
        # 若是 www.x.ai 这类，去掉 www
        if registrable.startswith("www."):
            registrable = registrable[4:]
        reg_c = compact(registrable)
        if len(reg_c) < 3:
            return
        key_d = host
        if key_d in seen:
            return
        seen.add(key_d)
        clues.append(
            dict(
                product_domain=host,
                registrable=registrable,
                compact=reg_c,
                via=via,
            )
        )

    name = name or ""
    url = url or ""

    for m in NAME_TLD_RE.finditer(name):
        push(m.group(1), "name_tld")

    m = NAME_SPACE_TLD_RE.match(name.strip())
    if m:
        left = re.sub(r"[^a-z0-9.-]+", "", m.group(1).lower().replace(" ", ""))
        # "Headoffis Com" → headoffis.com；保留内部连字符
        left2 = re.sub(r"[^a-z0-9-]+", "", m.group(1).lower().replace(" ", "-"))
        push(f"{left}.{m.group(2).lower()}", "name_space_tld")
        if left2 != left:
            push(f"{left2}.{m.group(2).lower()}", "name_space_tld")

    path = urlparse(url).path
    sm = SLUG_PATH_RE.search(path)
    if sm:
        for dom in _slug_to_product_domains(sm.group(1)):
            push(dom, "url_slug")

    # saashub 等：/nexusmarketintel-com
    if not sm and url:
        last = urlparse(url).path.rstrip("/").split("/")[-1]
        if last and "-" in last:
            for dom in _slug_to_product_domains(last):
                push(dom, "url_tail")

    return clues


def _tokens_in_order(tokens, hay_c: str) -> bool:
    if not tokens or not hay_c:
        return False
    pos = 0
    for tok in tokens:
        i = hay_c.find(tok, pos)
        if i < 0:
            return False
        pos = i + len(tok)
    return True


def _suffix_ok(hay_c: str, term_c: str) -> bool:
    """hay 以 term 开头时，剩余是否仅为壳站 filler。"""
    if not hay_c.startswith(term_c):
        return False
    rest = hay_c[len(term_c) :]
    if not rest:
        return True
    # 反复剥 filler
    changed = True
    while rest and changed:
        changed = False
        for suf in FILLER_SUFFIXES:
            if rest.endswith(suf) and len(rest) >= len(suf):
                rest = rest[: -len(suf)]
                changed = True
                break
            if rest.startswith(suf) and len(rest) >= len(suf):
                rest = rest[len(suf) :]
                changed = True
                break
    return rest == ""


def match_candidate(name: str, url: str, lexicon, exclude_owner):
    """偏严命中：返回 {matched_term, product_domain, reason} 或 None。"""
    clues = extract_product_clues(name, url)
    name_c = compact(name)
    # 去掉展示名里尾部孤立 TLD 词后再 compact（Headoffis Com）
    name_for_match = re.sub(
        r"(?i)\s*\.?\s+(?:" + "|".join(TLD_LABELS_INFER) + r")\s*$", "", name or ""
    ).strip()
    name_c2 = compact(name_for_match) or name_c

    # 产品域落在用户自有站 → 排除
    for cl in clues:
        if cl["product_domain"] in exclude_owner:
            return None

    best = None

    for entry in lexicon:
        term = entry["term"]
        term_c = entry["compact"]
        toks = entry["tokens"]
        if len(term_c) < 4:
            continue

        # 1) 展示名 compact 全等
        if name_c == term_c or name_c2 == term_c:
            # 纯品牌且无产品域线索时：仅当展示名本身带 TLD / 像壳，才报
            if clues or ("." in (name or "")) or NAME_SPACE_TLD_RE.match((name or "").strip()):
                best = dict(
                    matched_term=term,
                    product_domain=(clues[0]["product_domain"] if clues else None),
                    reason=f"name_compact=={term_c}",
                )
                break
            # 无域线索的纯名相等：多半是品牌 SaaS 与词表偶合，跳过
            continue

        # 2) 产品 registrable compact 全等
        hit_cl = None
        for cl in clues:
            if cl["compact"] == term_c:
                hit_cl = cl
                break
            # 单 token：registrable = term + filler
            if len(toks) == 1 and _suffix_ok(cl["compact"], term_c):
                hit_cl = cl
                break
        if hit_cl:
            best = dict(
                matched_term=term,
                product_domain=hit_cl["product_domain"],
                reason=f"product_reg=={term_c} via {hit_cl['via']}",
            )
            break

        # 3) 多 token：词的全部 token 按序出现在产品域或展示名 compact 里
        if len(toks) >= 2:
            for cl in clues:
                if _tokens_in_order(toks, cl["compact"]) and (
                    cl["compact"] == term_c or _suffix_ok(cl["compact"], term_c)
                    or (term_c in cl["compact"] and len(term_c) / max(len(cl["compact"]), 1) >= 0.55)
                ):
                    best = dict(
                        matched_term=term,
                        product_domain=cl["product_domain"],
                        reason=f"tokens_in_product_domain:{','.join(toks)}",
                    )
                    break
            if best:
                break
            if clues and _tokens_in_order(toks, name_c2) and term_c in name_c2 and (
                name_c2 == term_c or _suffix_ok(name_c2, term_c)
                or len(term_c) / max(len(name_c2), 1) >= 0.55
            ):
                # 多 token 名称命中必须已有产品域线索（壳站），避免纯描述品名
                best = dict(
                    matched_term=term,
                    product_domain=clues[0]["product_domain"],
                    reason=f"tokens_in_name:{','.join(toks)}",
                )
                break

        # 4) 单 token：产品域 compact 含 term 且 suffix ok（已在 2 处理）；
        #    或 name_c2 以 term 起头且 suffix ok，且有域线索
        if len(toks) == 1 and clues:
            for cl in clues:
                if term_c in cl["compact"] and _suffix_ok(cl["compact"], term_c):
                    best = dict(
                        matched_term=term,
                        product_domain=cl["product_domain"],
                        reason=f"single_token_product:{term_c}",
                    )
                    break
            if best:
                break

    return best


def scan_oldword_newsites(candidates, lexicon=None, exclude_owner=None, include_other=False):
    """对候选列表筛老词新站。candidates: dicts with name/url/domain/source_page。

    默认返回 demand + model（各带 kind）；other 默认丢弃。
    include_other=True 时把 other 也放进结果（冒烟看 dropped 用）。
    """
    if lexicon is None or exclude_owner is None:
        lexicon, exclude_owner = load_oldword_lexicon()
    # 按 compact 长度降序，优先更具体的词
    lexicon = sorted(lexicon, key=lambda e: len(e["compact"]), reverse=True)

    hits = []
    seen_keys = set()
    for cand in candidates or []:
        name = cand.get("name") or ""
        url = cand.get("url") or ""
        m = match_candidate(name, url, lexicon, exclude_owner)
        if not m:
            continue
        sk = f"{key(name)}|{m.get('product_domain') or ''}|{m['matched_term']}"
        if sk in seen_keys:
            continue
        seen_keys.add(sk)
        kind = classify_kind(m["matched_term"], m.get("product_domain") or "", name)
        if kind == "other" and not include_other:
            continue
        hits.append(
            dict(
                name=name,
                product_domain=m.get("product_domain"),
                matched_term=m["matched_term"],
                kind=kind,
                url=url,
                source_page=cand.get("source_page") or "",
                nav_domain=cand.get("domain") or "",
                reason=m.get("reason") or "",
            )
        )
    return hits


def attach_to_paid_nav_payload(out: dict) -> dict:
    """就地写入 oldword_newsites（仅 demand）/ oldword_newsites_model / totals。"""
    lexicon, exclude_owner = load_oldword_lexicon()
    pool = list(out.get("first_time_candidates") or [])
    # 可选：已知词但本轮首次出现在导航、且带壳域线索者
    for x in out.get("first_time_known") or []:
        if extract_product_clues(x.get("name") or "", x.get("url") or ""):
            pool.append(x)
    # include_other 以便计数 dropped；写出时再拆
    raw = scan_oldword_newsites(
        pool, lexicon=lexicon, exclude_owner=exclude_owner, include_other=True
    )
    demand = [h for h in raw if h.get("kind") == "demand"]
    model = [h for h in raw if h.get("kind") == "model"]
    dropped = [h for h in raw if h.get("kind") == "other"]
    out["oldword_newsites"] = demand
    out["oldword_newsites_model"] = model
    tot = out.setdefault("totals", {})
    tot["oldword_newsites"] = len(demand)
    tot["oldword_newsites_model"] = len(model)
    tot["oldword_newsites_dropped"] = len(dropped)
    tot["oldword_lexicon_size"] = len(lexicon)
    return out


def main():
    ap = argparse.ArgumentParser(description="离线/冒烟：筛老词新站")
    ap.add_argument("--from-json", default="", help="读已有 radar_paid_nav.json 并写回字段")
    ap.add_argument("--write", action="store_true", help="写回 --from-json")
    ap.add_argument("--also-seen-sample", action="store_true",
                    help="额外对 paid_nav_seen 里带域线索的条目做样例扫描（不改 seen）")
    ap.add_argument("--out-side", default="", help="旁路输出 radar_oldword_newsites.json 路径")
    a = ap.parse_args()

    lexicon, exclude_owner = load_oldword_lexicon()
    print(f"oldword lexicon={len(lexicon)} exclude_owner={len(exclude_owner)} at={nows()}")

    if a.from_json:
        data = load_json(a.from_json, {})
        # 冒烟：先拿含 other 的 raw，再 attach 写正式字段
        pool = list(data.get("first_time_candidates") or [])
        for x in data.get("first_time_known") or []:
            if extract_product_clues(x.get("name") or "", x.get("url") or ""):
                pool.append(x)
        raw = scan_oldword_newsites(
            pool, lexicon=lexicon, exclude_owner=exclude_owner, include_other=True
        )
        demand = [h for h in raw if h.get("kind") == "demand"]
        model = [h for h in raw if h.get("kind") == "model"]
        dropped = [h for h in raw if h.get("kind") == "other"]
        attach_to_paid_nav_payload(data)
        tot = data.get("totals") or {}
        print(
            f"from {a.from_json}: first_time={len(data.get('first_time_candidates') or [])} "
            f"demand={tot.get('oldword_newsites', len(demand))} "
            f"model={tot.get('oldword_newsites_model', len(model))} "
            f"dropped={tot.get('oldword_newsites_dropped', len(dropped))}"
        )
        for h in demand:
            print(f"  DEMAND {h['name']} → term={h['matched_term']} "
                  f"product={h.get('product_domain')} ({h.get('reason')}) "
                  f"via {h.get('nav_domain')}")
        for h in model:
            print(f"  MODEL  {h['name']} → term={h['matched_term']} "
                  f"product={h.get('product_domain')} ({h.get('reason')}) "
                  f"via {h.get('nav_domain')}")
        for h in dropped:
            print(f"  DROP   {h['name']} → term={h['matched_term']} "
                  f"product={h.get('product_domain')} ({h.get('reason')})")
        # 未命中样例
        lex_sorted = sorted(lexicon, key=lambda e: len(e["compact"]), reverse=True)
        for c in (data.get("first_time_candidates") or [])[:20]:
            if not match_candidate(
                c.get("name") or "", c.get("url") or "", lex_sorted, exclude_owner
            ):
                clues = extract_product_clues(c.get("name") or "", c.get("url") or "")
                print(f"  MISS {c.get('name')} clues={[x['product_domain'] for x in clues]}")
        if a.write:
            save_json(a.from_json, data)
            print(f"wrote {a.from_json}")
        if a.out_side:
            save_json(
                a.out_side,
                dict(
                    at=nows(),
                    totals=dict(
                        oldword_newsites=len(demand),
                        oldword_newsites_model=len(model),
                        oldword_newsites_dropped=len(dropped),
                        oldword_lexicon_size=len(lexicon),
                    ),
                    oldword_newsites=demand,
                    oldword_newsites_model=model,
                    oldword_newsites_dropped=dropped,
                    source=a.from_json,
                ),
            )
            print(f"side {a.out_side}")

    if a.also_seen_sample:
        seen = load_json(os.path.join(RD, "paid_nav_seen.json"), {})
        cands = []
        for _ck, s in seen.items():
            if s.get("junk"):
                continue
            name, url = s.get("name") or "", s.get("url") or ""
            if extract_product_clues(name, url):
                cands.append(dict(
                    name=name, url=url, domain=s.get("domain"),
                    source_page=s.get("source_page") or "",
                ))
        # 去重 by name
        uniq = {}
        for c in cands:
            uniq.setdefault(key(c["name"]), c)
        hits = scan_oldword_newsites(
            list(uniq.values()), lexicon=lexicon, exclude_owner=exclude_owner, include_other=True
        )
        dem = [h for h in hits if h.get("kind") == "demand"]
        mod = [h for h in hits if h.get("kind") == "model"]
        drp = [h for h in hits if h.get("kind") == "other"]
        print(
            f"seen domain-clue names={len(uniq)} "
            f"demand={len(dem)} model={len(mod)} dropped={len(drp)} (seen file NOT modified)"
        )
        for h in dem[:15]:
            print(f"  SEEN_DEMAND {h['name']} → {h['matched_term']} / {h.get('product_domain')}")
        for h in mod[:15]:
            print(f"  SEEN_MODEL  {h['name']} → {h['matched_term']} / {h.get('product_domain')}")
        for h in drp[:15]:
            print(f"  SEEN_DROP   {h['name']} → {h['matched_term']} / {h.get('product_domain')}")
        # 几个明确未命中
        for label in ("Stella", "SubSplitHQ", "Jelli", "Syncraft", "Colony"):
            for c in uniq.values():
                if c["name"] == label:
                    m = match_candidate(c["name"], c["url"], lexicon, exclude_owner)
                    print(f"  SEEN_CHECK {label}: {'HIT '+m['matched_term'] if m else 'MISS (ok)'}")
                    break


if __name__ == "__main__":
    main()
