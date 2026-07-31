#!/usr/bin/env python3
"""Build Envisioning Octa as an OpenType variable font from the stroke data.

The source is a monoline stroke font: every glyph is a set of polylines on a
0..110 x 0..180 grid, rendered live with a stroke-width slider.
This turns that into real filled outlines and exposes the two things the
drawing model varies continuously as OpenType axes:

    wght  100..900   stroke thickness   (3..25 grid units)
    wdth  100..125   horizontal scale of the skeleton

Both are separable from the glyph geometry, so four masters (the default plus
one per axis extreme) describe the whole design space exactly.

Outlines are built one quad per polyline segment, extended by half the stroke
at each end -- the "square" line cap the tool uses by default. Segments
overlap at the joins and are all wound the same direction, so nonzero fill
renders them as a union. That also keeps every master point-compatible: the
contour count and order never change, only the coordinates.

    node src/extract.js > build/skeletons.json
    .venv/bin/python src/build_font.py
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.fixedTools import otRound
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import flagOverlapSimple
from fontTools.varLib import build as build_variable

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, "build")
MASTERS = os.path.join(BUILD, "masters")
DIST = os.path.join(ROOT, "dist")

# ---------------------------------------------------------------- metrics ---

UPEM = 1000
SCALE = 7  # grid unit -> font unit
BASELINE = 150  # grid y of the baseline

CAP_HEIGHT = (BASELINE - 50) * SCALE  # 700
X_HEIGHT = (BASELINE - 80) * SCALE  # 490
DESCENDER = (BASELINE - 180) * SCALE  # -210
ACCENT_TOP = (BASELINE - 0) * SCALE  # 1050

# Two sets of vertical metrics, as usual: typo/hhea drive line layout, win
# bounds only have to clear the ink. Accents sit at the very top of the grid
# and the stroke grows around the skeleton, so at Black the real ink runs well
# past the accent line -- covered by the win values, not paid for in leading.
ASCENT = 950
DESCENT = -300
WIN_ASCENT = 1190
WIN_DESCENT = 350

# Advance = skeleton width + sidebearing + one stroke width, so the optical
# gap between letters holds steady as the stroke grows. At the tool's default
# stroke of 18 this reproduces its gap of 30 exactly.
SIDEBEARING = 12
SPACE_WIDTH = 45  # defaultGap * 3, as the tool advances for U+0020

FAMILY = "Envisioning Octa"
VERSION = "1.000"
DESIGNER = "Thomaz Rezende"
MANUFACTURER = "Envisioning"

# ------------------------------------------------------------------ axes ---

WGHT_MASTERS = {100: 3.0, 400: 10.0, 900: 25.0}  # wght -> stroke, grid units
WDTH_MASTERS = {100: 1.0, 125: 1.25}  # wdth -> horizontal scale

DEFAULT_WGHT, DEFAULT_WDTH = 400, 100

# Master locations: the default, plus each axis extreme. The two effects are
# additively separable, so corner masters would be redundant.
MASTER_LOCATIONS = [
    (100, 100),
    (400, 100),
    (900, 100),
    (400, 125),
]

WEIGHT_NAMES = [
    (100, "Thin"),
    (200, "ExtraLight"),
    (300, "Light"),
    (400, "Regular"),
    (500, "Medium"),
    (600, "SemiBold"),
    (700, "Bold"),
    (800, "ExtraBold"),
    (900, "Black"),
]

WIDTH_NAMES = [(100, None), (125, "Expanded")]


@dataclass
class Master:
    wght: int
    wdth: int

    @property
    def stroke(self) -> float:
        return WGHT_MASTERS[self.wght]

    @property
    def xscale(self) -> float:
        return WDTH_MASTERS[self.wdth]

    @property
    def name(self) -> str:
        return f"wght{self.wght}wdth{self.wdth}"


# --------------------------------------------------------------- outlines ---


def to_font_units(x: float, y: float, xscale: float) -> tuple[float, float]:
    """Grid space (y down, baseline at 150) -> font units (y up)."""
    return x * xscale * SCALE, (BASELINE - y) * SCALE


JOIN_SIDES = 16  # polygon approximating a round line join


def clockwise(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Round to integers and wind clockwise, the TrueType convention in y-up."""
    pts = [(otRound(px), otRound(py)) for px, py in points]
    area = 0.0
    for i in range(len(pts)):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % len(pts)]
        area += ax * by - bx * ay
    if area > 0:  # counter-clockwise
        pts.reverse()
    return pts


