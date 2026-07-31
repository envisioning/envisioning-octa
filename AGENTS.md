# envisioning-octa

Compiles the upstream stroke drawings into an installable OpenType variable font.

## Build

```bash
./build.sh
```

Extracts glyph data from `src/skeletons.js`, compiles `dist/`, then runs both check
suites. Everything is regenerated, so `dist/` is safe to delete.

## Layout

- `src/skeletons.js` — the stroke drawings, vendored verbatim from
  `https://envisioning.github.io/tools/evSans/evSans.js` (upstream still uses the
  old name). Do not edit. Re-vendor from that URL when it changes, then rebuild.
  Its contents are unmodified, so the global it defines is still called
  `evSans`; `extract.js` reads that global by name. Renaming it would have to be
  re-applied on every re-vendor, and it never reaches any output.
- `src/extract.js` — runs that file in a `vm` sandbox and dumps resolved glyph
  data to `build/skeletons.json`.
- `src/build_font.py` — masters, designspace, variable font, statics, WOFF2.
- `src/check_font.py` — structural checks (axes, metrics, stroke thickness, cmap).
- `src/check_macos.py` — registers each file with CoreText, the same path Font
  Book takes. Runs on system python3, not the venv, since it only needs ctypes.
- `dist/index.html` — the tester. Hand-written, not generated, but it reads
  `dist/glyphs.json` (which the build emits) for the glyph grid, axis ranges,
  and family name, so it never hardcodes what is in the font. Needs to be
  served over http because of that fetch.

## Invariants

- **Masters must stay point-compatible.** Every glyph emits one quad per polyline
  segment plus one 16-gon per interior join, in a fixed order. Any change to
  `draw_glyph` that makes contour count depend on stroke width or width factor
  breaks `varLib` interpolation.
- **Contours overlap on purpose.** Strokes are not booleaned into a single
  outline; segments and joins overlap and all wind clockwise, so nonzero fill
  renders the union. `OVERLAP_SIMPLE` is set on every simple glyph. Do not run
  an overlap-removal pass without also solving point compatibility.
- **Four masters.** Stroke thickness and horizontal scale are additively
  separable in the outline math, so the default plus one master per axis extreme
  describes the space exactly. Corner masters would be redundant.
- **The width axis starts at 100.** It ran down to 75 (Condensed) until MZ cut
  it on 2026-07-31: condensing a monoline face pushes the stems together without
  thinning them, and it read as squished. Restoring it means putting 75 back in
  `WDTH_MASTERS`, `MASTER_LOCATIONS`, `WIDTH_NAMES`, the axis minimum, and the
  matching expectations in `check_font.py`.
- **Glyphs are keyed by code, not by the `char` field.** Upstream `char` labels
  are wrong in several places (`c93` says `[`, `c123` says `(`, `c59` says `.`).
  `cNNN` is the codepoint and is authoritative.
- Upstream resolves `{import: ...}` placeholders with `delete arr[i]`, leaving
  array holes that become `null` in JSON. `extract.js` filters them.

## Publishing to envisioning.com

The site does not consume this repo as a package. Four files are copied by hand
into `~/Dev/envisioning/envisioning.com`, and all four have to move together or
the page will describe a font it is not serving:

```bash
OCTA=~/Dev/envisioning-octa
SITE=~/Dev/envisioning/envisioning.com
cp $OCTA/dist/EnvisioningOcta-VF.woff2 $SITE/app/fonts/
cp $OCTA/dist/EnvisioningOcta-VF.woff2 $OCTA/dist/EnvisioningOcta-VF.ttf $SITE/public/fonts/
cp $OCTA/dist/glyphs.json $SITE/app/about/brand/octa/glyphs.json
rm -f $SITE/public/fonts/EnvisioningOcta.zip
cd $OCTA/dist && zip -qr $SITE/public/fonts/EnvisioningOcta.zip EnvisioningOcta-VF.ttf EnvisioningOcta-VF.woff2 static
```

`app/fonts/` is what `next/font/local` loads. `public/fonts/` is what the
download buttons serve. `glyphs.json` drives the glyph grid, the axis ramps and
the instance counts in the page copy, so the page follows the font instead of
hardcoding it. The page lives at `app/about/brand/octa/`.

## Derived glyphs

`src/derive_glyphs.py` adds the glyphs the upstream drawings never included.
The source draws every lowercase accent but stops partway through the
uppercase ones, so N-tilde, O-tilde and the accented I were missing while
their lowercase existed, and caps in Spanish or Portuguese fell back to
another face mid-word.

Everything there is composed from parts the source already contains, using the
same base-plus-mark pattern it uses for the accented glyphs it did draw.
`extract.js` exports the bare component entries (`up_tilde`, `up_acute`, ...)
alongside the `cNNN` glyphs so this is possible. Marks are centred on the base
by shifting along x and snapping to 5 units, matching the source's own `move`
offsets.

Two entries go past pure assembly and are worth a designer's eye: the ring on
A-ring reuses the degree sign and sits closer to the letter than other marks
because it is twice their height, and O-slash is a single stroke across the
bowl's diagonal. The typographic quotes are cmap aliases onto the straight
quotes, not drawn curly quotes.

Not derivable, still needing real letterforms: AE, OE, eszett, thorn, eth,
S-caron, Z-caron, and the pound sign (`c163` is an empty path list upstream).

## Traps

- `c163` (£) has an empty path list upstream and is skipped, so the font has no
  pound sign. It will appear automatically once upstream draws it.
- Accents sit at the very top of the grid (y=0) with a 30-unit gap above cap
  height. That is the source design, not a metrics bug.
- Two sets of vertical metrics: typo/hhea drive line layout, win bounds only
  clear the ink. At Black the stroke pushes ink to ~1174 units, well past the
  950 ascent.
