#!/usr/bin/env python3
"""不需要 Key 的演练测试：AISA_DRY_RUN=1，所有接口读 tests/fixtures 里的虚构样例。

  python3 tests/test_dry_run.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script, *args, home_var=None, home=None, stdin=None):
    env = dict(os.environ, AISA_DRY_RUN='1', AISA_API_KEY='', AISA_KEYS_PATH='/nonexistent')
    if home_var:
        env[home_var] = str(home)
    p = subprocess.run([sys.executable, str(ROOT / script), *args], capture_output=True, text=True,
                       env=env, cwd=home or ROOT, input=stdin)
    return p.returncode, p.stdout, p.stderr


class SocialKB(unittest.TestCase):
    def test_fetch_each_platform(self):
        with tempfile.TemporaryDirectory() as d:
            for url, platform, needle in [
                ('https://x.com/demo_user/status/1900000000000000001', 'x', 'open-source agent'),
                ('https://v.douyin.com/demo123/', 'douyin', '知识库'),
                ('https://www.xiaohongshu.com/explore/abc', 'xiaohongshu', '演示'),
                ('https://www.youtube.com/watch?v=demoVID', 'youtube', 'write the SOP'),
                ('https://example.com/post', 'web', 'fictional article'),
            ]:
                rc, out, err = run('bots/social-kb/scripts/fetch_link.py', url, '--out', d)
                self.assertEqual(rc, 0, err + out)
                j = json.loads(out)
                self.assertEqual(j['platform'], platform)
                self.assertIn(needle, j['text'])

    def test_kb_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            note = Path(d, 'n.md'); note.write_text('# 演示笔记\n\n- 要点一')
            url = 'https://twitter.com/a/status/1?s=46&t=xyz'
            self.assertEqual(run('bots/social-kb/scripts/kb.py', 'add', '--topic', 'AI 工具', '--url', url,
                                 '--file', str(note), home_var='KB_HOME', home=d)[0], 0)
            # 同一条推文换了分享参数，也要认出是重复
            self.assertEqual(run('bots/social-kb/scripts/kb.py', 'seen', 'https://x.com/a/status/1',
                                 home_var='KB_HOME', home=d)[0], 0)
            self.assertEqual(run('bots/social-kb/scripts/kb.py', 'add', '--topic', 'AI 工具', '--url',
                                 'https://x.com/a/status/1', '--file', str(note), home_var='KB_HOME', home=d)[0], 2)
            self.assertIn('## 演示笔记', Path(d, 'kb', 'AI 工具.md').read_text())


class TradeRadar(unittest.TestCase):
    def test_scan_and_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = json.loads((ROOT / 'extras/trade-radar/config.example.json').read_text())
            Path(d, 'config.json').write_text(json.dumps(cfg))
            rc, out, err = run('extras/trade-radar/scripts/scan.py', home_var='TRADE_HOME', home=d)
            self.assertEqual(rc, 0, err)
            j = json.loads(out)
            # 样例里 BTC 76800 < 77000，应触发跌破提醒；样例推文含 hack，应触发关键词
            kinds = {t['type'] for t in j['triggers']}
            self.assertIn('price_alert', kinds)
            self.assertIn('keyword', kinds)
            self.assertTrue(Path(j['materials']).exists())
            # 第二次扫描：提醒已经发过、推文已经看过，不应重复触发
            j2 = json.loads(run('extras/trade-radar/scripts/scan.py', home_var='TRADE_HOME', home=d)[1])
            self.assertFalse(j2['triggered'], j2)

            bad = json.dumps({'event': 'x', 'direction': 'down', 'invalidation': 'y', 'order_size': 1})
            self.assertNotEqual(run('extras/trade-radar/scripts/ledger.py', 'add', '--json', '-',
                                    home_var='TRADE_HOME', home=d, stdin=bad)[0], 0)
            good = json.dumps({'event': '演示事件', 'assets': ['BTC'], 'direction': 'down', 'horizon_h': 0,
                               'invalidation': '4 小时内收回 78000', 'confidence': 0.6})
            rc, out, err = run('extras/trade-radar/scripts/ledger.py', 'add', '--json', '-',
                               home_var='TRADE_HOME', home=d, stdin=good)
            self.assertEqual(rc, 0, err)
            jid = json.loads(out)['id']
            due = json.loads(run('extras/trade-radar/scripts/ledger.py', 'due', home_var='TRADE_HOME', home=d)[1])
            self.assertEqual(due['count'], 1)
            run('extras/trade-radar/scripts/ledger.py', 'resolve', jid, 'hit', home_var='TRADE_HOME', home=d)
            st = json.loads(run('extras/trade-radar/scripts/ledger.py', 'stats', home_var='TRADE_HOME', home=d)[1])
            self.assertEqual(st['hit_rate'], 1.0)


class SiteOps(unittest.TestCase):
    def test_serp_and_dr(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = run('bots/site-ops/scripts/serp_sites.py', 'demo keyword', home_var='SITEOPS_HOME', home=d)
            self.assertEqual(rc, 0, err)
            j = json.loads(out)
            self.assertEqual(j['by_keyword']['demo keyword']['new_sites'], ['demo-tool-one.example', 'demo-tool-two.example'])
            rc, out, err = run('bots/site-ops/scripts/dr_check.py', '--from-sites', '2', home_var='SITEOPS_HOME', home=d)
            self.assertEqual(rc, 0, err)
            self.assertEqual(json.loads(out)['checked'][0]['domain_rating'], 23.0)


class Cli(unittest.TestCase):
    def test_list_and_run(self):
        rc, out, _ = run('lib/aisa/aisa_cli.py', 'list')
        self.assertIn('coin_prices', json.loads(out))
        rc, out, _ = run('lib/aisa/aisa_cli.py', 'run', 'coin_prices', 'ids=bitcoin')
        self.assertEqual(json.loads(out)['bitcoin']['usd'], 76800.0)


class NewtermWatchlist(unittest.TestCase):
    """竞品 / 导航站名单只来自工作目录的 watchlist.json，仓库不带真实名单。"""
    def test_watchlist_driven(self):
        import shutil
        pipe = ROOT / 'bots' / 'newterm' / 'pipeline'
        self.assertFalse((pipe / 'watchlist.json').exists())
        with tempfile.TemporaryDirectory() as d:
            for f in ('radar_sitemaps.py', 'radar_paid_nav.py', 'radar_common.py', 'radar_oldword_newsites.py',
                      'watchlist.example.json'):
                shutil.copy(pipe / f, d)
            code = ("import json, radar_sitemaps as R, radar_paid_nav as P; print(json.dumps(dict("
                    "s=list(R.SITES), p=list(P.SITES), a=R.parse('competitor-one.example', 'https://competitor-one.example/es/cat-dance-trend'), "
                    "b=R.parse('competitor-one.example', 'https://competitor-one.example/pricing'), "
                    "c=R.parse('big-platform.example', 'https://big-platform.example/models/foo-2-5-api'))))")
            env = dict(os.environ, NEWTERM_WATCHLIST='/nonexistent')
            p = subprocess.run([sys.executable, '-c', code], cwd=d, env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            j = json.loads(p.stdout)
            self.assertEqual((j['s'], j['p']), ([], []))          # 没有名单就是空的，不回落到任何内置名单
            env['NEWTERM_WATCHLIST'] = str(Path(d, 'watchlist.example.json'))
            p = subprocess.run([sys.executable, '-c', code], cwd=d, env=env, capture_output=True, text=True)
            j = json.loads(p.stdout)
            self.assertIn('competitor-one.example', j['s'])
            self.assertEqual(j['a'], ['cat dance', 'meme', 'page'])
            self.assertIsNone(j['b'])
            self.assertEqual(j['c'], ['foo 2.5', 'ai', 'model'])


class RunLog(unittest.TestCase):
    """可选模块 lib/runlog：运行日志、审批、规则变更、体检、归档。"""
    S = 'lib/runlog/runlog.py'

    def rl(self, d, *args):
        return run(self.S, *args, home_var='RUNLOG_HOME', home=d)

    def runs(self, d):
        return [json.loads(l) for l in Path(d, 'runs.jsonl').read_text().splitlines()]

    def test_wrap_cost_and_failure(self):
        with tempfile.TemporaryDirectory() as d:
            # 子进程模拟一次花了 $0.0123 的 AIsa 调用（格式和 lib/aisa/client.py 写的一样）
            fake = ("import os,datetime as dt;open(os.environ['AISA_CALL_LOG'],'a').write("
                    "f'{dt.datetime.now():%F %T}\\tapis/v1/demo\\tslot=env\\t0.012300\\t0.1s\\thttp 200\\n')")
            rc, _, err = self.rl(d, 'wrap', '早报', '--', sys.executable, '-c', fake)
            self.assertEqual(rc, 0, err)
            r = self.runs(d)[-1]
            self.assertEqual((r['routine'], r['status'], r['aisa_calls'], r['cost_usd']), ('早报', 'ok', 1, 0.0123))

            boom = "import sys;sys.stderr.write('boom token=abcdef123456\\n');sys.exit(3)"
            for _ in range(2):
                rc, _, _ = self.rl(d, 'wrap', '晚报', '--', sys.executable, '-c', boom)
                self.assertEqual(rc, 3)
            r = self.runs(d)[-1]
            self.assertEqual(r['status'], 'fail')
            self.assertIn('exit 3', r['error'])
            self.assertIn('token=***', r['error'])
            self.assertNotIn('abcdef123456', Path(d, 'runs.jsonl').read_text())

            out = self.rl(d, 'check', '--expect', '早报,夜间采集')[1]
            self.assertIn('连续失败：晚报', out)
            self.assertIn('漏跑：夜间采集', out)
            self.assertNotIn('漏跑：早报', out)

    def test_start_end_approve_rule_prune(self):
        with tempfile.TemporaryDirectory() as d:
            rid = self.rl(d, 'start', '收链接')[1].strip()
            rc, out, err = self.rl(d, 'end', rid, '--status', 'partial', '--outputs', '1', '--pushed',
                                   '--sources', 'x=ok,web=fail:timeout')
            self.assertEqual(rc, 0, err)
            r = self.runs(d)[-1]
            self.assertEqual((r['status'], r['outputs'], r['pushed']), ('partial', 1, True))
            self.assertEqual(r['sources'], {'x': 'ok', 'web': 'fail:timeout'})
            self.assertIn('部分失败：收链接', self.rl(d, 'check')[1])
            # 没结束的运行：超过阈值算卡住
            self.rl(d, 'start', '周报')
            self.assertIn('卡住：周报', self.rl(d, 'check', '--stuck-h', '0')[1])

            self.rl(d, 'approve', '--kind', 'spend', '--ask', '查 300 个域名外链约 $3', '--answer', '同意')
            self.assertEqual(json.loads(Path(d, 'approvals.jsonl').read_text())['answer'], '同意')
            self.rl(d, 'rule', '--what', '老站不推', '--why', '推了 3 年前的站', '--before', 'password=hunter2hunter2')
            md = Path(d, 'rules-changelog.md').read_text()
            self.assertIn('老站不推', md)
            self.assertNotIn('hunter2hunter2', md)

            with open(Path(d, 'runs.jsonl'), 'a') as f:
                f.write(json.dumps({'run_id': 'old', 'routine': '早报', 'status': 'ok',
                                    'start': '2020-01-05T09:30:00+08:00'}) + '\n')
            self.assertEqual(json.loads(self.rl(d, 'prune')[1])['runs'], 1)
            self.assertTrue(Path(d, 'archive', 'runs-2020-01.jsonl.gz').exists())
            self.assertNotIn('"old"', Path(d, 'runs.jsonl').read_text())



class DouyinCommentsSkill(unittest.TestCase):
    def test_scripts_compile(self):
        sk = ROOT / 'bots' / 'social-kb' / 'douyin-comments'
        self.assertTrue((sk / 'SKILL.md').exists())
        for py in (sk / 'scripts').glob('*.py'):
            compile(py.read_text(), str(py), 'exec')


if __name__ == '__main__':
    unittest.main(verbosity=2)