def segment_quad(p0, p1, half: float, cap0: bool, cap1: bool, xscale: float):
    """A polyline segment as a filled quad, square-capped only where asked."""
    x0, y0 = to_font_units(p0[0], p0[1], xscale)
    x1, y1 = to_font_units(p1[0], p1[1], xscale)

    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length == 0:
        dx, dy, length = 1.0, 0.0, 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux  # left normal

    e0x, e0y = (ux * half, uy * half) if cap0 else (0.0, 0.0)
    e1x, e1y = (ux * half, uy * half) if cap1 else (0.0, 0.0)
    ox, oy = nx * half, ny * half

    return clockwise(
        [
            (x0 - e0x + ox, y0 - e0y + oy),
            (x1 + e1x + ox, y1 + e1y + oy),
            (x1 + e1x - ox, y1 + e1y - oy),
            (x0 - e0x - ox, y0 - e0y - oy),
        ]
    )


def join_disc(p, half: float, xscale: float):
    """Round join, matching the tool's strokeLineJoin: 'round'."""
    cx, cy = to_font_units(p[0], p[1], xscale)
    return clockwise(
        [
            (
                cx + half * math.cos(2 * math.pi * i / JOIN_SIDES),
                cy + half * math.sin(2 * math.pi * i / JOIN_SIDES),
            )
            for i in range(JOIN_SIDES)
        ]
    )


def emit(pen, points) -> None:
    pen.moveTo(points[0])
    for pt in points[1:]:
        pen.lineTo(pt)
    pen.closePath()


def draw_glyph(paths, stroke: float, xscale: float, pen) -> None:
    half = stroke * SCALE / 2.0
    for path in paths:
        # The tool closes a path with `z` when it returns to its start, which
        # turns the seam into a join rather than two caps.
        closed = len(path) > 2 and path[0] == path[-1]
        last = len(path) - 2

        for i in range(len(path) - 1):
            emit(
                pen,
                segment_quad(
                    path[i],
                    path[i + 1],
                    half,
                    cap0=(i == 0 and not closed),
                    cap1=(i == last and not closed),
                    xscale=xscale,
                ),
            )

        # Round join at every interior vertex, plus the seam on closed paths.
        joins = list(range(1, len(path) - 1))
        if closed:
            joins.append(0)
        for i in joins:
            emit(pen, join_disc(path[i], half, xscale))


def notdef_glyph(pen) -> None:
    """A hollow box. Constant across masters, so it contributes no deltas."""
    outer = [(80, 0), (80, CAP_HEIGHT), (520, CAP_HEIGHT), (520, 0)]
    inner = [(160, 80), (440, 80), (440, CAP_HEIGHT - 80), (160, CAP_HEIGHT - 80)]
    for ring in (outer, inner):
        pen.moveTo(ring[0])
        for pt in ring[1:]:
            pen.lineTo(pt)
        pen.closePath()


# ---------------------------------------------------------------- kerning ---


def kern_value(a: dict, b: dict, kerning: dict) -> int:
    """Reproduce the source calcGap(): void classes on each side pick a reduction.

    Later matches win, matching the JS nested-map iteration order.
    """
    kern = 0
    for vc in a["voids"]:
        for vn in b["voids"]:
            v = kerning.get(f"v{vc}_{vn}")
            if v:
                kern = v
    return kern


# ------------------------------------------------------------------ build ---


def glyph_name(codepoint: int, label: str) -> str:
    return f"uni{codepoint:04X}"


def build_master(data: dict, master: Master, order: list, path: str) -> None:
    glyphs, advances = {}, {}

    pen = TTGlyphPen(None)
    notdef_glyph(pen)
    glyphs[".notdef"] = pen.glyph()
    advances[".notdef"] = otRound(600 * master.xscale)

    glyphs["space"] = TTGlyphPen(None).glyph()
    advances["space"] = otRound(SPACE_WIDTH * master.xscale * SCALE)

    for name, code in order:
        if name in glyphs:
            continue
        g = data["glyphs"][code]
        pen = TTGlyphPen(None)
        draw_glyph(g["paths"], master.stroke, master.xscale, pen)
        glyphs[name] = pen.glyph()
        advances[name] = otRound(
            ((g["defaultWidth"] + SIDEBEARING) * master.xscale + master.stroke) * SCALE
        )

    glyph_order = [".notdef", "space"] + [n for n, _ in order]
    cmap = {0x20: "space"}
    for name, code in order:
        cmap[data["glyphs"][code]["codepoint"]] = name

    style = style_name(master.wght, master.wdth)
    fb = FontBuilder(UPEM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (advances[n], glyphs[n].xMin if glyphs[n].numberOfContours else 0) for n in glyph_order})
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT, lineGap=0)
    fb.setupNameTable(
        {
            "familyName": FAMILY,
            "styleName": style,
            "uniqueFontIdentifier": f"{FAMILY} {style} {VERSION}",
            "fullName": f"{FAMILY} {style}",
            "psName": f"{FAMILY.replace(' ', '')}-{style.replace(' ', '')}",
            "version": VERSION,
            "designer": DESIGNER,
            "manufacturer": MANUFACTURER,
        }
    )
    fb.setupOS2(
        version=4,
        sTypoAscender=ASCENT,
        sTypoDescender=DESCENT,
        sTypoLineGap=0,
        usWinAscent=WIN_ASCENT,
        usWinDescent=WIN_DESCENT,
        sxHeight=X_HEIGHT,
        sCapHeight=CAP_HEIGHT,
        usWeightClass=master.wght,
        usWidthClass=width_class(master.wdth),
        fsSelection=(1 << 7),  # USE_TYPO_METRICS
        achVendID="ENVS",
    )
    fb.setupPost(isFixedPitch=0, underlinePosition=-100, underlineThickness=otRound(master.stroke * SCALE))
    fb.setupDummyDSIG()

    mark_overlaps(fb.font)
    fb.save(path)


