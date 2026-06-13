// i18n coverage gate (comprehensive): an EN user must never see raw Japanese. The gate
// enforces this across every surface where a Japanese string can reach the screen:
//
//   CHECK 1 (sinks, strict): Japanese literals passed to a display sink — showHelp / alert /
//     confirm / prompt / T() (SVG text) / .textContent= / .innerHTML= — must be wrapped in
//     tr() / trf() / L() (not merely registered), or marked /*i18n-allow*/.
//   CHECK 2 (script-wide): EVERY Japanese string literal in the inline <script> must be either
//     wrapped (tr/trf/L), a key in the JE dictionary (so it is translated at its use site, e.g.
//     KINDJ/HINT data maps), or i18n-allow. Catches stray literals not at a recognised sink
//     (e.g. a composed SVG message string).
//   CHECK 3 (HTML attrs): every Japanese title / placeholder / aria-label attribute in the static
//     markup must be a JE key (applyStatic translates these by dictionary lookup).
//
// Run: node tools/i18n_check.mjs
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url)).replace(/[\\/]tools$/, '');
const html = readFileSync(join(ROOT, 'index.html'), 'utf8');

const JP = /[぀-ヿ㐀-鿿＀-￯々〆ー]/;
const SINK_FNS = ['showHelp', 'alert', 'confirm', 'prompt', 'T'];
const WRAP = /(^|[^\w.])(tr|trf|L)\($/;        // tr()/trf()/L() i18n wrappers
const litRe = /(['"])((?:\\.|(?!\1).)*)\1/g;

// Split: the app lives in a single inline <script>. Scan JS there; scan attributes in the markup.
const sOpen = html.indexOf('<script>');
const sStart = sOpen + '<script>'.length;
const sEnd = html.indexOf('</script>', sStart);
const script = html.slice(sStart, sEnd);
const markup = html.slice(0, sOpen) + html.slice(sEnd);

// JE dictionary (inside the script): collect keys, and remember the block range to skip.
const jeStart = script.indexOf('var JE={');
const jeEnd = script.indexOf('function tr(', jeStart);
if (jeStart < 0 || jeEnd < 0) { console.error('NG: could not locate JE dictionary'); process.exit(1); }
const jeKeys = new Set();
const keyRe = /(?:^|,|\{)\s*'((?:\\.|[^'])*)'\s*:/g;
let km;
while ((km = keyRe.exec(script.slice(jeStart, jeEnd)))) jeKeys.add(km[1].replace(/\\'/g, "'"));

function lineStart(off) { return script.lastIndexOf('\n', off - 1) + 1; }
function allowAt(off) {
  let le = script.indexOf('\n', off); if (le < 0) le = script.length;
  return script.slice(lineStart(off), le).includes('i18n-allow');
}
function matchParen(s, i) {
  let depth = 1, q = null, esc = false;
  while (i < s.length && depth > 0) {
    const ch = s[i];
    if (q) { if (esc) esc = false; else if (ch === '\\') esc = true; else if (ch === q) q = null; }
    else if (ch === '\'' || ch === '"' || ch === '`') q = ch;
    else if (ch === '(') depth++;
    else if (ch === ')') depth--;
    i++;
  }
  return i;
}

const leaks = [], missing = [];

// CHECK 1 — display sinks (strict: must be wrapped, JE-key is not enough).
const segs = [];
const reMsg = new RegExp('(^|[^\\w.])(' + SINK_FNS.join('|') + ')\\s*\\(', 'g');
let mm;
while ((mm = reMsg.exec(script))) {
  const start = reMsg.lastIndex, end = matchParen(script, start);
  segs.push({ kind: mm[2] + '()', text: script.slice(start, end - 1) });
  reMsg.lastIndex = end;
}
const reSink = /\.(textContent|innerHTML)\s*=(?!=)/g;
let s;
while ((s = reSink.exec(script))) {
  let i = reSink.lastIndex, depth = 0, q = null, esc = false; const start = i;
  while (i < script.length) {
    const ch = script[i];
    if (q) { if (esc) esc = false; else if (ch === '\\') esc = true; else if (ch === q) q = null; }
    else if (ch === '\'' || ch === '"' || ch === '`') q = ch;
    else if (ch === '(' || ch === '[' || ch === '{') depth++;
    else if (ch === ')' || ch === ']' || ch === '}') { if (depth === 0) break; depth--; }
    else if (ch === ';' && depth === 0) break;
    i++;
  }
  segs.push({ kind: '.' + s[1] + '=', text: script.slice(start, i) });
}
for (const c of segs) {
  if (c.text.includes('i18n-allow')) continue;
  let lm; litRe.lastIndex = 0;
  while ((lm = litRe.exec(c.text))) {
    const text = lm[2];
    if (!JP.test(text)) continue;
    const before = c.text.slice(0, lm.index);
    if (!WRAP.test(before)) leaks.push(`${c.kind} raw Japanese literal "${text.slice(0, 48)}"`);
    else if (!jeKeys.has(text)) missing.push(`${c.kind} "${text.slice(0, 48)}" wrapped but not in JE dict`);
  }
}

// CHECK 2 — every Japanese literal in the script (outside the JE block) is wrapped, a JE key, or allowed.
litRe.lastIndex = 0;
let m;
while ((m = litRe.exec(script))) {
  const off = m.index;
  if (off >= jeStart && off < jeEnd) continue;       // the dictionary itself
  const text = m[2];
  if (!JP.test(text)) continue;
  const before = script.slice(lineStart(off), off);
  if (WRAP.test(before)) continue;                   // tr/trf/L wrapped
  if (jeKeys.has(text)) continue;                    // registered for translation (used via tr elsewhere)
  if (allowAt(off)) continue;                        // explicit opt-out
  leaks.push(`script raw Japanese literal "${text.slice(0, 48)}" (not wrapped / not a JE key)`);
}

// CHECK 3 — static HTML attributes that surface text must be JE keys (applyStatic translates them).
const attrRe = /(title|placeholder|aria-label)="([^"]*)"/g;
let a;
while ((a = attrRe.exec(markup))) {
  if (JP.test(a[2]) && !jeKeys.has(a[2])) missing.push(`@${a[1]} "${a[2].slice(0, 48)}" not in JE dict (applyStatic can't translate it)`);
}

const fails = leaks.concat(missing);
if (fails.length) {
  console.error('NG: i18n coverage gate found ' + fails.length + ' uncovered string(s):\n  - ' + fails.join('\n  - '));
  process.exit(1);
}
console.log(`OK: i18n coverage holds — ${segs.length} display sinks + all script literals + HTML title/placeholder attrs route Japanese through tr()/trf()/L() with JE entries (${jeKeys.size} keys)`);
