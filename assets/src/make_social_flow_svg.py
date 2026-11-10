"""生成社媒分析包 README 用的动态数据流图：assets/social-flow-{light,dark}.svg（英文）和 .zh-CN.svg（中文）

用法：
    pip install fonttools uharfbuzz
    FONTS_DIR=<放 Inter.ttf / NotoSansSC.ttf / JetBrainsMono.ttf 的目录> python3 assets/src/make_social_flow_svg.py assets

文字全部转成路径（GitHub 的 raw 图片不让加载字体），动画用 SMIL，<img> 里也能播。
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path

from textpath import Typesetter

HERE = Path(__file__).parent
AISA = (HERE / 'aisa_icon.svgfrag').read_text()
_bp = BoundsPen(None)
for _d in re.findall(r' d="([^"]+)"', AISA):
    parse_path(_d, _bp)
AISA_BOX = _bp.bounds

W, H = 1440, 780
V = 760.0       # 主流程光流速度 px/s
STREAK = 120.0  # 光尾长度
LOOP_V = 420.0  # Agent 和你之间不停循环的光流速度

THEMES = {
    'light': dict(bg='#FAFAF9', ink='#0A0A0A', muted='#55555B', faint='#9C9CA3', hair='#E2E2E6', dot='#E7E7EA',
                  acc='#6D4AFF', c=['#0284C7', '#E11D48'], kb='#0E9F6E', fb='#D97706',
                  agent_fill='#0A0A0A', agent_text='#FAFAF9', glow=0.10),
    'dark': dict(bg='#0B0B0D', ink='#F4F4F5', muted='#A1A1AA', faint='#6E6E78', hair='#27272C', dot='#1A1A1F',
                 acc='#9B8CFF', c=['#38BDF8', '#FB7185'], kb='#34D399', fb='#FBBF24',
                 agent_fill='#F4F4F5', agent_text='#0B0B0D', glow=0.16),
}

LINKS = ['X / Twitter', '抖音视频', '小红书笔记', 'YouTube 字幕', '公众号 · 网页']
ROWS = [('取原文', 'fetch_link.py', ['查重', '按平台取原文', '统一成 JSON']),
        ('抖音评论区', 'douyin-comments', ['照抄页面请求', '一级 + 楼中楼', '评论全文.md'])]

AX, AY, AR = 470, 400, 64       # AIsa
BX, BY, BR = 470, 630, 46       # 浏览器
TX0, TX1 = 620, 1010
STAGES = [690, 815, 940]
RY = [AY, BY]
GX, GY, GR = 1150, 515, 58      # Agent
KX, KY, KR = 1340, 420, 42      # 知识库
YX, YY, YR = 1340, 610, 42      # 你


def cubic(p0, p1, p2, p3):
    def pt(t):
        u = 1 - t
        return (u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1])
    pts = [pt(i / 200) for i in range(201)]
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(200))
    return f'M{p0[0]},{p0[1]} C{p1[0]},{p1[1]} {p2[0]},{p2[1]} {p3[0]},{p3[1]}', length


def line(p0, p1):
    return f'M{p0[0]},{p0[1]} L{p1[0]},{p1[1]}', math.dist(p0, p1)


class Anim:
    """所有动画共用一个周期，先排时间线，最后统一换算 keyTimes。"""

    def __init__(self):
        self.items = []
        self.loops, self.loop_pulses = [], []

    def streak(self, d, length, color, ts, s=STREAK, width=2.4):
        self.items.append(('streak', d, length, color, ts, ts + (length + s + 8) / V, s, width))
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


EN = {'丢一个链接，Agent 帮你拆进知识库': 'Drop a link. The agent files it into your knowledge base.',
      '脚本取原文、查重、记账；Agent 整理并对照你的工作流提取；你只看结论，决定改不改 SOP。': 'Scripts fetch, dedupe and log. The agent summarizes and pulls out what fits your workflow. You read and decide.',
      '01  你丢的链接': '01  YOUR LINKS',
      '02  取原文': '02  FETCH',
      '03  脚本 · 确定的事': '03  SCRIPTS · DETERMINISTIC',
      '04  Agent · 判断': '04  AGENT',
      '05  沉淀': '05  KEEP',
      '抖音视频': 'Douyin videos',
      '小红书笔记': 'RedNote posts',
      'YouTube 字幕': 'YouTube transcripts',
      '公众号 · 网页': 'WeChat · web pages',
      '抖音评论区': 'Douyin comments',
      '一个 Key 取五个平台': 'One key, five platforms',
      '按次计费 · 最高价保护': 'Pay per call · price cap',
      '你自己的浏览器': 'Your own browser',
      '不花钱 · 不逆向签名': 'Free · no signature hacks',
      '取原文': 'Fetch',
      '查重': 'Dedupe',
      '按平台取原文': 'Fetch by platform',
      '统一成 JSON': 'To JSON',
      '照抄页面请求': 'Replay request',
      '一级 + 楼中楼': 'All replies',
      '整理 · 对照你的工作流': 'Summarize, compare',
      '提取能改进 SOP 的部分': 'with your workflow',
      '知识库': 'KB',
      'kb/<主题>.md': 'kb/<topic>.md',
      '按主题合并 · 不重复': 'by topic · no dupes',
      '你': 'You',
      '评论全文.md': 'Report .md',
      '一句话总结 + 建议': 'Summary + suggestions',
      '每周日一份周报': 'Weekly digest, Sundays',
      '你点头后才改技能': 'Skills change only with your OK'}


def build(theme: str, lang: str = 'en') -> str:
    t = THEMES[theme]
    ts = Typesetter()
    an = Anim()
    base, top = [], []
    a, b = base.append, top.append

    def tx(x, y, s, size, wght=400, fill=None, anchor='start', mono=False, tracking=0.0, layer=None):
        if lang == 'en':
            s = EN.get(s, s)
        g, w = ts.text(x, y, s, size, wght, fill or t['ink'], anchor, mono, tracking)
        (layer or a)(g)
        return w

    def hairpath(d, dash=None, color=None, width=1.2):
        extra = f' stroke-dasharray="{dash}"' if dash else ''
        a(f'<path d="{d}" fill="none" stroke="{color or t["hair"]}" stroke-width="{width}"{extra}/>')

    # 标题区
    tx(96, 84, 'HOW IT WORKS', 15, 500, t['acc'], mono=True, tracking=3.2)
    tx(96, 136, '丢一个链接，Agent 帮你拆进知识库', 40, 700)
    tx(96, 176, '脚本取原文、查重、记账；Agent 整理并对照你的工作流提取；你只看结论，决定改不改 SOP。', 19, 400, t['muted'])

    for x, s, anc in ((96, '01  你丢的链接', 'start'), (AX, '02  取原文', 'middle'), (TX0, '03  脚本 · 确定的事', 'start'),
                      (GX, '04  Agent · 判断', 'middle'), (KX, '05  沉淀', 'middle')):
        tx(x, 262, s, 14, 500, t['faint'], anc, mono=True, tracking=1.2)

    # 1. 链接 → AIsa / 浏览器
    arrive = []
    ys = [AY - 100 + 50 * i for i in range(5)]
    for i, (name, y) in enumerate(zip(LINKS, ys)):
        tx(300, y + 7, name, 19, 450, t['muted'], 'end')
        a(f'<circle cx="318" cy="{y}" r="3" fill="{t["faint"]}"/>')
        d, L = cubic((326, y), (378, y), (372, AY), (AX - AR - 2, AY))
        hairpath(d)
        arrive.append(an.streak(d, L, t['acc'], 0.1 + ((i * 3) % 5) * 0.05))
    t_a = max(arrive)
    an.pulse(AX, AY, AR, t['acc'], t_a - 0.05, grow=26, dur=0.8)

    tx(300, BY + 7, '抖音评论区', 19, 450, t['muted'], 'end')
    a(f'<circle cx="318" cy="{BY}" r="3" fill="{t["faint"]}"/>')
    d, L = line((326, BY), (BX - BR - 2, BY))
    hairpath(d)
    t_b = an.streak(d, L, t['c'][1], 0.3)
    an.pulse(BX, BY, BR, t['c'][1], t_b - 0.05, grow=20, dur=0.8)

    # 2. AIsa 节点
    b(f'<circle cx="{AX}" cy="{AY}" r="{AR}" fill="{t["bg"]}" stroke="{t["hair"]}" stroke-width="1.5"/>')
    b(f'<circle cx="{AX}" cy="{AY}" r="{AR - 8}" fill="none" stroke="{t["hair"]}" stroke-width="1" stroke-dasharray="2 5"/>')
    x0, y0, x1, y1 = AISA_BOX
    ih = 40
    iw = ih * (x1 - x0) / (y1 - y0)
    b(f'<svg x="{AX - iw / 2:.1f}" y="{AY - 44}" width="{iw:.1f}" height="{ih}" '
      f'viewBox="{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}">{AISA}</svg>')
    tx(AX, AY + 32, 'AIsa', 20, 650, anchor='middle', layer=b)
    tx(AX, AY + AR + 34, '一个 Key 取五个平台', 16, 450, t['muted'], 'middle')
    tx(AX, AY + AR + 58, '按次计费 · 最高价保护', 16, 400, t['faint'], 'middle')

    # 浏览器节点
    b(f'<circle cx="{BX}" cy="{BY}" r="{BR}" fill="{t["bg"]}" stroke="{t["hair"]}" stroke-width="1.5"/>')
    b(f'<rect x="{BX - 20}" y="{BY - 15}" width="40" height="30" rx="5" fill="none" stroke="{t["ink"]}" stroke-width="2"/>'
      f'<path d="M{BX - 20},{BY - 6} H{BX + 20}" stroke="{t["ink"]}" stroke-width="2"/>'
      + ''.join(f'<circle cx="{BX - 15 + 5 * k}" cy="{BY - 10.5}" r="1.4" fill="{t["ink"]}"/>' for k in range(3)))
    tx(BX, BY + BR + 32, '你自己的浏览器', 16, 450, t['muted'], 'middle')
    tx(BX, BY + BR + 56, '不花钱 · 不逆向签名', 16, 400, t['faint'], 'middle')

    # 3. 两条脚本轨道
    starts = [t_a + 0.05, t_b + 0.05]
    arrive_g = []
    for (name, slug, stages), ry, col, st, (hx, hr) in zip(ROWS, RY, t['c'], starts, ((AX, AR), (BX, BR))):
        d, L = line((hx + hr + 2, ry), (TX0, ry))
        hairpath(d)
        t_row = an.streak(d, L, col, st)
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
        d, L = cubic((TX1, ry), (1062, ry), (1056, GY), (GX - GR - 2, GY))
        hairpath(d)
        arrive_g.append(an.streak(d, L, col, t_end - 0.02))
    t_g = max(arrive_g)

    # 4. Agent
    a(f'<circle cx="{GX}" cy="{GY}" r="150" fill="url(#glow)"/>')
    an.pulse(GX, GY, GR, t['acc'], t_g - 0.05, grow=30, dur=0.9, width=1.6)
    an.pulse(GX, GY, GR, t['acc'], t_g + 0.25, grow=30, dur=0.8, width=1.2)
    b(f'<circle cx="{GX}" cy="{GY}" r="{GR}" fill="{t["agent_fill"]}"/>')
    tx(GX, GY + 8, 'Agent', 22, 600, t['agent_text'], 'middle', layer=b)
    tx(GX, GY - GR - 46, '整理 · 对照你的工作流', 16, 450, t['muted'], 'middle')
    tx(GX, GY - GR - 22, '提取能改进 SOP 的部分', 16, 450, t['muted'], 'middle')

    # 5. 知识库（每轮一次）；Agent → 你 → 反馈回 Agent 不停循环
    d, L = cubic((GX + GR + 2, GY), (1250, GY), (1250, KY), (KX - KR - 2, KY))
    hairpath(d)
    t_k = an.streak(d, L, t['kb'], t_g + 0.2, s=60, width=2.4)
    an.pulse(KX, KY, KR, t['kb'], t_k - 0.03, grow=20, dur=0.7, width=1.2)
    push_curve, push_len = cubic((GX + GR + 2, GY), (1250, GY), (1250, YY), (YX - YR - 2, YY))
    hairpath(push_curve)
    fb_curve, fb_len = cubic((YX - 10, YY + YR + 66), (YX - 40, 748), (GX, 748), (GX, GY + GR + 8))
    hairpath(fb_curve, dash='3 5', color=t['faint'], width=1)
    a(f'<path d="M{GX - 5},{GY + GR + 16} L{GX},{GY + GR + 8} L{GX + 5},{GY + GR + 16}" fill="none" '
      f'stroke="{t["faint"]}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>')
    tx(1236, 766, '你点头后才改技能', 14, 450, t['faint'], 'middle')
    # 两段都从节点中心进出（被节点盖住）；你 → 反馈线起点之间隔着说明文字，用空白段跳过
    push = f'M{GX},{GY} L{GX + GR + 2},{GY} ' + push_curve[push_curve.index('C'):] + f' L{YX},{YY}'
    push_total = GR + 2 + push_len + YR + 2
    back = fb_curve + f' L{GX},{GY}'
    back_total = fb_len + GR + 8
    period, (p0, p1) = an.loop([(push, push_total, t['acc'], YR + 66), (back, back_total, t['fb'], 0)])
    an.loop_pulse(YX, YY, YR, t['ink'], period, p0 + (push_total - YR) / LOOP_V)
    an.loop_pulse(GX, GY, GR, t['fb'], period, p1 + (back_total - GR) / LOOP_V)

    b(f'<circle cx="{KX}" cy="{KY}" r="{KR}" fill="{t["bg"]}" stroke="{t["kb"]}" stroke-width="1.6"/>')
    tx(KX, KY + 7, '知识库', 19, 650, layer=b, anchor='middle')
    tx(KX, KY + KR + 30, 'kb/<主题>.md', 14, 450, t['muted'], 'middle', mono=True)
    tx(KX, KY + KR + 52, '按主题合并 · 不重复', 15, 400, t['faint'], 'middle')

    b(f'<circle cx="{YX}" cy="{YY}" r="{YR}" fill="{t["bg"]}" stroke="{t["ink"]}" stroke-width="1.6"/>')
    tx(YX, YY + 10, '你', 28, 700, layer=b, anchor='middle')
    tx(YX, YY + YR + 30, '一句话总结 + 建议', 15, 450, t['muted'], 'middle')
    tx(YX, YY + YR + 52, '每周日一份周报', 15, 400, t['faint'], 'middle')

    T = round(t_k + 0.8, 2)
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
            p = out / f'social-flow-{name}{suffix}.svg'
            p.write_text(build(name, lang))
            print(p, f'{p.stat().st_size / 1024:.0f} KB')
