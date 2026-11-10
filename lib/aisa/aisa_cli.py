#!/usr/bin/env python3
"""AIsa 命令行：给 Bot 和人手动试接口用。

  python3 lib/aisa/aisa_cli.py balance                       # 免费，验证 Key
  python3 lib/aisa/aisa_cli.py list                          # 列出可用的数据源函数
  python3 lib/aisa/aisa_cli.py run coin_prices ids=bitcoin   # 调一个数据源
  python3 lib/aisa/aisa_cli.py run --quote web_page url=https://example.com   # 只问价，不扣钱
  python3 lib/aisa/aisa_cli.py raw GET twitter/tweets tweet_ids=123           # 直接调任意接口

输出一律是 JSON，Key 不会出现在输出里。
"""
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import client  # noqa: E402
import sources  # noqa: E402


def kv(args):
    out = {}
    for a in args:
        if '=' not in a:
            sys.exit(f'参数要写成 key=value：{a}')
        k, v = a.split('=', 1)
        out[k] = int(v) if v.isdigit() else v
    return out


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    quote = '--quote' in rest
    rest = [a for a in rest if a != '--quote']
    if quote:
        os.environ['AISA_QUOTE'] = '1'
    try:
        if cmd == 'balance':
            res = client.balance()
        elif cmd == 'list':
            res = {n: (inspect.getdoc(f) or '').split('\n')[0] for n, f in inspect.getmembers(sources, inspect.isfunction)
                   if f.__module__ == 'sources'}
        elif cmd == 'run':
            fn = getattr(sources, rest[0], None) if rest else None
            if not callable(fn):
                sys.exit('用法：run <函数名> key=value ...（先用 list 看有哪些）')
            res = fn(**kv(rest[1:]))
        elif cmd == 'raw':
            method, path = rest[0], rest[1]
            params = kv(rest[2:])
            res = client.call(method, path, params=params if method.upper() == 'GET' else None,
                              body=params if method.upper() != 'GET' else None)
        else:
            sys.exit(f'未知命令：{cmd}')
    except client.AisaError as e:
        print(json.dumps({'error': str(e), 'status': e.status}, ensure_ascii=False))
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps({'stats': client.STATS}, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
