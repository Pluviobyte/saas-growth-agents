"""生成 README 用的动态数据流图：assets/flow-{light,dark}.svg（英文）和 .zh-CN.svg（中文）

用法：
    pip install fonttools uharfbuzz
    FONTS_DIR=<放 Inter.ttf / NotoSansSC.ttf / JetBrainsMono.ttf 的目录> python3 assets/src/make_flow_svg.py assets

文字全部转成路径（GitHub 的 raw 图片不让加载字体），动画用 SMIL，<img> 里也能播。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import re

from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path

from textpath import Typesetter

HERE = Path(__file__).parent
AISA = (HERE / 'aisa_icon.svgfrag').read_text()
_bp = BoundsPen(None)
for _d in re.findall(r' d="([^"]+)"', AISA):
    parse_path(_d, _bp)
AISA_BOX = _bp.bounds  # 按图形实际边界居中
W, H = 1440, 800
V = 760.0       # 主流程光流速度 px/s
STREAK = 120.0  # 光尾长度
LOOP_V = 420.0  # Agent 和你之间不停循环的光流速度

THEMES = {
    'light': dict(bg='#FAFAF9', ink='#0A0A0A', muted='#55555B', faint='#9C9CA3', hair='#E2E2E6', dot='#E7E7EA',
                  acc='#6D4AFF', c=['#0E9F6E', '#0284C7', '#D97706'], agent_fill='#0A0A0A', agent_text='#FAFAF9',
                  glow=0.10),
    'dark': dict(bg='#0B0B0D', ink='#F4F4F5', muted='#A1A1AA', faint='#6E6E78', hair='#27272C', dot='#1A1A1F',
                 acc='#9B8CFF', c=['#34D399', '#38BDF8', '#FBBF24'], agent_fill='#F4F4F5', agent_text='#0B0B0D',
                 glow=0.16),
}

SOURCES = ['X / Twitter', '抖音 · 小红书 · TikTok', 'YouTube 字幕', '网页 · 公众号',
           'Google SERP · Trends', 'Ahrefs 外链 · DR', 'Product Hunt · GitHub', '竞品 sitemap']
ROWS = [('新词监控', 'newterm', ['采集', '去重', 'Trends 打分']),
        ('出海站点运营', 'site-ops', ['搜词找站', '指标快照', '记台账']),
        ('社媒分析', 'social-kb', ['取原文', '查重', '入知识库'])]
FILES = ['pushed.json', 'sites.csv', 'metrics.jsonl', 'kb/*.md', 'ledger.jsonl']

CY = 485
AX, AR = 470, 64          # AIsa
TX0, TX1 = 620, 1010      # 流水线轨道
STAGES = [690, 815, 940]
RY = [345, 485, 625]
GX, GR = 1150, 58         # Agent
YX, YR = 1340, 44         # 你
STATE_Y = 716


def cubic(p0, p1, p2, p3):
    def pt(t):
        u = 1 - t
        return (u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1])
    pts = [pt(i / 200) for i in range(201)]
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(200))
    d = f'M{p0[0]},{p0[1]} C{p1[0]},{p1[1]} {p2[0]},{p2[1]} {p3[0]},{p3[1]}'
    return d, length


def line(p0, p1):
    return f'M{p0[0]},{p0[1]} L{p1[0]},{p1[1]}', math.dist(p0, p1)


class Anim:
    """所有动画共用一个周期，先排时间线，最后统一换算 keyTimes。"""

    def __init__(self):
        self.items = []  # 延迟到知道周期 T 后再输出
        self.loops, self.loop_pulses = [], []

    def streak(self, d, length, color, ts, s=STREAK, width=2.4):
        travel = length + s + 8
        self.items.append(('streak', d, length, color, ts, ts + travel / V, s, width))
        return ts + (length + 4) / V  # 光头到达终点的时刻

    def pulse(self, cx, cy, r, color, ts, grow=24, dur=1.0, width=1.5):
        self.items.append(('pulse', cx, cy, r, color, ts, dur, grow, width))

    def flash(self, cx, cy, r, color, ts, dur=1.4):
        self.items.append(('flash', cx, cy, r, color, ts, dur))

    def loop(self, segs, v=LOOP_V, s=70.0, width=2.4):
        """不停循环的光流：segs = [(d, 长度, 颜色, 段后空白)]，光头依次走完各段再回到起点。
        返回 (周期, 各段起点时刻)。"""
        total = sum(L + gap for _, L, _, gap in segs)
        period = total / v
        starts, acc = [], 0.0
        for d, L, color, gap in segs:
            starts.append(acc / v)
            self.loops.append((d, L, color, acc / v, period, total, s, width))
            acc += L + gap
        return period, starts

    def loop_pulse(self, cx, cy, r, color, period, phase, grow=18, width=1.2):
        self.loop_pulses.append((cx, cy, r, color, period, phase % period, grow, width))

    def render(self, T):
        def kt(*ts):
            return ';'.join(f'{min(max(t / T, 0), 1):.4f}' for t in ts)
        out, over = [], []
        for it in self.items:
            kind = it[0]
            if kind == 'streak':
                _, d, L, color, t0, t1, s, w = it
                for frac, op, ww in ((1.0, 0.16, w), (0.5, 0.42, w), (0.16, 1.0, w + 0.8)):
                    sk = s * frac
                    o0, o1 = sk + 4, sk - (L + s + 4)
                    out.append(
                        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{ww}" stroke-linecap="round" '
                        f'stroke-opacity="{op}" stroke-dasharray="{sk:.1f} {L + s + 40:.1f}" stroke-dashoffset="{o0:.1f}">'
                        f'<animate attributeName="stroke-dashoffset" dur="{T:.2f}s" repeatCount="indefinite" '
                        f'keyTimes="{kt(0, t0, t1, T)}" values="{o0:.1f};{o0:.1f};{o1:.1f};{o1:.1f}"/></path>')
            elif kind == 'pulse':
                _, cx, cy, r, color, t0, dur, grow, w = it
                t1 = t0 + dur
                out.append(
                    f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" opacity="0">'
                    f'<animate attributeName="r" dur="{T:.2f}s" repeatCount="indefinite" keyTimes="{kt(0, t0, t1, T)}" '
                    f'values="{r};{r};{r + grow};{r + grow}" calcMode="spline" keySplines="0 0 1 1;.2 .7 .3 1;0 0 1 1"/>'
                    f'<animate attributeName="opacity" dur="{T:.2f}s" repeatCount="indefinite" '
                    f'keyTimes="{kt(0, t0, t0 + 0.05, t1, T)}" values="0;0;.7;0;0"/></circle>')
            elif kind == 'flash':
                _, cx, cy, r, color, t0, dur = it
                over.append(
                    f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" opacity="0">'
                    f'<animate attributeName="opacity" dur="{T:.2f}s" repeatCount="indefinite" '
                    f'keyTimes="{kt(0, t0, t0 + 0.08, t0 + dur, T)}" values="0;0;1;0;0"/></circle>')
        for d, L, color, begin, period, total, s, w in self.loops:
            for frac, op, ww in ((1.0, 0.16, w), (0.5, 0.42, w), (0.16, 1.0, w + 0.8)):
                sk = s * frac
                o0 = sk + 4
                out.append(
                    f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{ww}" stroke-linecap="round" '
                    f'stroke-opacity="{op}" stroke-dasharray="{sk:.1f} {total + s + 40:.1f}" stroke-dashoffset="{o0:.1f}">'
                    f'<animate attributeName="stroke-dashoffset" begin="{begin:.3f}s" dur="{period:.3f}s" '
                    f'repeatCount="indefinite" from="{o0:.1f}" to="{o0 - total:.1f}"/></path>')
        for cx, cy, r, color, period, phase, grow, w in self.loop_pulses:
            out.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" opacity="0">'
                f'<animate attributeName="r" begin="{phase:.3f}s" dur="{period:.3f}s" repeatCount="indefinite" '
                f'keyTimes="0;.55;1" values="{r};{r + grow};{r + grow}" calcMode="spline" keySplines=".2 .7 .3 1;0 0 1 1"/>'
                f'<animate attributeName="opacity" begin="{phase:.3f}s" dur="{period:.3f}s" repeatCount="indefinite" '
                f'keyTimes="0;.55;1" values=".7;0;0"/></circle>')
        return ''.join(out), ''.join(over)


EN = {'脚本做确定的事，Agent 做判断，你做决定': 'Scripts fetch. Agents judge. You decide.',
      '把每天重复的增长活固化成 SOP：数据统一走 AIsa，例程定时触发，状态写进文件和账本。': 'Daily growth chores become SOPs: all data through AIsa, routines on a schedule, state kept in files and ledgers.',
      '01  数据源': '01  SOURCES',
      '02  统一入口': '02  ONE GATEWAY',
      '03  脚本 · 确定的事': '03  SCRIPTS · DETERMINISTIC',
      '04  Agent · 判断': '04  AGENT',
      '05  你 · 决定': '05  YOU',
      '抖音 · 小红书 · TikTok': 'Douyin · RedNote · TikTok',
      'YouTube 字幕': 'YouTube transcripts',
      '网页 · 公众号': 'Web · WeChat posts',
      'Ahrefs 外链 · DR': 'Ahrefs backlinks · DR',
      '竞品 sitemap': 'Competitor sitemaps',
      '一个 Key · 6000+ API': 'One key · 6000+ APIs',
      '按次计费 · 最高价保护': 'Pay per call · price cap',
      '新词监控': 'New-term radar',
      '出海站点运营': 'Site ops',
      '社媒分析': 'Social analysis',
      '采集': 'Collect',
      '去重': 'Dedupe',
      'Trends 打分': 'Trends score',
      '搜词找站': 'Find sites',
      '指标快照': 'Metrics',
      '记台账': 'Log it',
      '取原文': 'Fetch',
      '查重': 'Dedupe',
      '入知识库': 'Save to KB',
      '分析 · 提取 · 核实 · 写播报': 'Analyze · verify · report',
      '推送': 'push',
      '你的反馈 → 新规矩': 'your feedback → new rules',
      '你': 'You',
      '看结论 · 做决定': 'Read · decide',
      '花钱、发送、删除': 'Spend · send · delete',
      '都要你点头': 'needs your OK',
      '文件和账本，每次开工先读': 'files & ledgers, read before every run'}


def build(theme: str, lang: str = 'en') -> str:
    t = THEMES[theme]
    ts = Typesetter()
    an = Anim()
    base, top = [], []   # base：静态线和文字；top：节点（盖住动画线头）
    a, b = base.append, top.append

    def tx(x, y, s, size, wght=400, fill=None, anchor='start', mono=False, tracking=0.0, layer=None):
        if lang == 'en':
            s = EN.get(s, s)
        g, w = ts.text(x, y, s, size, wght, fill or t['ink'], anchor, mono, tracking)
        (layer or a)(g)
        return w

    # 标题区
    tx(96, 84, 'HOW IT WORKS', 15, 500, t['acc'], mono=True, tracking=3.2)
    tx(96, 136, '脚本做确定的事，Agent 做判断，你做决定', 40, 700)
    tx(96, 176, '把每天重复的增长活固化成 SOP：数据统一走 AIsa，例程定时触发，状态写进文件和账本。', 19, 400, t['muted'])

    # 栏目标签
    for x, s, anc in ((96, '01  数据源', 'start'), (AX, '02  统一入口', 'middle'), (TX0, '03  脚本 · 确定的事', 'start'),
                      (GX, '04  Agent · 判断', 'middle'), (YX, '05  你 · 决定', 'middle')):
        tx(x, 262, s, 14, 500, t['faint'], anc, mono=True, tracking=1.2)

    # 1. 数据源 → AIsa
    arrive_a = []
    for i, name in enumerate(SOURCES):
        y = 310 + 50 * i
        tx(300, y + 7, name, 19, 450, t['muted'], 'end')
        a(f'<circle cx="318" cy="{y}" r="3" fill="{t["faint"]}"/>')
        d, L = cubic((326, y), (378, y), (372, CY), (AX - AR - 2, CY))
        a(f'<path d="{d}" fill="none" stroke="{t["hair"]}" stroke-width="1.2"/>')
        start = 0.1 + ((i * 5) % 8) * 0.045
        arrive_a.append(an.streak(d, L, t['acc'], start))
    t_a = max(arrive_a)
    an.pulse(AX, CY, AR, t['acc'], t_a - 0.05, grow=26, dur=0.8)

    # 2. AIsa 节点
    b(f'<circle cx="{AX}" cy="{CY}" r="{AR}" fill="{t["bg"]}" stroke="{t["hair"]}" stroke-width="1.5"/>')
    b(f'<circle cx="{AX}" cy="{CY}" r="{AR - 8}" fill="none" stroke="{t["hair"]}" stroke-width="1" stroke-dasharray="2 5"/>')
    x0, y0, x1, y1 = AISA_BOX
    ih = 40
    iw = ih * (x1 - x0) / (y1 - y0)
    b(f'<svg x="{AX - iw / 2:.1f}" y="{CY - 44}" width="{iw:.1f}" height="{ih}" '
      f'viewBox="{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}">{AISA}</svg>')
    tx(AX, CY + 32, 'AIsa', 20, 650, anchor='middle', layer=b)
    tx(AX, CY + AR + 34, '一个 Key · 6000+ API', 16, 450, t['muted'], 'middle')
    tx(AX, CY + AR + 58, '按次计费 · 最高价保护', 16, 400, t['faint'], 'middle')

    # 3. 三条流水线
    arrive_g = []
    for r, ((name, slug, stages), ry, col) in enumerate(zip(ROWS, RY, t['c'])):
        d, L = cubic((AX + AR + 2, CY), (578, CY), (572, ry), (TX0, ry))
        a(f'<path d="{d}" fill="none" stroke="{t["hair"]}" stroke-width="1.2"/>')
        t_row = an.streak(d, L, col, t_a + 0.05 + r * 0.04)

        w = tx(TX0, ry - 24, name, 21, 600)
        tx(TX0 + w + 12, ry - 24, slug, 14, 400, t['faint'], mono=True)
        a(f'<rect x="{TX0}" y="{ry - 0.75}" width="{TX1 - TX0}" height="1.5" rx=".75" fill="{t["hair"]}"/>')
        d, L = line((TX0, ry), (TX1, ry))
        t_end = an.streak(d, L, col, t_row, width=2.6)
        for x, label in zip(STAGES, stages):
            b(f'<circle cx="{x}" cy="{ry}" r="6" fill="{t["bg"]}" stroke="{col}" stroke-width="1.6"/>')
            hit = t_row + (x - TX0 + 4) / V
            an.flash(x, ry, 3.6, col, hit, dur=0.9)
            an.pulse(x, ry, 6, col, hit, grow=10, dur=0.6, width=1.2)
            tx(x, ry + 32, label, 16, 450, t['muted'], 'middle')

        d, L = cubic((TX1, ry), (1062, ry), (1056, CY), (GX - GR - 2, CY))
        a(f'<path d="{d}" fill="none" stroke="{t["hair"]}" stroke-width="1.2"/>')
        arrive_g.append(an.streak(d, L, col, t_end - 0.02))

        if r == 2:  # 流水线写状态
            d, L = line((STAGES[2], ry + 46), (STAGES[2], STATE_Y - 6))
            a(f'<path d="{d}" fill="none" stroke="{t["faint"]}" stroke-width="1" stroke-dasharray="2 4"/>')
            an.streak(d, L, col, t_row + (STAGES[2] - TX0) / V + 0.2, s=26, width=2)
    t_g = max(arrive_g)

    # 4. Agent
    a(f'<circle cx="{GX}" cy="{CY}" r="150" fill="url(#glow)"/>')
    an.pulse(GX, CY, GR, t['acc'], t_g - 0.05, grow=30, dur=0.9, width=1.6)
    an.pulse(GX, CY, GR, t['acc'], t_g + 0.25, grow=30, dur=0.8, width=1.2)
    b(f'<circle cx="{GX}" cy="{CY}" r="{GR}" fill="{t["agent_fill"]}"/>')
    tx(GX, CY + 8, 'Agent', 22, 600, t['agent_text'], 'middle', layer=b)
    tx(GX, CY + GR + 34, '分析 · 提取 · 核实 · 写播报', 16, 450, t['muted'], 'middle')
    # Agent 读状态
    d, L = line((GX, STATE_Y - 6), (GX, CY + GR + 52))
    a(f'<path d="{d}" fill="none" stroke="{t["faint"]}" stroke-width="1" stroke-dasharray="2 4"/>')
    an.streak(d, L, t['acc'], t_g - 0.5, s=26, width=2)

    # 5. 你：Agent 推送 → 你 → 反馈回 Agent，不停循环
    fb = t['c'][2]
    a(f'<path d="M{GX + GR + 2},{CY} L{YX - YR - 2},{CY}" fill="none" stroke="{t["hair"]}" stroke-width="1.2"/>')
    tx((GX + GR + YX - YR) / 2, CY - 14, '推送', 14, 450, t['faint'], 'middle')
    arc, arc_len = cubic((YX, CY - YR - 4), (YX, CY - 118), (GX, CY - 118), (GX, CY - GR - 6))
    a(f'<path d="{arc}" fill="none" stroke="{t["faint"]}" stroke-width="1" stroke-dasharray="3 5"/>')
    a(f'<path d="M{GX - 5},{CY - GR - 14} L{GX},{CY - GR - 6} L{GX + 5},{CY - GR - 14}" fill="none" '
      f'stroke="{t["faint"]}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>')
    tx((GX + YX) / 2, CY - 104, '你的反馈 → 新规矩', 14, 450, t['faint'], 'middle')
    # 两段都穿过节点中心（被节点盖住），光头看起来是钻进节点再钻出来
    push = f'M{GX},{CY} L{YX},{CY}'
    back = f'M{YX},{CY} L{YX},{CY - YR - 4} ' + arc[arc.index('C'):] + f' L{GX},{CY}'
    back_len = YR + 4 + arc_len + GR + 6
    period, (p0, p1) = an.loop([(push, YX - GX, t['acc'], 0), (back, back_len, fb, 0)])
    an.loop_pulse(YX, CY, YR, t['ink'], period, p0 + (YX - YR - GX) / LOOP_V)
    an.loop_pulse(GX, CY, GR, fb, period, p1 + (back_len - GR) / LOOP_V)

    b(f'<circle cx="{YX}" cy="{CY}" r="{YR}" fill="{t["bg"]}" stroke="{t["ink"]}" stroke-width="1.6"/>')
    tx(YX, CY + 10, '你', 28, 700, anchor='middle', layer=b)
    tx(YX, CY + YR + 34, '看结论 · 做决定', 16, 450, t['muted'], 'middle')
    tx(YX, CY + YR + 58, '花钱、发送、删除', 15, 400, t['faint'], 'middle')
    tx(YX, CY + YR + 80, '都要你点头', 15, 400, t['faint'], 'middle')

    # 状态层
    a(f'<rect x="96" y="{STATE_Y - 0.5}" width="{YX + YR - 96}" height="1" fill="{t["hair"]}"/>')
    w = tx(96, STATE_Y + 38, 'STATE', 14, 500, t['faint'], mono=True, tracking=2.4)
    tx(96 + w + 16, STATE_Y + 38, '文件和账本，每次开工先读', 16, 450, t['muted'])
    x = TX0
    for f in FILES:
        x += tx(x, STATE_Y + 38, f, 15, 450, t['ink'], mono=True) + 30

    T = round(t_g + 1.1, 2)
    anim, over = an.render(T)

    dots = (f'<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
            f'<circle cx="1" cy="1" r="1" fill="{t["dot"]}"/></pattern>')
    glow = (f'<radialGradient id="glow"><stop offset="0" stop-color="{t["acc"]}" stop-opacity="{t["glow"]}"/>'
            f'<stop offset="1" stop-color="{t["acc"]}" stop-opacity="0"/></radialGradient>')
    blur = ('<filter id="bloom" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.4" result="b"/>'
            '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'<defs>{ts.defs_svg()}{dots}{glow}{blur}</defs>'
            f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/><rect width="{W}" height="{H}" fill="url(#dots)"/>'
            f'{"".join(base)}<g filter="url(#bloom)">{anim}</g>{"".join(top)}{over}</svg>')


if __name__ == '__main__':
    out = Path(sys.argv[1]).resolve()
    for lang, suffix in (('en', ''), ('zh', '.zh-CN')):  # 英文是默认，中文版给 README.zh-CN.md 用
        for name in THEMES:
            p = out / f'flow-{name}{suffix}.svg'
            p.write_text(build(name, lang))
            print(p, f'{p.stat().st_size / 1024:.0f} KB')
