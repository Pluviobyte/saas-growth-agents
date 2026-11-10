#!/usr/bin/env python3
"""运行日志（可选模块）：每次例程跑了没有、成没成、花了多少，审批记录，规则变更。

  python3 runlog.py wrap <例程名> -- <命令...>      # 脚本型例程：包一层，自动记开始/结束/退出码/花费
  python3 runlog.py start <例程名>                  # Agent 自己动手的例程：开工时记一行，打印 run_id
  python3 runlog.py end <run_id> --status ok|partial|fail|skipped [--outputs N] [--pushed]
                        [--sources "x=ok,web=fail:timeout"] [--error "..."] [--note "..."]
  python3 runlog.py approve --kind spend|send|delete|other --ask "..." --answer "..." [--run <run_id>]
  python3 runlog.py rule --what "..." --why "..." [--where "技能名"] [--before "..."]
  python3 runlog.py check [--days 1] [--expect 早报,晚报]  # 体检：失败、卡住、漏跑、花费异常；没问题只输出一行
  python3 runlog.py prune [--keep-days 90]          # 过期的运行日志按月压缩进 archive/

目录：RUNLOG_HOME（默认 ./logs）。
  runs.jsonl          每次运行两行：开始一行 status=running，结束一行最终状态
  approvals.jsonl     审批记录，永久保留
  rules-changelog.md  规则变更，永久保留
  archive/            prune 压缩出去的旧记录
花费：读 AISA_CALL_LOG（默认 RUNLOG_HOME/aisa-calls.log）里这次运行起止时间之间的调用。
写入前统一打码：Key、Token、Cookie、密码之类一律换成 ***。只用标准库。
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get('RUNLOG_HOME', 'logs'))
RUNS = HOME / 'runs.jsonl'
APPROVALS = HOME / 'approvals.jsonl'
RULES = HOME / 'rules-changelog.md'
ARCHIVE = HOME / 'archive'
STATUSES = ('ok', 'partial', 'fail', 'skipped')

SECRET_PATTERNS = [
    (re.compile(r'(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}'), r'\1***'),
    (re.compile(r'(?i)\b((?:api[_-]?key|access[_-]?token|token|secret|password|passwd|cookie|authorization|session(?:id)?)'
                r'["\']?\s*[:=]\s*["\']?)[^\s"\'&,;]+'), r'\1***'),
    (re.compile(r'\bsk-[A-Za-z0-9_-]{8,}'), '***'),
    (re.compile(r'\b[A-Za-z0-9_-]{40,}\b'), '***'),
]


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _env_secrets() -> list[str]:
    return [v for k, v in os.environ.items()
            if re.search(r'KEY|SECRET|TOKEN|PASSWORD|COOKIE', k, re.I) and len(v) >= 8]


def redact(x):
    if isinstance(x, str):
        for v in _env_secrets():
            x = x.replace(v, '***')
        for pat, rep in SECRET_PATTERNS:
            x = pat.sub(rep, x)
        return x
    if isinstance(x, dict):
        return {k: redact(v) for k, v in x.items()}
    if isinstance(x, list):
        return [redact(v) for v in x]
    return x


def _append(path: Path, rec: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(redact(rec), ensure_ascii=False) + '\n')


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _ts(s: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.astimezone()


def call_log() -> Path:
    return Path(os.environ.get('AISA_CALL_LOG') or HOME / 'aisa-calls.log')


def aisa_cost(start: dt.datetime, end: dt.datetime) -> tuple[int, float]:
    """AISA_CALL_LOG 里 [start, end] 之间的调用次数和花费（美元）。同时段有别的例程在跑会算在一起。"""
    f = call_log()
    if not f.exists():
        return 0, 0.0
    n, cost = 0, 0.0
    for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
        parts = line.split('\t')
        if len(parts) < 4:
            continue
        try:
            t = dt.datetime.strptime(parts[0], '%Y-%m-%d %H:%M:%S').astimezone()
            c = float(parts[3])
        except ValueError:
            continue
        if start.replace(microsecond=0) <= t <= end:
            n += 1
            cost += c
    return n, round(cost, 6)


def _sources(s: str | None):
    """'x=ok,web=fail:timeout' 或 JSON 对象。"""
    if not s:
        return None
    try:
        j = json.loads(s)
        if isinstance(j, dict):
            return j
    except json.JSONDecodeError:
        pass
    out = {}
    for item in s.split(','):
        if '=' in item:
            k, v = item.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def start(routine: str) -> dict:
    t = now()
    rec = {'run_id': f'r{t:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}', 'routine': routine,
           'status': 'running', 'start': t.isoformat(timespec='seconds')}
    _append(RUNS, rec)
    return rec


def _find_start(run_id: str) -> dict | None:
    for r in _read(RUNS):
        if r.get('run_id') == run_id and r.get('status') == 'running':
            return r
    return None


def end(run_id: str, status: str, outputs=None, pushed=False, sources=None, error=None, note=None) -> dict:
    s = _find_start(run_id)
    if not s:
        raise SystemExit(f'找不到 {run_id} 的开始记录（先用 start 或 wrap）')
    t = now()
    t0 = _ts(s['start'])
    calls, cost = aisa_cost(t0, t)
    rec = {'run_id': run_id, 'routine': s['routine'], 'status': status, 'start': s['start'],
           'end': t.isoformat(timespec='seconds'), 'secs': round((t - t0).total_seconds()),
           'aisa_calls': calls, 'cost_usd': cost, 'outputs': outputs, 'pushed': bool(pushed)}
    if sources:
        rec['sources'] = sources
    if error:
        rec['error'] = error[-600:]
    if note:
        rec['note'] = note[-300:]
    _append(RUNS, rec)
    return rec


def wrap(routine: str, cmd: list[str]) -> int:
    os.environ.setdefault('AISA_CALL_LOG', str(call_log().resolve()))
    HOME.mkdir(parents=True, exist_ok=True)
    rec = start(routine)
    tail = collections.deque(maxlen=12)
    try:
        p = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, errors='replace')
        for line in p.stderr:
            sys.stderr.write(line)
            tail.append(line.rstrip())
        rc = p.wait()
    except OSError as e:
        rc, tail = 127, [f'启动失败：{e}']
    end(rec['run_id'], 'ok' if rc == 0 else 'fail',
        error=None if rc == 0 else f'exit {rc}: ' + ' | '.join(tail))
    return rc


def runs_merged() -> list[dict]:
    """每个 run_id 取最后一条；没有结束记录的保持 running。"""
    last: dict[str, dict] = {}
    for r in _read(RUNS):
        if 'run_id' in r:
            last[r['run_id']] = r
    return sorted(last.values(), key=lambda r: r.get('start', ''))


def check(days: float = 1, expect: list[str] | None = None, stuck_h: float = 2, spike: float = 1.5) -> list[str]:
    t = now()
    since = t - dt.timedelta(days=days)
    runs = runs_merged()
    recent = [r for r in runs if _ts(r['start']) >= since]
    issues = []

    for r in recent:
        if r['status'] == 'running' and t - _ts(r['start']) > dt.timedelta(hours=stuck_h):
            issues.append(f"卡住：{r['routine']} {r['start'][5:16]} 开始，超过 {stuck_h:g} 小时没有结束记录")
        elif r['status'] in ('fail', 'partial'):
            word = '失败' if r['status'] == 'fail' else '部分失败'
            issues.append(f"{word}：{r['routine']} {r['start'][5:16]}  {r.get('error') or r.get('sources') or ''}".rstrip())

    by_routine = collections.defaultdict(list)
    for r in runs:
        if r['status'] != 'running':
            by_routine[r['routine']].append(r['status'])
    for name, sts in by_routine.items():
        if len(sts) >= 2 and sts[-1] == sts[-2] == 'fail':
            issues.append(f'连续失败：{name} 最近两次都失败')

    for name in expect or []:
        if not any(r['routine'] == name for r in recent):
            issues.append(f'漏跑：{name} 在最近 {days:g} 天没有运行记录')

    cost_now = sum(r.get('cost_usd') or 0 for r in recent)
    base = [r for r in runs if since - dt.timedelta(days=7) <= _ts(r['start']) < since]
    if base:
        avg = sum(r.get('cost_usd') or 0 for r in base) / 7 * days
        if cost_now > max(avg * spike, 0.05):
            issues.append(f'花费异常：最近 {days:g} 天 ${cost_now:.2f}，前 7 天同期平均 ${avg:.2f}')
    return issues


def prune(keep_days: int = 90) -> dict:
    cutoff = now() - dt.timedelta(days=keep_days)
    moved = {'runs': 0, 'calls': 0}
    if RUNS.exists():
        keep, old = [], collections.defaultdict(list)
        for line in RUNS.read_text(encoding='utf-8').splitlines():
            try:
                t = _ts(json.loads(line)['start'])
            except (json.JSONDecodeError, KeyError, ValueError):
                keep.append(line)
                continue
            (old[f'{t:%Y-%m}'] if t < cutoff else keep).append(line)
        for month, lines in old.items():
            ARCHIVE.mkdir(parents=True, exist_ok=True)
            with gzip.open(ARCHIVE / f'runs-{month}.jsonl.gz', 'at', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            moved['runs'] += len(lines)
        RUNS.write_text(''.join(l + '\n' for l in keep), encoding='utf-8')
    cl = call_log()
    if cl.exists() and cl.resolve().parent == HOME.resolve():
        keep, old = [], collections.defaultdict(list)
        for line in cl.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                t = dt.datetime.strptime(line.split('\t', 1)[0], '%Y-%m-%d %H:%M:%S').astimezone()
            except ValueError:
                keep.append(line)
                continue
            (old[f'{t:%Y-%m}'] if t < cutoff else keep).append(line)
        for month, lines in old.items():
            ARCHIVE.mkdir(parents=True, exist_ok=True)
            with gzip.open(ARCHIVE / f'aisa-calls-{month}.log.gz', 'at', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            moved['calls'] += len(lines)
        cl.write_text(''.join(l + '\n' for l in keep), encoding='utf-8')
    return moved


def approve(kind: str, ask: str, answer: str, run_id: str | None = None) -> dict:
    rec = {'ts': now().isoformat(timespec='seconds'), 'kind': kind, 'ask': ask, 'answer': answer}
    if run_id:
        rec['run_id'] = run_id
    _append(APPROVALS, rec)
    return rec


def rule(what: str, why: str, where: str | None = None, before: str | None = None) -> str:
    HOME.mkdir(parents=True, exist_ok=True)
    head = f"## {now():%Y-%m-%d %H:%M}" + (f' · {redact(where)}' if where else '')
    lines = [head, f'- 改了什么：{redact(what)}', f'- 原因：{redact(why)}']
    if before:
        lines.append('- 改之前：\n\n```text\n' + redact(before) + '\n```')
    new = not RULES.exists()
    with open(RULES, 'a', encoding='utf-8') as f:
        if new:
            f.write('# 规则变更记录\n\n每次按用户的纠正改技能、例程或长期指令，都在这里记一条。\n\n')
        f.write('\n'.join(lines) + '\n\n')
    return head


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='运行日志（可选模块）')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('wrap'); p.add_argument('routine'); p.add_argument('command', nargs=argparse.REMAINDER)
    p = sub.add_parser('start'); p.add_argument('routine')
    p = sub.add_parser('end'); p.add_argument('run_id'); p.add_argument('--status', required=True, choices=STATUSES)
    p.add_argument('--outputs', type=int); p.add_argument('--pushed', action='store_true')
    p.add_argument('--sources'); p.add_argument('--error'); p.add_argument('--note')
    p = sub.add_parser('approve'); p.add_argument('--kind', required=True, choices=('spend', 'send', 'delete', 'other'))
    p.add_argument('--ask', required=True); p.add_argument('--answer', required=True); p.add_argument('--run')
    p = sub.add_parser('rule'); p.add_argument('--what', required=True); p.add_argument('--why', required=True)
    p.add_argument('--where'); p.add_argument('--before')
    p = sub.add_parser('check'); p.add_argument('--days', type=float, default=1)
    p.add_argument('--expect', default=''); p.add_argument('--stuck-h', type=float, default=2)
    p.add_argument('--json', action='store_true')
    p = sub.add_parser('prune'); p.add_argument('--keep-days', type=int, default=90)
    a = ap.parse_args(argv)

    if a.cmd == 'wrap':
        cmd = a.command[1:] if a.command[:1] == ['--'] else a.command
        if not cmd:
            ap.error('wrap 后面要跟 -- <命令>')
        return wrap(a.routine, cmd)
    if a.cmd == 'start':
        print(start(a.routine)['run_id'])
    elif a.cmd == 'end':
        r = end(a.run_id, a.status, a.outputs, a.pushed, _sources(a.sources), a.error, a.note)
        print(json.dumps({k: r[k] for k in ('run_id', 'status', 'secs', 'cost_usd')}, ensure_ascii=False))
    elif a.cmd == 'approve':
        approve(a.kind, a.ask, a.answer, a.run)
        print('ok')
    elif a.cmd == 'rule':
        print(rule(a.what, a.why, a.where, a.before))
    elif a.cmd == 'check':
        issues = check(a.days, [x.strip() for x in a.expect.split(',') if x.strip()], a.stuck_h)
        if a.json:
            print(json.dumps({'ok': not issues, 'issues': issues}, ensure_ascii=False))
        else:
            print('\n'.join(issues) if issues else f'最近 {a.days:g} 天运行正常')
    elif a.cmd == 'prune':
        print(json.dumps(prune(a.keep_days), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
