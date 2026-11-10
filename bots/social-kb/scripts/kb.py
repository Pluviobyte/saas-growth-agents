#!/usr/bin/env python3
"""社媒知识库：按主题存 Markdown，按链接去重。

  python3 kb.py seen <链接>                                    # 收过没有？exit 0=收过，1=没收过
  python3 kb.py add --topic "AI 视频" --url <链接> --file note.md   # 追加一条（note.md 由 Bot 写）
  python3 kb.py topics                                         # 现有主题和条数
  python3 kb.py week [--days 7]                                # 最近 N 天新增，周报用

目录（KB_HOME，默认当前目录）：
  kb/<主题>.md      每个主题一个文件，新条目追加在末尾
  kb/index.jsonl    一行一条：时间、主题、链接、标题；去重和周报都读它
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

HOME = Path(os.environ.get('KB_HOME', '.'))
KB = HOME / 'kb'
INDEX = KB / 'index.jsonl'
TRACKING = re.compile(r'^(utm_|spm|share_|xsec_|s$|t$|si$|feature$|ref$)')


def canon(url: str) -> str:
    """去掉分享参数，x.com/twitter.com 统一，便于去重。"""
    u = urlparse(url.strip())
    host = u.netloc.lower().replace('www.', '').replace('mobile.', '').replace('twitter.com', 'x.com')
    q = '&'.join(p for p in u.query.split('&') if p and not TRACKING.match(p.split('=')[0]))
    return urlunparse(('https', host, u.path.rstrip('/'), '', q, ''))


def entries():
    if not INDEX.exists():
        return []
    out = []
    for line in INDEX.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def safe_topic(t: str) -> str:
    t = re.sub(r'[\\/:*?"<>|\n]', ' ', t).strip()
    return t or '未分类'


def cmd_seen(a):
    c = canon(a.url)
    hit = next((e for e in entries() if e.get('url') == c), None)
    print(json.dumps({'seen': bool(hit), 'entry': hit}, ensure_ascii=False))
    return 0 if hit else 1


def cmd_add(a):
    c = canon(a.url)
    if any(e.get('url') == c for e in entries()) and not a.force:
        print(json.dumps({'ok': False, 'reason': 'duplicate', 'url': c}, ensure_ascii=False))
        return 2
    note = Path(a.file).read_text(encoding='utf-8') if a.file else sys.stdin.read()
    note = note.strip()
    if not note:
        sys.exit('笔记内容是空的')
    topic = safe_topic(a.topic)
    KB.mkdir(parents=True, exist_ok=True)
    f = KB / f'{topic}.md'
    now = dt.datetime.now().astimezone()
    title = a.title or next((l.lstrip('# ').strip() for l in note.splitlines() if l.strip()), c)[:80]
    head = '' if f.exists() else f'# {topic}\n'
    with f.open('a', encoding='utf-8') as fh:
        fh.write(f'{head}\n## {title}\n\n- 来源：{c}\n- 入库：{now:%Y-%m-%d %H:%M}\n\n{note}\n')
    rec = {'ts': now.isoformat(timespec='seconds'), 'topic': topic, 'url': c, 'title': title}
    with INDEX.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps({'ok': True, 'file': str(f), **rec}, ensure_ascii=False))
    return 0


def cmd_topics(a):
    count = {}
    for e in entries():
        count[e['topic']] = count.get(e['topic'], 0) + 1
    print(json.dumps(dict(sorted(count.items(), key=lambda x: -x[1])), ensure_ascii=False, indent=1))
    return 0


def cmd_week(a):
    since = dt.datetime.now().astimezone() - dt.timedelta(days=a.days)
    recent = [e for e in entries() if dt.datetime.fromisoformat(e['ts']) >= since]
    print(json.dumps({'since': since.isoformat(timespec='seconds'), 'count': len(recent), 'entries': recent},
                     ensure_ascii=False, indent=1))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('seen'); s.add_argument('url'); s.set_defaults(fn=cmd_seen)
    s = sub.add_parser('add'); s.add_argument('--topic', required=True); s.add_argument('--url', required=True)
    s.add_argument('--file', help='笔记文件，不填就从标准输入读'); s.add_argument('--title')
    s.add_argument('--force', action='store_true', help='重复链接也追加'); s.set_defaults(fn=cmd_add)
    s = sub.add_parser('topics'); s.set_defaults(fn=cmd_topics)
    s = sub.add_parser('week'); s.add_argument('--days', type=int, default=7); s.set_defaults(fn=cmd_week)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == '__main__':
    raise SystemExit(main())
