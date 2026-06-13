// Full-ee headless parity: loads each sample proposal into the real editor (index.html)
// via a #z= deep link, reads the structured ee the editor dumps into #eedump, and compares
// it to solver.py's ee — covering the GEOMETRY fields (wireLength / decoupling / padJoints /
// bodyOverlaps / grounding) that the pure-Node parity_check.mjs cannot run (they need geom()).
// Skips gracefully (exit 0) if no headless Chrome is available, so CI never breaks on it.
import { readFileSync, writeFileSync, mkdtempSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { deflateRawSync } from 'node:zlib';

const ROOT = dirname(fileURLToPath(import.meta.url)).replace(/[\\/]tools$/, '');
const PY = process.env.PERFWIRE_PYTHON || 'python';
const CHROME_CANDIDATES = [process.env.CHROME, 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
  'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].filter(Boolean);

function findChrome() {
  for (const c of CHROME_CANDIDATES) {
    try { if (c.includes('/') || c.includes('\\')) { if (existsSync(c)) return c; } else { execFileSync(c, ['--version'], { stdio: 'ignore' }); return c; } } catch { }
  }
  return null;
}
const CHROME = findChrome();
if (!CHROME) { console.log('SKIP: no headless Chrome found (headless ee-parity not run)'); process.exit(0); }

function deepLink(state) {
  const b64 = deflateRawSync(Buffer.from(JSON.stringify(state), 'utf8'), { level: 9 })
    .toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return pathToFileURL(join(ROOT, 'index.html')).href + '#z=' + b64;
}
function renderEE(url) {
  const tmp = mkdtempSync(join(tmpdir(), 'pw-hl-'));
  const dom = execFileSync(CHROME, ['--headless=new', '--disable-gpu', '--no-first-run', '--dump-dom',
    '--virtual-time-budget=6000', '--user-data-dir=' + tmp, url], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  const m = dom.match(/id="eedump"[^>]*>(.*?)<\/div>/s);
  if (!m) throw new Error('no #eedump in rendered DOM');
  return JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
}
function solverEE(state) {
  const tmp = mkdtempSync(join(tmpdir(), 'pw-sl-'));
  const sp = join(tmp, 's.json'), op = join(tmp, 'o.json');
  writeFileSync(sp, JSON.stringify(state));
  execFileSync(PY, [join(ROOT, 'solver.py'), sp, '--config', join(ROOT, 'config.example.json'), '-o', op], { cwd: ROOT });
  return JSON.parse(readFileSync(op, 'utf8')).ee;
}
const norm = {
  wireLength: a => JSON.stringify((a || []).map(x => x.net + ':' + x.holes + ':' + (x.ok ? 1 : 0)).sort()),
  decoupling: a => JSON.stringify((a || []).map(x => x.cap + '>' + x.pin + ':' + x.holes + ':' + (x.ok ? 1 : 0)).sort()),
  padJoints: a => (a || []).length,
  bodyOverlaps_ng: ee => Array.isArray(ee.bodyOverlaps) ? ee.bodyOverlaps.filter(o => o.sev === 'ng').length : (ee.bodyOverlaps || {}).ng,
  bodyOverlaps_wr: ee => Array.isArray(ee.bodyOverlaps) ? ee.bodyOverlaps.filter(o => o.sev !== 'ng').length : (ee.bodyOverlaps || {}).wr,
  grounding: a => JSON.stringify((a || []).map(x => x.net + ':' + x.topology + ':' + x.maxDepth + ':' + (x.daisyReturn ? 1 : 0)).sort()),
};

const sample = JSON.parse(readFileSync(join(ROOT, 'examples', 'client-hardware_tap_buffer.json'), 'utf8'));
const fails = [];
for (const prop of sample.proposals) {
  const js = renderEE(deepLink(prop.state));
  const py = solverEE(prop.state);
  for (const f of ['wireLength', 'decoupling', 'grounding']) {
    if (norm[f](js[f]) !== norm[f](py[f])) fails.push(`${prop.name} :: ${f}\n    JS=${norm[f](js[f])}\n    PY=${norm[f](py[f])}`);
  }
  if (norm.padJoints(js.padJoints) !== norm.padJoints(py.padJoints)) fails.push(`${prop.name} :: padJoints count ${norm.padJoints(js.padJoints)} != ${norm.padJoints(py.padJoints)}`);
  if (norm.bodyOverlaps_ng(js) !== norm.bodyOverlaps_ng(py)) fails.push(`${prop.name} :: bodyOverlaps.ng ${norm.bodyOverlaps_ng(js)} != ${norm.bodyOverlaps_ng(py)}`);
  if (norm.bodyOverlaps_wr(js) !== norm.bodyOverlaps_wr(py)) fails.push(`${prop.name} :: bodyOverlaps.wr ${norm.bodyOverlaps_wr(js)} != ${norm.bodyOverlaps_wr(py)}`);
  if (js.fabReady !== py.fabReady) fails.push(`${prop.name} :: fabReady ${js.fabReady} != ${py.fabReady}`);
}
if (fails.length) { console.error('NG: headless ee parity (geometry fields):\n  - ' + fails.join('\n  - ')); process.exit(1); }
console.log(`OK: headless full-ee parity (incl. geometry) holds across ${sample.proposals.length} proposals`);
