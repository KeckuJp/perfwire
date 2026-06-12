// CI gate: extract the inline <script> from index.html and verify it parses.
// (The app is a single HTML file; this catches syntax errors without a DOM.)
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const m = html.match(/<script>([\s\S]*)<\/script>/);
if (!m) {
  console.error('NG: no <script> block found in index.html');
  process.exit(1);
}
try {
  new Function(m[1]); // parse only — never executed
  console.log('OK: index.html script parses (' + m[1].length + ' chars)');
} catch (e) {
  console.error('NG: syntax error in index.html script: ' + e.message);
  process.exit(1);
}
const init = html.match(/var INIT=(\{[\s\S]*?\});\r?\n/);
if (!init) {
  console.error('NG: embedded INIT not found');
  process.exit(1);
}
const data = JSON.parse(init[1]);
if (!Array.isArray(data.proposals) || !data.proposals.length) {
  console.error('NG: INIT.proposals missing/empty');
  process.exit(1);
}
console.log('OK: embedded INIT valid (' + data.proposals.length + ' proposals)');
