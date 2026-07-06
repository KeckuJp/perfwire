// CI gate: validate the plugin + marketplace manifests and their agreement,
// deterministically and without depending on the `claude` CLI being present.
// Mirrors what `claude plugin validate --strict` checks that matters for drift:
// required fields, marketplace description (strict requires it), version agreement,
// and that the skills path the plugin points at actually contains the skill.
import { readFileSync, existsSync } from 'node:fs';

const root = new URL('..', import.meta.url);
const fail = [];
const readJson = (rel) => {
  try { return JSON.parse(readFileSync(new URL(rel, root), 'utf8')); }
  catch (e) { fail.push(`cannot read/parse ${rel}: ${e.message}`); return null; }
};

const plugin = readJson('.claude-plugin/plugin.json');
const market = readJson('.claude-plugin/marketplace.json');

if (plugin) {
  if (plugin.name !== 'perfwire') fail.push(`plugin.json: name must be "perfwire" (got ${JSON.stringify(plugin.name)})`);
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(plugin.name || '')) fail.push('plugin.json: name must be kebab-case');
  if (!plugin.description) fail.push('plugin.json: description is required');
  if (!plugin.version) fail.push('plugin.json: version is required');
  const skillsPath = plugin.skills || 'skills';
  const skillFile = new URL(skillsPath.replace(/^\.\//, '') + '/perfwire/SKILL.md', root);
  if (!existsSync(skillFile)) fail.push(`plugin.json: skills path "${skillsPath}" has no perfwire/SKILL.md (looked at ${skillFile.pathname})`);
}

if (market) {
  if (market.name !== 'perfwire') fail.push(`marketplace.json: name must be "perfwire"`);
  if (!market.owner || !market.owner.name) fail.push('marketplace.json: owner.name is required');
  if (!market.description) fail.push('marketplace.json: description is required (strict validation fails without it)');
  const entry = (market.plugins || [])[0];
  if (!entry) fail.push('marketplace.json: plugins[] is empty');
  else {
    if (entry.name !== 'perfwire') fail.push('marketplace.json: plugins[0].name must be "perfwire"');
    if (!entry.source) fail.push('marketplace.json: plugins[0].source is required');
    if (plugin && entry.version !== plugin.version)
      fail.push(`version drift: marketplace entry ${entry.version} != plugin.json ${plugin.version}`);
  }
}

// README i18n structure gate (lightweight — existence + cross-link only, no content-sync
// enforcement: README.ja.md is allowed to lag one release behind per CONTRIBUTING.md's Tier
// policy, so this deliberately does NOT diff the two files or check the SYNC version number).
const readText = (rel) => {
  try { return readFileSync(new URL(rel, root), 'utf8'); }
  catch (e) { fail.push(`cannot read ${rel}: ${e.message}`); return null; }
};
const readmeEn = readText('README.md');
const readmeJa = readText('README.ja.md');
if (readmeEn && !/README\.ja\.md/.test(readmeEn.split('\n').slice(0, 3).join('\n')))
  fail.push('README.md: first 3 lines must link to README.ja.md (language switcher)');
if (readmeJa) {
  if (!/README\.md/.test(readmeJa.split('\n').slice(0, 3).join('\n')))
    fail.push('README.ja.md: first 3 lines must link back to README.md (language switcher)');
  if (!/SYNC:\s*README\.md\s*@/.test(readmeJa))
    fail.push('README.ja.md: missing a "SYNC: README.md @ <version>" marker near the top');
}

if (fail.length) {
  console.error('NG: manifest checks failed:\n  - ' + fail.join('\n  - '));
  process.exit(1);
}
console.log(`OK: plugin.json + marketplace.json valid and in agreement (v${plugin.version}); skill found at ${plugin.skills || 'skills'}/perfwire/SKILL.md; README.md/README.ja.md cross-linked`);
