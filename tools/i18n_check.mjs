// i18n coverage gate: every user-facing runtime string must route its Japanese text
// through tr() or trf() so an EN user never sees raw Japanese. This covers BOTH classes
// of sink:
//   1. message functions: showHelp / alert / confirm / prompt
//   2. DOM display sinks:  .textContent= / .innerHTML=   (hover status, button labels, …)
// It fails CI if a new Japanese literal is added unwrapped at any of these sinks, and also
// verifies every wrapped key actually exists in the JE dictionary (no wrapped-but-untranslated).
//
// Run: node tools/i18n_check.mjs
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url)).replace(/[\\/]tools$/, '');
const html = readFileSync(join(ROOT, 'index.html'), 'utf8');

const JP = /[぀-ヿ㐀-鿿＀-￯々〆ー]/;
const MSG = ['showHelp', 'alert', 'confirm', 'prompt'];

// Balance parens with string-awareness from position `i` (just after an opening paren);
// returns the index just past the matching close paren.
function matchParen(src, i) {
  let depth = 1, q = null, esc = false;
  while (i < src.length && depth > 0) {
    const ch = src[i];
    if (q) { if (esc) esc = false; else if (ch === '\\') esc = true; else if (ch === q) q = null; }
    else if (ch === '\'' || ch === '"' || ch === '`') q = ch;
    else if (ch === '(') depth++;
    else if (ch === ')') depth--;
    i++;
  }
  return i;
}

// Collect scan segments: (1) message-call argument lists, (2) the RHS of textContent/innerHTML
// assignments (read to the statement-terminating ; at depth 0, string-aware).
function segments(src) {
  const out = [];
  const reMsg = new RegExp('\\b(' + MSG.join('|') + ')\\s*\\(', 'g');
  let m;
  while ((m = reMsg.exec(src))) {
    const start = reMsg.lastIndex, end = matchParen(src, start);
    out.push({ kind: m[1] + '()', text: src.slice(start, end - 1) });
    reMsg.lastIndex = end;
  }
  const reSink = /\.(textContent|innerHTML)\s*=(?!=)/g;
  let s;
  while ((s = reSink.exec(src))) {
    let i = reSink.lastIndex, depth = 0, q = null, esc = false;
    const start = i;
    while (i < src.length) {
      const ch = src[i];
      if (q) { if (esc) esc = false; else if (ch === '\\') esc = true; else if (ch === q) q = null; }
      else if (ch === '\'' || ch === '"' || ch === '`') q = ch;
      else if (ch === '(' || ch === '[' || ch === '{') depth++;
      else if (ch === ')' || ch === ']' || ch === '}') { if (depth === 0) break; depth--; }
      else if (ch === ';' && depth === 0) break;
      i++;
    }
    out.push({ kind: '.' + s[1] + '=', text: src.slice(start, i) });
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
const segs = segments(html);
for (const c of segs) {
  if (c.text.includes('i18n-allow')) continue;  // explicit opt-out (e.g. the language-toggle label is the OTHER language by design)
  let lm;
  litRe.lastIndex = 0;
  while ((lm = litRe.exec(c.text))) {
    const text = lm[2];
    const before = c.text.slice(0, lm.index);
    const isWrapped = wrapped.test(before);
    if (JP.test(text)) {
      if (!isWrapped) leaks.push(`${c.kind} raw Japanese literal "${text.slice(0, 48)}"`);
      else if (!jeKeys.has(text)) missing.push(`${c.kind} "${text.slice(0, 48)}" wrapped but not in JE dict`);
    }
  }
}

const fails = leaks.concat(missing);
if (fails.length) {
  console.error('NG: i18n coverage gate found ' + fails.length + ' uncovered string(s):\n  - ' + fails.join('\n  - '));
  process.exit(1);
}
console.log(`OK: i18n coverage holds — all ${segs.length} user-facing sinks (showHelp/alert/confirm/prompt + .textContent=/.innerHTML=) route Japanese through tr()/trf() with JE entries`);