def mark_overlaps(font: TTFont) -> None:
    """Tell rasterizers the contours self-overlap by design."""
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        g = glyf[name]
        if g.numberOfContours > 0:
            g.flags[0] |= flagOverlapSimple


def width_class(wdth: int) -> int:
    return {100: 5, 125: 7}[wdth]


def style_name(wght: int, wdth: int) -> str:
    weight = dict(WEIGHT_NAMES)[wght]
    width = dict(WIDTH_NAMES)[wdth]
    if width is None:
        return weight
    return f"{width} {weight}" if weight != "Regular" else width


def main() -> None:
    os.makedirs(MASTERS, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    with open(os.path.join(BUILD, "skeletons.json")) as fp:
        data = json.load(fp)

    order = sorted(
        ((glyph_name(g["codepoint"], g["label"]), code) for code, g in data["glyphs"].items()),
        key=lambda item: data["glyphs"][item[1]]["codepoint"],
    )

    masters = [Master(w, d) for w, d in MASTER_LOCATIONS]
    for master in masters:
        build_master(data, master, order, os.path.join(MASTERS, f"{master.name}.ttf"))
    print(f"built {len(masters)} masters, {len(order) + 2} glyphs each")

    doc = DesignSpaceDocument()
    for tag, name, minimum, default, maximum in (
        ("wght", "Weight", 100, DEFAULT_WGHT, 900),
        ("wdth", "Width", 100, DEFAULT_WDTH, 125),
    ):
        axis = AxisDescriptor()
        axis.tag, axis.name = tag, name
        axis.minimum, axis.default, axis.maximum = minimum, default, maximum
        doc.addAxis(axis)

    for master in masters:
        source = SourceDescriptor()
        source.path = os.path.join(MASTERS, f"{master.name}.ttf")
        source.name = master.name
        source.location = {"Weight": master.wght, "Width": master.wdth}
        if master.wght == DEFAULT_WGHT and master.wdth == DEFAULT_WDTH:
            source.copyLib = source.copyInfo = source.copyGroups = source.copyFeatures = True
        doc.addSource(source)

    for wdth, width in WIDTH_NAMES:
        for wght, weight in WEIGHT_NAMES:
            doc.addInstanceDescriptor(
                familyName=FAMILY,
                styleName=style_name(wght, wdth),
                location={"Weight": wght, "Width": wdth},
            )

    ds_path = os.path.join(BUILD, "EnvisioningOcta.designspace")
    doc.write(ds_path)

    vf, _, _ = build_variable(ds_path)
    add_kerning(vf, data, order)
    add_stat(vf)
    name_instances(vf)
    mark_overlaps(vf)

    out = os.path.join(DIST, "EnvisioningOcta-VF.ttf")
    vf.save(out)
    print(f"wrote {out}")

    # Same font, web-compressed, for envisioning.com and friends.
    vf.flavor = "woff2"
    vf.save(os.path.join(DIST, "EnvisioningOcta-VF.woff2"))
    print(f"wrote {os.path.join(DIST, 'EnvisioningOcta-VF.woff2')}")

    make_statics(out)
    write_glyph_index(vf, data, order)


def write_glyph_index(font: TTFont, data: dict, order: list) -> None:
    """Glyph inventory for the preview page, so it can't drift from the font."""
    entries = [{"cp": 0x20, "name": "space", "label": "space"}]
    for name, code in order:
        g = data["glyphs"][code]
        entries.append({"cp": g["codepoint"], "name": name, "label": chr(g["codepoint"])})

    index = {
        "family": FAMILY,
        "axes": [
            {"tag": a.axisTag, "min": a.minValue, "default": a.defaultValue, "max": a.maxValue}
            for a in font["fvar"].axes
        ],
        "instances": [
            {
                "name": font["name"].getDebugName(i.subfamilyNameID),
                "location": {k: v for k, v in i.coordinates.items()},
            }
            for i in font["fvar"].instances
        ],
        "weights": [{"value": w, "name": n} for w, n in WEIGHT_NAMES],
        "widths": [{"value": w, "name": n or "Normal"} for w, n in WIDTH_NAMES],
        "metrics": {
            "upem": UPEM,
            "capHeight": CAP_HEIGHT,
            "xHeight": X_HEIGHT,
            "ascent": ASCENT,
            "descent": DESCENT,
        },
        "glyphs": entries,
    }
    path = os.path.join(DIST, "glyphs.json")
    with open(path, "w") as fp:
        json.dump(index, fp, ensure_ascii=False, indent=1)
    print(f"wrote {path} ({len(entries)} glyphs)")


# A short list of static cuts, for anything that still chokes on a variable
# font (older Adobe apps, some print workflows).
STATIC_CUTS = [
    (100, 100), (300, 100), (400, 100), (700, 100), (900, 100),
    (400, 125), (700, 125),
]


def make_statics(vf_path: str) -> None:
    from fontTools.varLib.instancer import instantiateVariableFont

    # Wipe first, so cuts dropped from STATIC_CUTS do not linger from an
    # earlier build and ship as part of the download bundle.
    static_dir = os.path.join(DIST, "static")
    if os.path.isdir(static_dir):
        for stale in os.listdir(static_dir):
            os.remove(os.path.join(static_dir, stale))
    os.makedirs(static_dir, exist_ok=True)
    for wght, wdth in STATIC_CUTS:
        font = instantiateVariableFont(
            TTFont(vf_path), {"wght": wght, "wdth": wdth}, updateFontNames=True
        )
        style = style_name(wght, wdth)
        font["OS/2"].usWeightClass = wght
        font["OS/2"].usWidthClass = width_class(wdth)
        name = f"EnvisioningOcta-{style.replace(' ', '')}.ttf"
        font.save(os.path.join(static_dir, name))
    print(f"wrote {len(STATIC_CUTS)} static instances to {static_dir}")


def name_instances(font: TTFont) -> None:
    """Typographic family names plus a PostScript name per named instance.

    Without these, CoreText builds instance names by tacking the instance name
    onto the full name -- "Envisioning Octa Regular Condensed Thin" in Font Book.
    """
    name = font["name"]
    name.setName(FAMILY, 16, 3, 1, 0x409)
    name.setName("Regular", 17, 3, 1, 0x409)

    for instance in font["fvar"].instances:
        style = name.getDebugName(instance.subfamilyNameID)
        ps = f"{FAMILY.replace(' ', '')}-{style.replace(' ', '')}"
        instance.postscriptNameID = name.addName(ps, minNameID=255)


def add_stat(font: TTFont) -> None:
    axes = [
        {
            "tag": "wght",
            "name": "Weight",
            "ordering": 0,
            "values": [
                {
                    "value": wght,
                    "name": name,
                    "flags": 0x2 if wght == 400 else 0,
                    **({"linkedValue": 700} if wght == 400 else {}),
                }
                for wght, name in WEIGHT_NAMES
            ],
        },
        {
            "tag": "wdth",
            "name": "Width",
            "ordering": 1,
            "values": [
                {
                    "value": wdth,
                    "name": name or "Regular",
                    "flags": 0x2 if wdth == 100 else 0,
                }
                for wdth, name in WIDTH_NAMES
            ],
        },
    ]
    buildStatTable(font, axes, elidedFallbackName="Regular")


def add_kerning(font: TTFont, data: dict, order: list) -> None:
    """Port the void-class kerning to GPOS as class-based pair positioning."""
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

    by_name = {name: data["glyphs"][code] for name, code in order}

    # Group glyphs by their void list; kerning only ever reads that.
    left_classes: dict[tuple, list[str]] = {}
    right_classes: dict[tuple, list[str]] = {}
    for name, g in by_name.items():
        key = tuple(g["voids"])
        left_classes.setdefault(key, []).append(name)
        right_classes.setdefault(key, []).append(name)

    lines = []
    for i, key in enumerate(left_classes):
        lines.append(f"@L{i} = [{' '.join(left_classes[key])}];")
    for i, key in enumerate(right_classes):
        lines.append(f"@R{i} = [{' '.join(right_classes[key])}];")

    pairs = 0
    rules = []
    for i, lkey in enumerate(left_classes):
        for j, rkey in enumerate(right_classes):
            kern = kern_value({"voids": list(lkey)}, {"voids": list(rkey)}, data["kerning"])
            if kern:
                rules.append(f"    pos @L{i} @R{j} {-kern * SCALE};")
                pairs += 1

    if not rules:
        return
    fea = "\n".join(lines) + "\n\nfeature kern {\n" + "\n".join(rules) + "\n} kern;\n"
    addOpenTypeFeaturesFromString(font, fea)
    print(f"kerning: {pairs} class pairs from {len(left_classes)} void groups")


if __name__ == "__main__":
    main()
