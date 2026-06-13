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
const ERC_SRC = grab(/function ercAudit\(\)\{[\s\S]*?stripShorts:stripShorts\};\}/, 'ercAudit');
const STRIP_SRC = grab(/function stripSegs\([\s\S]*?return segs;\}/, 'stripSegs');

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
const stripSegs = new Function('key', STRIP_SRC + '\nreturn stripSegs;')(key);
function runJS(D) {
  const names = ['D', 'CFG', 'DEFCFG', 'key', 'cheb', 'clsOf', 'cdef', 'partLeads', 'cols', 'rows', 'stripSegs'];
  const vals = [D, CFG, DEFCFG, key, cheb, clsOf, cdef, partLeads, D.grid.cols, D.grid.rows, stripSegs];
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
  stripShorts: a => JSON.stringify((a || []).map(s => ({ seg: s.segment, nets: s.nets.slice().sort() }))
    .sort((x, y) => JSON.stringify(x) < JSON.stringify(y) ? -1 : 1)),
};

// synthetic stripboard fixtures so the golden test also covers strip connectivity / shorts / cuts
const STRIP = (cuts) => ({
  grid: { cols: 6, rows: 3, type: 'strip', stripAxis: 'row' }, netColors: { A: '#f00', B: '#0f0' },
  leads: { 'P1.a': { net: 'A', at: [1, 1] }, 'P1.b': { net: 'A', at: [1, 3] },
           'P2.a': { net: 'B', at: [4, 1] }, 'P2.b': { net: 'B', at: [4, 3] } },
  parts: [{ id: 'P1', kind: 'r', leads: [[1, 1], [1, 3]], leadNames: ['P1.a', 'P1.b'] },
          { id: 'P2', kind: 'r', leads: [[4, 1], [4, 3]], leadNames: ['P2.a', 'P2.b'] }],
  padBridges: [], wires: [], blockedHoles: [], trackCuts: cuts,
});
// Config-agreement: the two threshold files (editor DEFCFG camelCase vs solver
// config.example.json snake_case) must encode the SAME EE limits, or a gate-affecting
// field like wire-length could drift between the engines while ercAudit parity stays green.
const cfgFails = [];
const PYCFG = JSON.parse(readFileSync(join(ROOT, 'config.example.json'), 'utf8'));
const cmap = { HIZ: 'HIZ', SIG: 'SIG', OUT: 'OUT', PWR: 'PWR' };
for (const c of Object.keys(cmap)) {
  const j = DEFCFG.classes[c], p = (PYCFG.net_classes || {})[c] || {};
  const cmp = [['maxWire', 'max_wire_holes'], ['adjPen', 'adj_penalty'], ['keepHoles', 'keep_away_holes']];
  for (const [jk, pk] of cmp) if (j[jk] !== p[pk]) cfgFails.push(`net_classes.${c}.${jk}(${j[jk]}) != config.${pk}(${p[pk]})`);
  if (JSON.stringify((j.nets || []).slice().sort()) !== JSON.stringify((p.nets || []).slice().sort())) cfgFails.push(`net_classes.${c}.nets differ`);
  if (JSON.stringify((j.keepAway || []).slice().sort()) !== JSON.stringify((p.keep_away_from || []).slice().sort())) cfgFails.push(`net_classes.${c}.keepAway differ`);
}
if (DEFCFG.rules.maxJoints !== PYCFG.rules.max_joints_per_pad) cfgFails.push('rules.maxJoints != max_joints_per_pad');
if (JSON.stringify((DEFCFG.rules.singleLeadAllow || []).slice().sort()) !== JSON.stringify((PYCFG.rules.single_lead_allowlist || []).slice().sort())) cfgFails.push('single-lead allowlist differ');
if (JSON.stringify(DEFCFG.railRank) !== JSON.stringify(PYCFG.rail_rank)) cfgFails.push('rail_rank differ');
if (JSON.stringify(DEFCFG.powerEntry) !== JSON.stringify(PYCFG.power_entry)) cfgFails.push('power_entry differ');
const jdec = (DEFCFG.decoupling || []).map(d => d.cap + ':' + d.pin + ':' + d.max).sort();
const pdec = (PYCFG.decoupling || []).map(d => d.cap + ':' + d.pin + ':' + d.max_holes).sort();
if (JSON.stringify(jdec) !== JSON.stringify(pdec)) cfgFails.push('decoupling list differ');

const sample = JSON.parse(readFileSync(join(ROOT, 'examples', 'client-hardware_tap_buffer.json'), 'utf8'));
// openNets/powerReach depend on the solver's auto-routing (Python adds jumpers, the editor
// evaluates the as-given wiring), so they only match on fully-wired inputs (the sample proposals).
// The synthetic strip fixtures carry no jumpers -> skip those two fields for them.
const WIRING_DEP = ['openNets', 'powerReach'];
const cases = sample.proposals.map(p => ({ name: p.name, state: p.state, skip: [] }))
  .concat([{ name: 'strip:short', state: STRIP([]), skip: WIRING_DEP },
           { name: 'strip:cut', state: STRIP([[[3, 1], [4, 1]]]), skip: WIRING_DEP }]);
const tmp = mkdtempSync(join(tmpdir(), 'pw-parity-'));
const failures = [];
for (const prop of cases) {
  const js = runJS(JSON.parse(JSON.stringify(prop.state)));
  const stateP = join(tmp, 'state.json'), outP = join(tmp, 'out.json');
  writeFileSync(stateP, JSON.stringify(prop.state));
  execFileSync(PY, [join(ROOT, 'solver.py'), stateP, '--config', join(ROOT, 'config.example.json'), '-o', outP], { cwd: ROOT });
  const ee = JSON.parse(readFileSync(outP, 'utf8')).ee;
  for (const [f, norm] of Object.entries(FIELDS)) {
    if ((prop.skip || []).includes(f)) continue;
    const a = norm(js[f]), b = norm(ee[f]);
    if (JSON.stringify(a) !== JSON.stringify(b))
      failures.push(`${prop.name} :: ${f}\n    JS    = ${a}\n    PY    = ${b}`);
  }
}
const allFails = cfgFails.map(f => 'config-drift :: ' + f).concat(failures);
if (allFails.length) {
  console.error('NG: JS<->Python parity / config mismatch:\n  - ' + allFails.join('\n  - '));
  process.exit(1);
}
console.log(`OK: JS<->Python ERC parity holds across ${cases.length} cases (${Object.keys(FIELDS).length} fields) + config files agree on EE limits`);
