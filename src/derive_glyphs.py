#!/usr/bin/env python3
"""Fill the gaps the upstream drawings left, without inventing letterforms.

The source stops partway through the accented set: it draws every lowercase
accent but only some uppercase ones, so uppercase N-tilde, O-tilde and the
accented I are missing while their lowercase exist. Anything set in Spanish or
Portuguese caps falls back to another face mid-word.

Everything here is built from parts the source already has, using the same
base-plus-mark composition it uses for the accented glyphs it did draw. The
one place this goes beyond assembly is the ring on A-ring and the bar on
O-slash, which are flagged below and are worth a designer's eye.

Genuinely new letterforms (AE, OE, eszett, thorn, eth, S-caron, Z-caron, the
pound sign, and true curly quotes) are not here. Those need drawing, not
composition.
"""

from __future__ import annotations

# Marks sit at a fixed x in the source, drawn for a glyph of a particular
# width. Centring them over a different base is a shift along x, the same
# trick the source uses for i-grave and friends.
COMPOSED = [
    # (codepoint, label, base code, mark component, uppercase?)
    (0x00CC, "Ì", "c73", "up_grave", True),
    (0x00CD, "Í", "c73", "up_acute", True),
    (0x00CE, "Î", "c73", "up_circumflex", True),
    (0x00CF, "Ï", "c73", "up_diaeresis", True),
    (0x00D1, "Ñ", "c78", "up_tilde", True),
    (0x00D5, "Õ", "c79", "up_tilde", True),
    (0x00DD, "Ý", "c89", "up_acute", True),
    (0x0178, "Ÿ", "c89", "up_diaeresis", True),
]

# ! and ? turned through 180 degrees and dropped to sit between the x-height
# and the descender, which is how the inverted marks are drawn.
ROTATED = [
    (0x00A1, "¡", "c33"),
    (0x00BF, "¿", "c63"),
]

# Straight quotes stand in for the typographic ones. They are not curly, and a
# real pair should be drawn, but mapping them means smart-quoted copy renders
# instead of showing a missing-glyph box.
ALIASES = {
    0x2018: 0x27,  # ' -> '
    0x2019: 0x27,  # ' -> '
    0x201C: 0x22,  # " -> "
    0x201D: 0x22,  # " -> "
}


def bbox(paths):
    xs = [p[0] for path in paths for p in path]
    ys = [p[1] for path in paths for p in path]
    return min(xs), min(ys), max(xs), max(ys)


def move(paths, dx, dy):
    return [[[p[0] + dx, p[1] + dy] for p in path] for path in paths]


def rotate180(paths, cx, cy):
    return [[[2 * cx - p[0], 2 * cy - p[1]] for p in path] for path in paths]


def snap(value, step=5):
    return round(value / step) * step


def add(data, codepoint, label, paths, voids):
    x0, _, x1, _ = bbox(paths)
    data["glyphs"][f"c{codepoint}"] = {
        "codepoint": codepoint,
        "label": label,
        "voids": voids,
        "paths": paths,
        "defaultWidth": max(x1, 0),
    }


def derive(data: dict) -> int:
    """Add the derivable glyphs to the extracted data. Returns how many."""
    glyphs, parts = data["glyphs"], data.get("components", {})
    before = len(glyphs)

    for codepoint, label, base_code, mark_name, upper in COMPOSED:
        base, mark = glyphs.get(base_code), parts.get(mark_name)
        if not base or not mark:
            continue

        bx0, _, bx1, _ = bbox(base["paths"])
        mx0, _, mx1, _ = bbox(mark["paths"])
        shift = snap(((bx0 + bx1) / 2) - ((mx0 + mx1) / 2))

        # Accented capitals all carry voids [12, 13] upstream regardless of
        # the base letter's own voids, so the kerning stays consistent.
        voids = [12, 13] if upper else base["voids"]
        add(data, codepoint, label, base["paths"] + move(mark["paths"], shift, 0), voids)

    for codepoint, label, base_code in ROTATED:
        base = glyphs.get(base_code)
        if not base:
            continue
        x0, y0, x1, y1 = bbox(base["paths"])
        turned = rotate180(base["paths"], (x0 + x1) / 2, (y0 + y1) / 2)
        add(data, codepoint, label, move(turned, 0, 30), base["voids"])

    # A-ring and a-ring reuse the degree sign, which is already a small ring
    # on this grid. Placement is a judgement call: the ring is 40 units tall
    # against the 20 of every other mark, so it sits closer to the letter.
    ring = glyphs.get("c176")
    if ring:
        for codepoint, label, base_code, drop in (
            (0x00C5, "Å", "c65", 50),
            (0x00E5, "å", "c97", 30),
        ):
            base = glyphs.get(base_code)
            if not base:
                continue
            bx0, _, bx1, _ = bbox(base["paths"])
            rx0, _, rx1, _ = bbox(ring["paths"])
            shift = snap(((bx0 + bx1) / 2) - ((rx0 + rx1) / 2))
            voids = [12, 13] if codepoint == 0x00C5 else base["voids"]
            add(
                data,
                codepoint,
                label,
                base["paths"] + move(ring["paths"], shift, -drop),
                voids,
            )

    # O-slash: a single stroke across the bowl's diagonal. Square caps push it
    # past the corners on their own, which is what makes the mark read.
    for codepoint, label, base_code in ((0x00D8, "Ø", "c79"), (0x00F8, "ø", "c111")):
        base = glyphs.get(base_code)
        if not base:
            continue
        x0, y0, x1, y1 = bbox(base["paths"])
        add(data, codepoint, label, base["paths"] + [[[x0, y1], [x1, y0]]], base["voids"])

    # Ordinals and dots, all straight reuse of shapes already on the grid.
    period = glyphs.get("c46")
    if period:
        px0, py0, _, _ = bbox(period["paths"])
        add(data, 0x2026, "…", [[[px0 + i, py0], [px0 + i, py0 + 1]] for i in (0, 40, 80)], [])
        add(data, 0x00B7, "·", move(period["paths"], 0, -40), [])
    if ring:
        add(data, 0x00BA, "º", ring["paths"], [])

    # Plus-minus: the plus lifted, with its own bar underneath.
    plus = glyphs.get("c43")
    if plus:
        _, _, _, py1 = bbox(plus["paths"])
        bar_x0, _, bar_x1, _ = bbox([plus["paths"][0]])
        add(
            data,
            0x00B1,
            "±",
            move(plus["paths"], 0, -10) + [[[bar_x0, py1 + 10], [bar_x1, py1 + 10]]],
            plus["voids"],
        )

    return len(glyphs) - before
