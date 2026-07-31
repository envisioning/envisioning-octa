#!/usr/bin/env python3
"""Structural checks on the built variable font."""

import os
import sys

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VF = os.path.join(ROOT, "dist", "EnvisioningOcta-VF.ttf")

fails = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(label)


font = TTFont(VF)

check("required tables", all(t in font for t in ("fvar", "gvar", "STAT", "GPOS", "cmap", "glyf")),
      ", ".join(sorted(set(font.keys()) & {"fvar", "gvar", "STAT", "GPOS", "HVAR", "avar"})))

axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
check("axes", axes == {"wght": (100.0, 400.0, 900.0), "wdth": (100.0, 100.0, 125.0)}, str(axes))
check("named instances", len(font["fvar"].instances) == 18, f"{len(font['fvar'].instances)}")

cmap = font.getBestCmap()

# A count is brittle; what matters is that the languages we set type in work.
REQUIRED = {
    "ASCII": "".join(chr(c) for c in range(0x21, 0x7F)),
    "Spanish": "ÁÉÍÓÚÜÑ¡¿áéíóúüñ",
    "Portuguese": "ÁÂÃÀÇÉÊÍÓÔÕÚáâãàçéêíóôõúº",
    "French": "ÀÂÇÈÉÊËÎÏÔÙÛÜŸàâçèéêëîïôùûüÿ",
    "German": "ÄÖÜäöü",
    "Nordic": "ÅØåø",
    "Typographic": "“”‘’–—…·•«»",
}
for label, chars in REQUIRED.items():
    missing = [c for c in chars if ord(c) not in cmap]
    check(f"cmap covers {label}", not missing, f"missing {''.join(missing)}" if missing else f"{len(chars)} chars")
print(f"      cmap total: {len(cmap)} codepoints")

# Advance widths and left sidebearings must agree with the outlines.
hmtx = font["hmtx"]
glyf = font["glyf"]
bad_lsb = []
for name in font.getGlyphOrder():
    g = glyf[name]
    if g.numberOfContours <= 0:
        continue
    g.recalcBounds(glyf)
    if hmtx[name][1] != g.xMin:
        bad_lsb.append((name, hmtx[name][1], g.xMin))
check("hmtx lsb matches xMin", not bad_lsb, str(bad_lsb[:4]))

# Stroke thickness at each axis end, measured off the stem of "l" (U+006C).
def stem_width(f, loc):
    inst = instantiateVariableFont(TTFont(VF), loc, inplace=False)
    gs = inst.getGlyphSet()
    pen = BoundsPen(gs)
    gs["uni006C"].draw(pen)
    xmin, ymin, xmax, ymax = pen.bounds
    return xmax - xmin, ymax - ymin


for loc, expected in (
    ({"wght": 100, "wdth": 100}, 3 * 7),
    ({"wght": 400, "wdth": 100}, 10 * 7),
    ({"wght": 900, "wdth": 100}, 25 * 7),
):
    w, h = stem_width(VF, loc)
    # "l" is a stem plus a 10-unit foot, so width is stroke + 10 grid units.
    got = w - 10 * 7
    check(f"stroke at wght={loc['wght']}", abs(got - expected) <= 1, f"{got} vs {expected} units")

# Width axis scales the skeleton, not the stroke.
narrow = stem_width(VF, {"wght": 400, "wdth": 100})
wide = stem_width(VF, {"wght": 400, "wdth": 125})
check("wdth scales skeleton", abs((wide[0] - 70) / (narrow[0] - 70) - 1.25) < 0.05,
      f"{narrow[0]} -> {wide[0]}")
check("wdth leaves height alone", narrow[1] == wide[1], f"{narrow[1]} / {wide[1]}")

# Vertical metrics vs. real ink at the heaviest weight, where the stroke
# pushes furthest past the accent line.
heavy = instantiateVariableFont(TTFont(VF), {"wght": 900, "wdth": 125}, inplace=False)
hglyf = heavy["glyf"]
drawn = [n for n in heavy.getGlyphOrder() if hglyf[n].numberOfContours > 0]
for n in drawn:
    hglyf[n].recalcBounds(hglyf)
ink_top = max(hglyf[n].yMax for n in drawn)
ink_bottom = min(hglyf[n].yMin for n in drawn)
os2 = font["OS/2"]
check("winAscent clears ink", os2.usWinAscent >= ink_top, f"{os2.usWinAscent} >= {ink_top}")
check("winDescent clears ink", -os2.usWinDescent <= ink_bottom, f"{-os2.usWinDescent} <= {ink_bottom}")
check("hhea matches typo metrics",
      (font["hhea"].ascent, font["hhea"].descent) == (os2.sTypoAscender, os2.sTypoDescender),
      f"{font['hhea'].ascent}/{font['hhea'].descent}")
check("USE_TYPO_METRICS set", bool(os2.fsSelection & (1 << 7)))

# Round-trip: the font must survive a compile/decompile cycle.
import io

buf = io.BytesIO()
font.save(buf)
buf.seek(0)
TTFont(buf).getGlyphOrder()
check("round-trips", True)

print()
if fails:
    print(f"{len(fails)} check(s) failed")
    sys.exit(1)
print("all checks passed")
