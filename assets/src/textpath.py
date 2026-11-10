"""把文字排成 SVG 路径，GitHub 的 raw 图片禁止加载字体，只能这样保证各平台显示一致。

依赖：fonttools、uharfbuzz（pip install fonttools uharfbuzz）
字体（都是 OFL，放在 FONTS_DIR）：Inter.ttf、NotoSansSC.ttf、JetBrainsMono.ttf
"""
from __future__ import annotations

import os
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

FONTS_DIR = Path(os.environ.get('FONTS_DIR', Path(__file__).parent / 'fonts'))
FILES = {'latin': 'Inter.ttf', 'cjk': 'NotoSansSC.ttf', 'mono': 'JetBrainsMono.ttf'}


def is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x2E80 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF


class Typesetter:
    def __init__(self):
        self._tt = {}
        self._hb = {}
        self._gs = {}
        self.defs = {}  # (family, wght, gid) -> (id, d)

    def _font(self, fam: str, wght: int):
        if fam not in self._tt:
            path = str(FONTS_DIR / FILES[fam])
            self._tt[fam] = TTFont(path)
            self._hb[fam] = hb.Face(hb.Blob.from_file_path(path))
        key = (fam, wght)
        if key not in self._gs:
            tt = self._tt[fam]
            axes = {a.axisTag for a in tt['fvar'].axes}
            loc = {'wght': wght}
            if 'opsz' in axes:
                loc['opsz'] = 22
            font = hb.Font(self._hb[fam])
            font.set_variations(loc)
            self._gs[key] = (font, tt.getGlyphSet(location=loc), tt.getGlyphOrder(), tt['head'].unitsPerEm)
        return self._gs[key]

    def _glyph_id(self, fam, wght, gid):
        k = (fam, wght, gid)
        if k not in self.defs:
            _, gs, order, _ = self._font(fam, wght)
            pen = SVGPathPen(gs, ntos=lambda v: str(round(v)))
            gs[order[gid]].draw(pen)
            self.defs[k] = (f'g{len(self.defs)}', pen.getCommands())
        return self.defs[k][0]

    def layout(self, text: str, size: float, wght: int, mono=False, tracking=0.0):
        """返回 [(glyph_id, x, scale)] 和总宽度（px）。"""
        runs, cur = [], None
        for ch in text:
            fam = 'mono' if mono and not is_cjk(ch) else ('cjk' if is_cjk(ch) else 'latin')
            if cur and cur[0] == fam:
                cur[1] += ch
            else:
                cur = [fam, ch]
                runs.append(cur)
        out, x = [], 0.0
        for fam, s in runs:
            font, _, _, upem = self._font(fam, wght)
            k = size / upem
            buf = hb.Buffer()
            buf.add_str(s)
            buf.guess_segment_properties()
            hb.shape(font, buf, {'cv08': True} if fam == 'latin' else {})
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
                gid = self._glyph_id(fam, wght, info.codepoint)
                out.append((gid, x + pos.x_offset * k, k))
                x += pos.x_advance * k + tracking
        return out, x - (tracking if out else 0)

    def text(self, x, y, s, size, wght=400, fill='#000', anchor='start', mono=False, tracking=0.0, extra=''):
        glyphs, w = self.layout(s, size, wght, mono, tracking)
        x0 = x - (w / 2 if anchor == 'middle' else w if anchor == 'end' else 0)
        uses = ''.join(
            f'<use href="#{gid}" transform="translate({x0 + gx:.1f} {y}) scale({k:.5f} {-k:.5f})"/>'
            for gid, gx, k in glyphs)
        return f'<g fill="{fill}"{extra}>{uses}</g>', w

    def defs_svg(self) -> str:
        return ''.join(f'<path id="{i}" d="{d}"/>' for i, d in self.defs.values())
