#!/usr/bin/env python3
"""AIsa Data API 的最小客户端，只用标准库。

- Key：优先走 aisa_keyring（AISA_KEY_A / AISA_KEY_B 轮换），没配就读环境变量 AISA_API_KEY。
- 费用：每次请求都带 X-AISA-Max-Price-USD（默认 AISA_MAX_PRICE=0.02），超价的请求 AIsa 会直接拒绝。
- 报价：quote=True 时只问价不执行（X-AISA-Cost-Mode: quote），装机验收用它，不花钱。
- 演练：AISA_DRY_RUN=1 时不发请求，从 AISA_FIXTURES 目录读样例 JSON，没有 Key 也能跑通流程。
- 日志：AISA_CALL_LOG 记录 路径 / 槽位 / 花费 / 状态码，绝不记录 Key。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ.get('AISA_BASE_URL', 'https://api.aisa.one').rstrip('/')
DATA_PREFIX = '/apis/v1/'
MAX_PRICE = os.environ.get('AISA_MAX_PRICE', '0.02')
FIXTURES = Path(os.environ.get('AISA_FIXTURES') or Path(__file__).resolve().parents[2] / 'tests' / 'fixtures')
CALL_LOG = os.environ.get('AISA_CALL_LOG', '')
STATS = dict(calls=0, ok=0, fail=0, cost=0.0)


class AisaError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


def dry_run() -> bool:
    return os.environ.get('AISA_DRY_RUN', '') not in ('', '0', 'false', 'False')


def _key() -> tuple[str, str]:
    """返回 (槽位, Key)。槽位只用于日志。"""
    try:
        import aisa_keyring
        return aisa_keyring.acquire_slot()
    except ImportError:
        pass
    except Exception as e:  # keyring 没配置时退回环境变量
        if os.environ.get('AISA_API_KEY'):
            return 'env', os.environ['AISA_API_KEY']
        raise AisaError(f'没有可用的 AIsa Key：{e}') from None
    k = os.environ.get('AISA_API_KEY')
    if not k:
        raise AisaError('没有可用的 AIsa Key：请把 AISA_API_KEY 放进保险库或 .env')
    return 'env', k


def _disable(slot: str) -> None:
    if slot == 'env':
        return
    try:
        import aisa_keyring
        aisa_keyring.disable_slot(slot, 'http_401')
    except Exception:
        pass


def _log(path: str, slot: str, cost: float, secs: float, note: str) -> None:
    STATS['calls'] += 1
    STATS['cost'] += cost
    if not CALL_LOG:
        return
    try:
        with open(CALL_LOG, 'a', encoding='utf-8') as f:
            f.write(f'{dt.datetime.now():%F %T}\t{path}\tslot={slot}\t{cost:.6f}\t{secs:.1f}s\t{note}\n')
    except OSError:
        pass


def fixture_name(path: str) -> str:
    """apis/v1/twitter/tweet/advanced_search -> twitter__tweet__advanced_search"""
    p = path.split('?', 1)[0]
    if p.startswith(DATA_PREFIX):
        p = p[len(DATA_PREFIX):]
    return p.strip('/').replace('/', '__')


def _from_fixture(path: str) -> dict:
    f = FIXTURES / (fixture_name(path) + '.json')
    if not f.exists():
        raise AisaError(f'dry-run 缺样例文件：{f}')
    return json.loads(f.read_text(encoding='utf-8'))


def call(method: str, path: str, params: dict | None = None, body=None,
         max_price: str | float | None = None, quote: bool = False, timeout: int = 90) -> dict:
    """调用一个 AIsa 接口。path 可以写完整的 /apis/v1/... ，也可以只写 twitter/tweets。

    401：停用该槽位并报错，不偷偷换 Key 重试；429：直接报错，由调用方决定等多久。"""
    if not path.startswith('/'):
        path = DATA_PREFIX + path
    quote = quote or os.environ.get('AISA_QUOTE', '') not in ('', '0', 'false', 'False')
    if dry_run():
        _log(path, 'dry', 0.0, 0.0, 'dry-run')
        STATS['ok'] += 1
        return _from_fixture(path)

    slot, secret = _key()
    url = BASE + path
    if params:
        clean = {k: ('true' if v is True else 'false' if v is False else v) for k, v in params.items() if v is not None}
        url += '?' + urllib.parse.urlencode(clean, doseq=True)
    headers = {
        'Authorization': f'Bearer {secret}',
        'Accept': 'application/json',
        'X-AISA-Max-Price-USD': str(max_price or MAX_PRICE),
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if quote:
        headers['X-AISA-Cost-Mode'] = 'quote'
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw, hdrs = r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        status, raw, hdrs = e.code, e.read(), e.headers
    except (urllib.error.URLError, TimeoutError) as e:
        _log(path, slot, 0.0, time.time() - t, f'network {type(e).__name__}')
        STATS['fail'] += 1
        raise AisaError(f'网络错误 {type(e).__name__}（{path}）') from None

    cost = int(hdrs.get('x-aisa-customer-cost-micros-usd') or 0) / 1e6
    _log(path, slot, cost, time.time() - t, f'http {status}' + (' quote' if quote else ''))
    if status == 401:
        _disable(slot)
        STATS['fail'] += 1
        raise AisaError(f'401：Key 无效或缺失（槽位 {slot} 已停用）', 401)
    if status == 402:
        STATS['fail'] += 1
        raise AisaError('402：余额不足或超过单次最高价，请检查控制台余额或调高 max_price', 402)
    if status == 429:
        STATS['fail'] += 1
        raise AisaError('429：被限速了，稍后再试', 429)
    if status >= 400:
        STATS['fail'] += 1
        raise AisaError(f'HTTP {status}（{path}）：{raw[:200].decode("utf-8", "replace")}', status)
    try:
        j = json.loads(raw or b'{}')
    except json.JSONDecodeError:
        STATS['fail'] += 1
        raise AisaError(f'返回的不是 JSON（{path}）', status) from None
    STATS['ok'] += 1
    if quote and isinstance(j, dict):
        j.setdefault('_quoted_cost_usd', cost)
    return j


def get(path: str, **params) -> dict:
    return call('GET', path, params=params)


def post(path: str, body) -> dict:
    return call('POST', path, body=body)


def balance() -> dict:
    """免费接口：查余额，同时验证 Key 能不能用。"""
    if dry_run():
        return {'available_balance_micros_usd': 0, 'dry_run': True}
    return call('GET', '/v1/credits/balance')
