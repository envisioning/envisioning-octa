#!/usr/bin/env bash
# Full rebuild: extract glyph data from the skeletons, compile the fonts, verify.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q fonttools brotli
fi

node src/extract.js > build/skeletons.json
.venv/bin/python src/build_font.py
.venv/bin/python src/check_font.py
python3 src/check_macos.py
