// Runs the vendored skeleton source (unmodified) and dumps the resolved glyph
// data as JSON for the Python font builder.
//
//   node src/extract.js > build/skeletons.json

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const srcPath = path.join(__dirname, "skeletons.js");
const code = fs.readFileSync(srcPath, "utf8");

// It is chatty on load; keep stdout clean for the JSON dump.
const sandbox = { console: { log() {}, warn() {}, error() {} } };
vm.createContext(sandbox);
vm.runInContext(code + "\n;globalThis.__out = { evSans, defaultGap };", sandbox);

const { evSans, defaultGap } = sandbox.__out;

const glyphs = {};
for (const code_ in evSans.chars) {
  const c = evSans.chars[code_];

  // Only cNNN entries map to a codepoint. Bare names (ci, low_grave, ...) are
  // components that have already been resolved into the paths above.
  const m = /^c(\d+)$/.exec(code_);
  if (!m) continue;

  // Import placeholders are removed with `delete arr[i]`, leaving holes.
  const paths = c.paths
    .filter((p) => Array.isArray(p) && p.length > 0)
    .map((p) => p.map((pt) => [pt.ix, pt.iy]));

  if (paths.length === 0) continue; // e.g. c163 (£) has no outline yet

  glyphs[code_] = {
    codepoint: parseInt(m[1], 10),
    label: c.char,
    voids: c.voids || [],
    paths,
    defaultWidth: c.defaultWidth,
  };
}

process.stdout.write(
  JSON.stringify(
    { defaultGap, kerning: evSans.kearning, glyphs },
    null,
    2
  ) + "\n"
);
