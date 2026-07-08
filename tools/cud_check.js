// Manual CUD (Color Universal Design) check for perfwire's NETPAL net-color palette.
// Not part of the 7 CI gates (see AGENTS.md) -- run by hand whenever NETPAL is edited.
//
// Run: node tools/cud_check.js
//
// What it does: simulates protanopia (protan) and deuteranopia (deutan) per Viénot et al.
// 1999, then computes pairwise CIELAB dE76 for every color pair in NETPAL, for the normal
// vision / protan / deutan conditions. Reports the worst (most confusable) pair per mode,
// both across all 12 colors and across just the first 8 (the colors netColor() actually
// assigns first, in index order -- see index.html's NETPAL comment).
//
// IMPORTANT LMS-matrix note (read before touching the simulate() coefficients below):
// the Viénot dichromacy-simulation coefficients used here (2.02344 / -2.52581 for protan,
// 0.494207 / 1.24827 for deutan) are only valid when paired with an LMS space matched to
// their derivation -- the "raw" Hunt-Pointer-Estevez-style matrix below (rows summing to
// ~65.5 / ~34.5 / ~1.68, NOT normalized to map white to (1,1,1)). An earlier draft of this
// script instead used an LMS matrix normalized so white maps to (1,1,1); that matrix is
// *not* a uniform per-row rescaling of the one below (verified: row ratios were
// 0.018/0.015/0.011 and 0.045/0.028/0.022 -- not constant), yet it reused the same
// simulation coefficients. That mismatch produced spurious near-total collapse for some
// hue pairs (a claimed deutan dE~0.6 for a pair that independent re-verification -- both a
// correctly-paired Viénot computation and an entirely different method, Machado et al. 2009
// applied directly in linear RGB -- put at dE~13-24, i.e. clearly distinguishable). If you
// change the matrix below, re-derive or re-verify the simulate() coefficients against it;
// don't assume they transfer.
function hex2rgb(h) { h = h.slice(1); return [parseInt(h.slice(0, 2), 16) / 255, parseInt(h.slice(2, 4), 16) / 255, parseInt(h.slice(4, 6), 16) / 255]; }
function s2l(c) { return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
function l2s(c) { c = Math.max(0, Math.min(1, c)); return c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055; }
// Viénot 1999 linear RGB -> LMS (Hunt-Pointer-Estevez-derived, NOT white-normalized).
function rgb2lms(r, g, b) {
  return [
    17.8824 * r + 43.5161 * g + 4.11935 * b,
    3.45565 * r + 27.1554 * g + 3.86714 * b,
    0.0299566 * r + 0.184309 * g + 1.46709 * b];
}
// Exact inverse of rgb2lms above.
function lms2rgb(L, M, S) {
  return [
    0.0809444479 * L - 0.130504409 * M + 0.116721066 * S,
    -0.0102485335 * L + 0.0540193266 * M - 0.113614708 * S,
    -0.000365296938 * L - 0.00412161469 * M + 0.693511405 * S];
}
function simulate(rgb, type) {
  var lin = rgb.map(s2l), lms = rgb2lms(lin[0], lin[1], lin[2]);
  var L = lms[0], M = lms[1], S = lms[2];
  if (type === 'protan') { L = 2.02344 * M - 2.52581 * S; }
  else if (type === 'deutan') { M = 0.494207 * L + 1.24827 * S; }
  return lms2rgb(L, M, S).map(l2s);
}
function rgb2lab(rgb) {
  var lin = rgb.map(s2l);
  var X = 0.4124564 * lin[0] + 0.3575761 * lin[1] + 0.1804375 * lin[2];
  var Y = 0.2126729 * lin[0] + 0.7151522 * lin[1] + 0.0721750 * lin[2];
  var Z = 0.0193339 * lin[0] + 0.1191920 * lin[1] + 0.9503041 * lin[2];
  var xn = 0.95047, yn = 1.0, zn = 1.08883;
  function f(t) { return t > 0.008856 ? Math.cbrt(t) : (7.787 * t + 16 / 116); }
  var fx = f(X / xn), fy = f(Y / yn), fz = f(Z / zn);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}
function dE(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); }

// Keep this literal in sync with NETPAL in index.html (`var NETPAL=[` -- search for it).
var PAL = ['#7d73de', '#b7bf22', '#22bf9f', '#bf2241', '#73b8de', '#9513ec', '#bf2290', '#bf6022', '#deae73', '#bf2268', '#de7378', '#7398de'];

function report(list, label) {
  console.log('\n=== ' + label + ' (' + list.length + ' colors) ===');
  ['normal', 'protan', 'deutan'].forEach(function (mode) {
    var cols = list.map(function (h) { var rgb = hex2rgb(h); return mode === 'normal' ? rgb : simulate(rgb, mode); });
    var labs = cols.map(rgb2lab);
    var pairs = [];
    for (var i = 0; i < list.length; i++) for (var j = i + 1; j < list.length; j++) pairs.push({ i: i, j: j, d: dE(labs[i], labs[j]) });
    pairs.sort(function (a, b) { return a.d - b.d; });
    console.log('  ' + mode + ': worst pair dE=' + pairs[0].d.toFixed(1) + '  [' + pairs[0].i + ']' + list[pairs[0].i] + ' vs [' + pairs[0].j + ']' + list[pairs[0].j]);
    console.log('  ' + mode + ': next-worst 4:');
    pairs.slice(1, 5).forEach(function (p) { console.log('    dE=' + p.d.toFixed(1) + '  [' + p.i + ']' + list[p.i] + ' vs [' + p.j + ']' + list[p.j]); });
  });
}
report(PAL.slice(0, 8), 'first 8 (typical board, netColor assignment order)');
report(PAL, 'all 12');
