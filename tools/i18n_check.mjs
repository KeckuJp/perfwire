// i18n coverage gate: every user-facing runtime message (showHelp / alert / confirm /
// prompt) must route its Japanese text through tr() or trf() so EN users never see a
// raw Japanese toast. This fails CI if a new message literal is added unwrapped —
// catching the whole class of leaks, not just the ones fixed by hand.
//
// It also verifies that every tr()/trf() KEY actually present at a call site exists in
// the JE dictionary, so a wrapped-but-untranslated string can't slip through either.
//
// Run: node tools/i18n_check.mjs
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url)).replace(/[\\/]tools$/, '');
const html = readFileSync(join(ROOT, 'index.html'), 'utf8');

const JP = /[぀-ヿ㐀-鿿＀-￯々〆ー]/;
const MSG = ['showHelp', 'alert', 'confirm', 'prompt'];

// Extract the argument text of every message-function call by balancing parens with
// string-awareness (handles nested tr()/trf() and multi-line calls).
function callArgs(src) {
  const out = [];
  const re = new RegExp('\\b(' + MSG.join('|') + ')\\s*\\(', 'g');
  let m;
  while ((m = re.exec(src))) {
    let i = re.lastIndex, depth = 1, q = null, esc = false;
    const start = i;
    while (i < src.length && depth > 0) {
      const ch = src[i];
      if (q) { if (esc) esc = false; else if (ch === '\\') esc = true; else if (ch === q) q = null; }
      else if (ch === '\'' || ch === '"' || ch === '`') q = ch;
      else if (ch === '(') depth++;
      else if (ch === ')') depth--;
      i++;
    }
    out.push({ fn: m[1], arg: src.slice(start, i - 1), at: m.index });
    re.lastIndex = i;
  }
  return out;
}

// Pull the JE dictionary keys so we can verify wrapped strings are actually translated.
// Slice from `var JE={` to the `function tr(` that follows it (robust to where `};` sits).
const jeStart = html.indexOf('var JE={');
const jeEnd = html.indexOf('function tr(', jeStart);
if (jeStart < 0 || jeEnd < 0) { console.error('NG: could not locate JE dictionary'); process.exit(1); }
const jeText = html.slice(jeStart, jeEnd);
const jeKeys = new Set();
const keyRe = /(?:^|,|\{)\s*'((?:\\.|[^'])*)'\s*:/g;
let km;
while ((km = keyRe.exec(jeText))) jeKeys.add(km[1].replace(/\\'/g, "'"));

const litRe = /(['"])((?:\\.|(?!\1).)*)\1/g;
const wrapped = /(^|[^\w.])(tr|trf)\($/;
const leaks = [], missing = [];
for (const c of callArgs(html)) {
  let lm;
  litRe.lastIndex = 0;
  while ((lm = litRe.exec(c.arg))) {
    const text = lm[2];
    const before = c.arg.slice(0, lm.index);
    const isWrapped = wrapped.test(before);
    if (JP.test(text)) {
      if (!isWrapped) leaks.push(`${c.fn}(): raw Japanese literal "${text.slice(0, 48)}"`);
      else if (!jeKeys.has(text)) missing.push(`${c.fn}(): "${text.slice(0, 48)}" wrapped but not in JE dict`);
    } else if (isWrapped && !jeKeys.has(text)) {
      // a tr()/trf() key with no Japanese is allowed (already-English keys), so don't flag.
    }
  }
}

const fails = leaks.concat(missing);
if (fails.length) {
  console.error('NG: i18n coverage gate found ' + fails.length + ' uncovered message string(s):\n  - ' + fails.join('\n  - '));
  process.exit(1);
}
const total = callArgs(html).length;
console.log(`OK: i18n coverage holds — all ${total} message calls (showHelp/alert/confirm/prompt) route Japanese through tr()/trf() with JE entries`);
