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
const components = {};

for (const code_ in evSans.chars) {
  const c = evSans.chars[code_];

  const paths_ = c.paths
    .filter((p) => Array.isArray(p) && p.length > 0)
    .map((p) => p.map((pt) => [pt.ix, pt.iy]));

  // Only cNNN entries map to a codepoint. Bare names (ci, up_tilde, ...) are
  // the accent marks and part-letters the source composes from. They are
  // exported too, so the builder can compose the accented glyphs upstream
  // never drew.
  const m = /^c(\d+)$/.exec(code_);
  if (!m) {
    if (paths_.length) components[code_] = { paths: paths_ };
    continue;
  }

  if (paths_.length === 0) continue; // e.g. c163 (£) has no outline yet

  glyphs[code_] = {
    codepoint: parseInt(m[1], 10),
    label: c.char,
    voids: c.voids || [],
    paths: paths_,
    defaultWidth: c.defaultWidth,
  };
}

process.stdout.write(
  JSON.stringify(
    { defaultGap, kerning: evSans.kearning, glyphs, components },
    null,
    2
  ) + "\n"
);
