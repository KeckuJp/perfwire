// Golden parity test: the in-browser ercAudit (JS) and solver.py (Python) must
// agree on every gate-affecting ERC field for each bundled sample proposal.
// This locks the two implementations (and implicitly the two config files —
// index.html DEFCFG vs config.example.json) against drift.
//
// Run: node tools/parity_check.mjs   (uses $PERFWIRE_PYTHON or `python`)
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url)).replace(/[\\/]tools$/, '');
const html = readFileSync(join(ROOT, 'index.html'), 'utf8');
const PY = process.env.PERFWIRE_PYTHON || 'python';

function grab(re, label) {
  const m = html.match(re);
  if (!m) throw new Error('parity_check: could not extract ' + label);
  return m[0];
}
// Pull DEFCFG + the helpers ercAudit needs + ercAudit itself, straight from index.html.
const DEFCFG_SRC = grab(/var DEFCFG=[\s\S]*?\]\};/, 'DEFCFG');
const ERC_SRC = grab(/function ercAudit\(\)\{[\s\S]*?undrivenNets:undriven\};\}/, 'ercAudit');

function key(p) { return p[0] + ',' + p[1]; }
function cheb(a, b) { return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])); }
function partLeads(p) {
  const out = [];
  if (p.kind === 'ic') Object.keys(p.pins).forEach(k => out.push({ name: p.id + '.' + k, pos: p.pins[k] }));
  else (p.leadNames || []).forEach((nm, i) => out.push({ name: nm, pos: p.leads[i] }));
  return out;
}
const sandbox = {};
new Function('S', DEFCFG_SRC + '\nS.DEFCFG=DEFCFG;')(sandbox);
const DEFCFG = sandbox.DEFCFG;
const CFG = DEFCFG;
function clsOf(net) { for (const c in CFG.classes) if (CFG.classes[c].nets.indexOf(net) >= 0) return c; return null; }
function cdef(net) { const c = clsOf(net); return c ? CFG.classes[c] : { maxWire: 99, adjPen: 1, keepAway: [], keepHoles: 0 }; }
function runJS(D) {
  const names = ['D', 'CFG', 'DEFCFG', 'key', 'cheb', 'clsOf', 'cdef', 'partLeads'];
  const vals = [D, CFG, DEFCFG, key, cheb, clsOf, cdef, partLeads];
  return new Function(...names, ERC_SRC.replace(/^function ercAudit\(\)\{/, '').replace(/\}$/, ''))(...vals);
}

// Normalizers so shape differences (extra fields) don't matter, only VALUES do.
const N = {
  list: a => JSON.stringify((a || []).slice().sort()),
  multi: a => JSON.stringify((a || []).map(m => ({ net: m.net, pins: m.pins.slice().sort() })).sort((x, y) => x.net < y.net ? -1 : 1)),
  okmap: (a, k) => JSON.stringify(Object.fromEntries((a || []).map(x => [x[k], !!x.ok]).sort())),
  count: a => (a || []).length,
};
const FIELDS = {
  openNets: N.list, singleLeadNets: N.list, unconnectedLeads: N.list, duplicateIds: N.list,
  unclassifiedNets: N.list, floatingPowerPins: N.list, undrivenNets: N.list, multipleDrivers: N.multi,
  polarity: a => N.okmap(a, 'part'), powerReach: a => N.okmap(a, 'net'), keepAway: N.count,
};

const sample = JSON.parse(readFileSync(join(ROOT, 'examples', 'client-hardware_tap_buffer.json'), 'utf8'));
const tmp = mkdtempSync(join(tmpdir(), 'pw-parity-'));
const failures = [];
for (const prop of sample.proposals) {
  const js = runJS(JSON.parse(JSON.stringify(prop.state)));
  const stateP = join(tmp, 'state.json'), outP = join(tmp, 'out.json');
  writeFileSync(stateP, JSON.stringify(prop.state));
  execFileSync(PY, [join(ROOT, 'solver.py'), stateP, '--config', join(ROOT, 'config.example.json'), '-o', outP], { cwd: ROOT });
  const ee = JSON.parse(readFileSync(outP, 'utf8')).ee;
  for (const [f, norm] of Object.entries(FIELDS)) {
    const a = norm(js[f]), b = norm(ee[f]);
    if (JSON.stringify(a) !== JSON.stringify(b))
      failures.push(`${prop.name} :: ${f}\n    JS    = ${a}\n    PY    = ${b}`);
  }
}
if (failures.length) {
  console.error('NG: JS<->Python ERC parity mismatch:\n  - ' + failures.join('\n  - '));
  process.exit(1);
}
console.log(`OK: JS<->Python ERC parity holds across ${sample.proposals.length} proposals (${Object.keys(FIELDS).length} fields each)`);
