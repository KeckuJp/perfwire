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
function resolvePy() {  // pick a Python that actually runs; on Windows `python`/`python3` may be the MS Store stub
  for (const c of [process.env.PERFWIRE_PYTHON, 'python3', 'python'].filter(Boolean)) {
    try { execFileSync(c, ['-c', 'import sys'], { stdio: 'ignore' }); return c; } catch { /* try next */ }
  }
  console.error('parity_check: no working Python 3 found. Set PERFWIRE_PYTHON to a real interpreter ' +
    '(on Windows `python`/`python3` may be the Microsoft Store stub — use a full path, e.g. PERFWIRE_PYTHON=C:/path/to/python.exe).');
  process.exit(1);
}
const PY = resolvePy();

function grab(re, label) {
  const m = html.match(re);
  if (!m) throw new Error('parity_check: could not extract ' + label);
  return m[0];
}
// Pull DEFCFG + the helpers ercAudit needs + ercAudit itself, straight from index.html.
const DEFCFG_SRC = grab(/var DEFCFG=[\s\S]*?\]\};/, 'DEFCFG');
const ERC_SRC = grab(/function ercAudit\(\)\{[\s\S]*?bridgeDangle:bdang\};\}/, 'ercAudit');
const STRIP_SRC = grab(/function stripSegs\([\s\S]*?return segs;\}/, 'stripSegs');
const BOARDLINKS_SRC = grab(/function boardLinks\([\s\S]*?return \[\];\}/, 'boardLinks');

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
const boardLinks = new Function('key', 'stripSegs', BOARDLINKS_SRC + '\nreturn boardLinks;')(key, stripSegs);
function runJS(D) {
  const names = ['D', 'CFG', 'DEFCFG', 'key', 'cheb', 'clsOf', 'cdef', 'partLeads', 'cols', 'rows', 'stripSegs', 'boardLinks'];
  const vals = [D, CFG, DEFCFG, key, cheb, clsOf, cdef, partLeads, D.grid.cols, D.grid.rows, stripSegs, boardLinks];
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
  resistorPower: a => JSON.stringify((a || []).map(x => ({ part: x.part, ok: !!x.ok })).sort((p, q) => p.part < q.part ? -1 : 1)),
  decouplingValueWarn: a => JSON.stringify((a || []).map(x => x.cap).sort()),
  pinConflicts: a => JSON.stringify((a || []).map(x => x.net).sort()),
  clampRisk: a => JSON.stringify((a || []).map(x => ({ pin: x.pin, via: (x.via || []).slice().sort() })).sort((p, q) => p.pin < q.pin ? -1 : 1)),
  netMerge: a => JSON.stringify((a || []).map(m => m.nets.slice().sort()).sort((x, y) => JSON.stringify(x) < JSON.stringify(y) ? -1 : 1)),
  railShort: a => JSON.stringify((a || []).map(x => ({ part: x.part, ok: !!x.ok })).sort((p, q) => p.part < q.part ? -1 : 1)),
  railReff: a => JSON.stringify((a || []).map(x => ({ pair: x.pair, ok: !!x.ok })).sort((p, q) => JSON.stringify(p.pair) < JSON.stringify(q.pair) ? -1 : 1)),
  bridgeDangle: a => JSON.stringify((a || []).map(x => ({ net: x.net, tap: x.tap, bridgeTo: x.bridgeTo })).sort((p, q) => JSON.stringify(p) < JSON.stringify(q) ? -1 : 1)),
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
// value-aware fixture: intentionally trips resistorPower (R across V3V3-GND, 33ohm -> 0.33W > 0.25),
// decouplingValueWarn (C3 is a listed bypass cap with 10uF > 1uF), pinConflicts (net NET carries both an
// out driver and a pwr source), and multipleDrivers (two out drivers on NET = output contention).
// Proves these gate-affecting fields on the POPULATED path, not just empty.
const VALUE = {
  grid: { cols: 8, rows: 6, type: 'perf' }, netColors: { V3V3: '#f00', GND: '#000', NET: '#0a0' },
  leads: {
    'R9.a': { net: 'V3V3', at: [1, 1] }, 'R9.b': { net: 'GND', at: [1, 3] },
    'C3.p': { net: 'V3V3', at: [3, 1] }, 'C3.n': { net: 'GND', at: [3, 3] },
    'W.DRV': { net: 'NET', at: [6, 1], role: 'out' }, 'W.DRV2': { net: 'NET', at: [6, 5], role: 'out' },
    'W.PWR': { net: 'NET', at: [6, 3], role: 'pwr' },
  },
  parts: [
    { id: 'R9', kind: 'r', leads: [[1, 1], [1, 3]], leadNames: ['R9.a', 'R9.b'], value: 33 },
    { id: 'C3', kind: 'disc', leads: [[3, 1], [3, 3]], leadNames: ['C3.p', 'C3.n'], value: 1e-5 },
  ],
  padBridges: [], wires: [], blockedHoles: [], trackCuts: [],
};
// effective-short fixture: a 2-resistor SERIES chain V3V3->MIDX->GND (22+22 -> R_eff=44ohm -> 75mA > 50)
// trips railReff but NOT railShort (each resistor touches only ONE rail). Proves the full-network R_eff
// solve on the populated case (the gap per-resistor railShort misses). Integer values, clear 50mA margin.
const EFFSHORT = {
  grid: { cols: 10, rows: 6, type: 'perf' }, netColors: { V3V3: '#f00', GND: '#000', MIDX: '#0a0' },
  leads: {
    'R1.a': { net: 'V3V3', at: [1, 1] }, 'R1.b': { net: 'MIDX', at: [1, 3] },
    'R2.a': { net: 'MIDX', at: [3, 1] }, 'R2.b': { net: 'GND', at: [3, 3] },
  },
  parts: [
    { id: 'R1', kind: 'r', leads: [[1, 1], [1, 3]], leadNames: ['R1.a', 'R1.b'], value: 22 },
    { id: 'R2', kind: 'r', leads: [[3, 1], [3, 3]], leadNames: ['R2.a', 'R2.b'], value: 22 },
  ],
  padBridges: [], wires: [], blockedHoles: [], trackCuts: [],
};
// cross-wired (十字配線/mesh) board: every hole bonded to its 4 neighbors -> the WHOLE grid is one net,
// so a design routed assuming isolation shorts V3V3 to GND through the substrate. As-shipped (no cuts)
// netMerge must fire; with a cut-ring isolating the V3V3 island, it must clear. Proves intrinsic-link
// union + subtractive cut model, in BOTH engines (boardLinks runs identically).
const MESH = (cuts) => ({
  grid: { cols: 4, rows: 4, type: 'mesh' }, netColors: { V3V3: '#f00', GND: '#000' },
  leads: { 'P.v': { net: 'V3V3', at: [1, 1] }, 'P.g': { net: 'GND', at: [4, 4] } },
  parts: [{ id: 'P', kind: 'r', leads: [[1, 1], [4, 4]], leadNames: ['P.v', 'P.g'] }],
  padBridges: [], wires: [], blockedHoles: [], trackCuts: cuts,
});
// a ring of cuts isolating the [1,1] V3V3 hole from the rest of the mesh -> V3V3/GND no longer common
const MESH_ISLAND = MESH([[[1, 1], [2, 1]], [[1, 1], [1, 2]]]);
// breadboard-pattern: top/bottom rows are continuous power-rail strips; V+ and GND land on the two rails
// -> the rails short them (netMerge) while the center column segments stay distinct.
const BREADBOARD = {
  grid: { cols: 5, rows: 4, type: 'breadboard', segLen: 2, railRows: [1, 4] }, netColors: { V3V3: '#f00', GND: '#000', SIG: '#0a0' },
  leads: { 'A.v': { net: 'V3V3', at: [1, 1] }, 'A.g': { net: 'GND', at: [5, 1] }, 'B.s': { net: 'SIG', at: [2, 2] } },
  parts: [{ id: 'A', kind: 'r', leads: [[1, 1], [5, 1]], leadNames: ['A.v', 'A.g'] },
          { id: 'B', kind: 'r', leads: [[2, 2], [2, 3]], leadNames: ['B.s', 'B.s2'] }],
  padBridges: [], wires: [], blockedHoles: [], trackCuts: [],
};
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
if (JSON.stringify(DEFCFG.railVolts || null) !== JSON.stringify(PYCFG.rail_volts || null)) cfgFails.push('rail_volts differ');
if ((DEFCFG.railShortMa ?? 50) !== (PYCFG.rail_short_ma ?? 50)) cfgFails.push(`railShortMa(${DEFCFG.railShortMa}) != rail_short_ma(${PYCFG.rail_short_ma})`);
if (JSON.stringify(DEFCFG.powerEntry) !== JSON.stringify(PYCFG.power_entry)) cfgFails.push('power_entry differ');
if (JSON.stringify(DEFCFG.referenceRails || null) !== JSON.stringify(PYCFG.reference_rails || null)) cfgFails.push('reference_rails differ');
const jdec = (DEFCFG.decoupling || []).map(d => d.cap + ':' + d.pin + ':' + d.max).sort();
const pdec = (PYCFG.decoupling || []).map(d => d.cap + ':' + d.pin + ':' + d.max_holes).sort();
if (JSON.stringify(jdec) !== JSON.stringify(pdec)) cfgFails.push('decoupling list differ');
// Physical footprints + cited source: the editor reads dims/source from DEFCFG.physical
// (legend span-range + provenance), the solver from config.example.json.physical. If they
// drift, the legend/spans and the solver disagree on the same part — and the dimension
// citation shown to the user no longer matches what the solver used. Lock both (there is
// no separate PHYSREF table any more; source lives next to the dims it cites).
const PHYS_DIM = [['bodyLen', 'body_len_mm'], ['bodyWid', 'body_wid_mm'], ['maxSpan', 'max_span_mm'], ['dia', 'dia_mm'], ['bend', 'bend_margin_mm']];
for (const k of ['r', 'film', 'disc', 'elec', 'ic']) {
  const j = DEFCFG.physical[k] || {}, p = (PYCFG.physical || {})[k] || {};
  if (j.source !== p.source) cfgFails.push(`physical.${k}.source(${JSON.stringify(j.source)}) != config(${JSON.stringify(p.source)})`);
  for (const [jk, pk] of PHYS_DIM) if (j[jk] !== undefined && j[jk] !== p[pk]) cfgFails.push(`physical.${k}.${jk}(${j[jk]}) != config.${pk}(${p[pk]})`);
}
// Placement profiles (the plain-language goals the editor dropdown and `solver.py --profile`
// share): both files must agree on each goal's NAME and its full weight vector, or the agent and
// the human would mean different layouts by the same goal name. The editor uses camelCase weight
// keys, the solver snake_case — map and compare every one.
const PROF_WMAP = { bridgeBonus: 'bridge_bonus', wireLen: 'wire_len', cautionBase: 'caution_base', hizMult: 'hiz_mult', keepAwayPen: 'keep_away_penalty', diagPen: 'diag_penalty', spanPen: 'span_penalty', standPen: 'standing_penalty' };
const jprof = DEFCFG.profiles || {}, pprof = PYCFG.placement_profiles || {};
if (Object.keys(jprof).length !== Object.keys(pprof).length) cfgFails.push(`profile count ${Object.keys(jprof).length} != config ${Object.keys(pprof).length}`);
for (const k of Object.keys(jprof)) {
  if (!pprof[k]) { cfgFails.push(`profile ${k} missing in config`); continue; }
  if (jprof[k].ja !== pprof[k].ja) cfgFails.push(`profile.${k}.ja(${jprof[k].ja}) != config(${pprof[k].ja})`);
  const jw = jprof[k].weights || {}, pw = pprof[k].weights || {};
  for (const [jk, pk] of Object.entries(PROF_WMAP)) if (jw[jk] !== pw[pk]) cfgFails.push(`profile.${k}.${jk}(${jw[jk]}) != config.${pk}(${pw[pk]})`);
}
if (DEFCFG.defaultProfile !== PYCFG.default_profile) cfgFails.push(`defaultProfile(${DEFCFG.defaultProfile}) != config.default_profile(${PYCFG.default_profile})`);

const sample = JSON.parse(readFileSync(join(ROOT, 'examples', 'client-hardware_tap_buffer.json'), 'utf8'));
// openNets/powerReach depend on the solver's auto-routing (Python adds jumpers, the editor
// evaluates the as-given wiring), so they only match on fully-wired inputs (the sample proposals).
// The synthetic strip fixtures carry no jumpers -> skip those two fields for them.
const WIRING_DEP = ['openNets', 'powerReach', 'netMerge', 'bridgeDangle'];
// substrate-short fixtures: netMerge comes purely from intrinsic board-links (no wires), so it is
// computed identically by both engines and MUST be compared (and proven non-empty) -> keep netMerge OUT of skip.
const WIRING_DEP_NOMERGE = ['openNets', 'powerReach', 'bridgeDangle'];
const cases = sample.proposals.map(p => ({ name: p.name, state: p.state, skip: [] }))
  .concat([{ name: 'strip:short', state: STRIP([]), skip: WIRING_DEP },
           { name: 'strip:cut', state: STRIP([[[3, 1], [4, 1]]]), skip: WIRING_DEP },
           { name: 'value:over-power+bypass+pinconflict', state: VALUE, skip: WIRING_DEP },
           { name: 'effshort:series-rail', state: EFFSHORT, skip: WIRING_DEP },
           { name: 'mesh:uncut-short', state: MESH([]), skip: WIRING_DEP_NOMERGE },
           { name: 'mesh:cut-island', state: MESH_ISLAND, skip: WIRING_DEP_NOMERGE },
           { name: 'breadboard:rail-short', state: BREADBOARD, skip: WIRING_DEP_NOMERGE }]);
// fixture-completeness: these gate-affecting fields are easy to ship "always empty" (they need
// value/role/rail inputs). Require at least one case to exercise each on the non-empty path,
// so a regression that silently zeroes them out can't pass the golden test.
const MUST_COVER = ['resistorPower', 'decouplingValueWarn', 'pinConflicts', 'multipleDrivers', 'stripShorts', 'clampRisk', 'railShort', 'railReff'];
const coverage = Object.fromEntries(MUST_COVER.map(f => [f, 0]));
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
  for (const f of MUST_COVER) if ((ee[f] || []).length > 0) coverage[f]++;
  // substrate-short direction: an uncut mesh board must merge nets; a cut-isolated one must not.
  if (prop.name === 'mesh:uncut-short' && !((ee.netMerge || []).length > 0))
    failures.push('mesh:uncut-short :: expected ee.netMerge non-empty (uncut 十字 board should short nets) but got []');
  if (prop.name === 'mesh:cut-island' && (ee.netMerge || []).length > 0)
    failures.push(`mesh:cut-island :: expected ee.netMerge empty (cut ring isolates V3V3) but got ${JSON.stringify(ee.netMerge)}`);
}
const uncovered = MUST_COVER.filter(f => coverage[f] === 0);
const covFails = uncovered.map(f => `fixture-coverage :: no case exercises ee.${f} on the non-empty path`);
const allFails = cfgFails.map(f => 'config-drift :: ' + f).concat(covFails).concat(failures);
if (allFails.length) {
  console.error('NG: JS<->Python parity / config mismatch:\n  - ' + allFails.join('\n  - '));
  process.exit(1);
}
console.log(`OK: JS<->Python ERC parity holds across ${cases.length} cases (${Object.keys(FIELDS).length} fields) + config files agree on EE limits + ${MUST_COVER.length} fields covered non-empty`);
