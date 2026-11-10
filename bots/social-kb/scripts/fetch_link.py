#!/usr/bin/env python3
"""链接 -> 统一格式的素材 JSON（社媒分析 Bot 的第一步）。

  python3 fetch_link.py <链接> [--out 目录]

按域名选 AIsa 接口：
  x.com / twitter.com        -> Twitter（tweets_by_ids）
  douyin.com / v.douyin.com  -> TikHub 抖音（fetch_one_video_by_share_url）
  xiaohongshu.com / xhslink  -> TikHub 小红书（图文，失败再试视频笔记）
  youtube.com / youtu.be     -> DataForSEO YouTube 字幕 + 视频信息
  其他网页                    -> Firecrawl，失败再用 Tavily Extract

输出：{platform, url, title, author, published_at, text, stats, fetched_at, raw}
只取数据、不做总结；总结和提取交给 Bot 按岗位说明来做。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib' / 'aisa'))
import sources  # noqa: E402
from client import AisaError  # noqa: E402

TEXT_KEYS = ('full_text', 'text', 'desc', 'description', 'content', 'markdown', 'raw_content', 'subtitle', 'title')
TITLE_KEYS = ('title', 'video_title', 'note_title')
AUTHOR_KEYS = ('screen_name', 'userName', 'nickname', 'author_name', 'channel_name', 'author')
TIME_KEYS = ('createdAt', 'created_at', 'create_time', 'time', 'publish_time', 'publication_date', 'publishedAt')
STAT_KEYS = ('likeCount', 'retweetCount', 'replyCount', 'viewCount', 'digg_count', 'comment_count', 'share_count',
             'collect_count', 'play_count', 'liked_count', 'collected_count', 'views_count', 'likes_count')


def platform_of(url: str) -> str:
    h = urlparse(url).netloc.lower()
    if h.endswith(('x.com', 'twitter.com')):
        return 'x'
    if 'douyin.com' in h or 'iesdouyin.com' in h:
        return 'douyin'
    if 'xiaohongshu.com' in h or 'xhslink' in h:
        return 'xiaohongshu'
    if 'youtube.com' in h or h == 'youtu.be':
        return 'youtube'
    return 'web'


def youtube_id(url: str) -> str | None:
    u = urlparse(url)
    if u.netloc == 'youtu.be':
        return u.path.strip('/').split('/')[0] or None
    if u.path.startswith(('/shorts/', '/live/')):
        return u.path.split('/')[2]
    return (parse_qs(u.query).get('v') or [None])[0]


def walk(obj):
    """深度遍历 JSON，产出 (key, value)。各家返回结构不同，用它按字段名兜底取值。"""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                yield k, v
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)


def first(obj, keys, kind=str):
    for k, v in walk(obj):
        if k in keys and isinstance(v, kind) and v not in ('', None):
            return v
    return None


def longest_text(obj) -> str:
    best = ''
    for k, v in walk(obj):
        if k in TEXT_KEYS and isinstance(v, str) and len(v) > len(best):
            best = v
    return best


def subtitles_text(res) -> str:
    """把 DataForSEO 字幕条目拼成正文。"""
    parts = [v for k, v in walk(res) if k == 'text' and isinstance(v, str)]
    parts.reverse()  # walk 是栈，顺序相反
    return '\n'.join(parts)


def fetch(url: str) -> dict:
    p = platform_of(url)
    raw, text = {}, ''
    if p == 'x':
        m = re.search(r'/status(?:es)?/(\d+)', url)
        if not m:
            raise AisaError('没认出推文 ID，请发单条推文的链接')
        raw = sources.tweets_by_ids(m.group(1))
        text = first(raw, ('text', 'full_text')) or ''
    elif p == 'douyin':
        raw = sources.douyin_video(url)
        text = first(raw, ('desc', 'caption')) or ''
    elif p == 'xiaohongshu':
        try:
            raw = sources.xhs_note(url)
        except AisaError:
            raw = sources.xhs_note(url, video=True)
        text = longest_text(raw)
    elif p == 'youtube':
        vid = youtube_id(url)
        if not vid:
            raise AisaError('没认出 YouTube 视频 ID')
        info = sources.youtube_video_info(vid)
        try:
            subs = sources.youtube_subtitles(vid)
            text = subtitles_text(subs)
        except AisaError as e:
            subs = {'error': str(e)}
        raw = {'info': info, 'subtitles': subs}
        text = text or longest_text(info)
    else:
        try:
            raw = sources.web_page(url)
        except AisaError:
            raw = sources.web_extract(url)
        text = first(raw, ('markdown', 'raw_content')) or longest_text(raw)

    stats = {}
    for k, v in walk(raw):
        if k in STAT_KEYS and isinstance(v, (int, float)) and k not in stats:
            stats[k] = v
    return {
        'platform': p,
        'url': url,
        'title': first(raw, TITLE_KEYS),
        'author': first(raw, AUTHOR_KEYS),
        'published_at': first(raw, TIME_KEYS) or first(raw, TIME_KEYS, int),
        'text': text,
        'text_chars': len(text),
        'stats': stats,
        'fetched_at': dt.datetime.now().astimezone().isoformat(timespec='seconds'),
        'raw': raw,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('url')
    ap.add_argument('--out', default=os.environ.get('KB_HOME', '.') + '/inbox', help='素材保存目录')
    ap.add_argument('--no-raw', action='store_true', help='输出里不带原始返回')
    a = ap.parse_args()
    try:
        item = fetch(a.url)
    except AisaError as e:
        print(json.dumps({'ok': False, 'url': a.url, 'error': str(e)}, ensure_ascii=False))
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"{dt.date.today():%Y%m%d}-{item['platform']}-{hashlib.sha1(a.url.encode()).hexdigest()[:8]}.json"
    (out / name).write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding='utf-8')
    if a.no_raw:
        item.pop('raw', None)
    else:
        item['raw'] = f'（已存到 {out / name}）'
    item.update(ok=True, saved_to=str(out / name))
    print(json.dumps(item, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
