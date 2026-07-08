# AGENTS.md

This file defines repository-level instructions for AI coding agents working **on**
perfwire (contributors). It is not loaded for plugin *consumers* — a Claude Code user
who installs the perfwire plugin never sees this file; only someone who opens this
repository does. Frame everything here as contributor guidance.

## Repository purpose

This repository is a **frontend-app** (single-file browser editor) plus a Python CLI:
an AI-assisted planner/auditor for hand-soldered perfboard (universal board /
protoboard) wiring, distributed as a Claude Code plugin.

- `index.html` — single self-contained browser drag editor with an embedded JS solver/ERC.
- `solver.py` — Python **stdlib-only** CLI that places/routes/audits the same board model.
- `tools/*` — CI gates and the agent↔human round-trip tools (`make_link.py` / `read_link.py`).
- `config.example.json` — EE/physical constraint config consumed by `solver.py`.
- `.claude/skills/perfwire/SKILL.md` — the product skill (the consumer-facing entrypoint).

See `README.md` for product overview (and Quick start) and `.claude/skills/perfwire/SKILL.md`
for the persona routing / round-trip design that governs runtime behavior. To preview locally,
open `index.html` in any modern browser — there is no build step.

## Risk note (read before touching ee/ERC or any "safe" wording)

perfwire is **R2 (customer-facing)** with a **physical-build safety overlay**: its output
is advisory soldering instruction that a human builds by hand. It does NOT actuate
hardware, so it is not R4 — but its electrical claims have a real-world safety dimension.

- **Never state or imply a board is "safe to power."** The ERC (shorts / polarity /
  clamp / etc.) is advisory; always require an independent human pre-power inspection.
- Do not weaken or remove existing ERC checks to make a plan "pass." A failing audit is
  a true signal, not a bug to silence.

## Working agreements

- Read this file before making changes.
- Prefer small, reviewable diffs.
- Do not invent commands. Inspect `tools/`, `.github/workflows/ci.yml`, and config first.
- Do not mark work complete until the verification gates below have run, or you clearly
  state which gate could not run and why.
- If changing public behavior, update `README.md`, `CHANGELOG.md`, and the SKILL if affected.
- If changing dependencies, ask for human confirmation. `solver.py` is **stdlib-only by
  design** — adding a third-party Python dependency requires explicit approval.

## Load-bearing repo rules (these are the things agents get wrong)

a. **Same-name 3-copies trap.** This repo (`perfwire-dev/perfwire`) is the only canonical
   copy. Do **not** edit either of the other two that may exist on the maintainer's own
   machine: an outdated (v4) copy embedded in an unrelated private project's own data
   directory, and the installed plugin build
   (`~/.claude/plugins/cache/.../perfwire/<version>/index.html`, a build artifact wiped on
   update). Fix bugs here; the others are not the source of truth.

b. **Parity is an invariant.** The JS ERC in `index.html` and `solver.py` must agree
   byte-for-byte on ee / EE-limit math. UI / render / guide / legend changes are
   parity-safe and need no math change. **Never change ee/ERC math in one place only** —
   mirror it in both, or the parity gates fail. If you are not changing the math, don't
   touch the ee/parity code paths.

c. **i18n coverage.** Any new Japanese runtime string in `index.html` must be routed
   through `tr()` / `trf()` / `L()` and have an English entry added to the `JE` dictionary.
   A raw Japanese literal in runtime code fails `i18n_check.mjs`.

d. **Plugin-consume absolute paths.** `.claude/skills/perfwire/SKILL.md` must not invoke
   bundled scripts with cwd-relative paths — when installed, the plugin runs from a foreign
   cwd in the plugin cache. `consume_smoke.py` lints this; reference bundled scripts by an
   absolute path anchored on the discovered plugin root (see SKILL.md §前提), never cwd-relative.

e. **Verify with real Chrome; don't guess.** Reproduce UI/render bugs in headless Chrome
   and capture the real exception before fixing — open `index.html` in a browser, or headless:
   `chrome --headless=new --screenshot=out.png "file:///<abs>/index.html"`. Do not "fix" by inference.

## Protected areas

Do not modify without explicit human approval:

- `config.example.json` ee/limit values used by the parity gates (changing them changes
  audit results in both engines).
- The `tr()`/`trf()`/`L()` routing mechanism and the `JE` dictionary's structure/format
  (adding a new key + EN value per rule (c) is expected and needs no approval; changing the
  routing or restructuring the dictionary does).
- `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` version fields, and the
  `index.html` header badge `<span class="brand">perfwire<small>vX.Y.Z</small></span>` (all three
  must stay in agreement — `check_manifests.mjs` enforces; bump all three together on release).
  Note: `index.html`'s `APPVER` is the localStorage-schema version, a separate thing — do not touch it.
- `.github/workflows/ci.yml` gate set.
- `LICENSE`.

## Verification

This repo's gates are the 7 CI checks in `.github/workflows/ci.yml`. Run the relevant
ones locally after changes (all 7 before a release):

```bash
node tools/extract_check.mjs        # index.html inline-JS parse + INIT validation
node tools/check_manifests.mjs      # plugin.json/marketplace.json fields, version agreement, skill exists
node tools/i18n_check.mjs           # all JA runtime literals routed through tr()/trf()/L() + JE dict
python tools/ci_smoke.py            # solver on all sample proposals; schema completeness; wires>0
python tools/consume_smoke.py       # installed-cache (foreign cwd) consume + SKILL.md cwd-relative lint
node tools/parity_check.mjs         # JS ercAudit vs solver.py ee/EE-limit byte parity (auto-detects Python 3)
node tools/parity_headless.mjs      # headless-Chrome geometry parity (auto-detects Python 3; skips if no Chrome)
```

The parity gates auto-detect a working Python 3. If detection fails (e.g. Windows where
`python`/`python3` is the Microsoft Store stub), set `PERFWIRE_PYTHON` to a real interpreter
first — bash: `PERFWIRE_PYTHON=/abs/python node tools/parity_check.mjs`; PowerShell:
`$env:PERFWIRE_PYTHON='C:\abs\python.exe'; node tools/parity_check.mjs` (an inline `VAR=value`
prefix is not valid in PowerShell).

Gate-to-rule map: extract→(general), check_manifests→protected versions, i18n→rule (c),
ci_smoke→solver contract, consume_smoke→rule (d), parity_check/parity_headless→rule (b).

If a gate does not exist or cannot run, do not invent a substitute. Record the gap in
`docs/harness/HARNESS_HEALTH.md`.

## Done criteria

A task is not done until:

1. relevant files are updated,
2. the relevant gates above have run (all 7 for a release),
3. remaining risks are listed (including any "never claim safe" caveats),
4. user-facing behavior changes are documented in `README.md` / `CHANGELOG.md` / SKILL.

## Skills

This repo ships one product skill: `.claude/skills/perfwire/SKILL.md` (perfboard
planning/auditing — the consumer entrypoint, and the source of truth for persona routing
and the agent↔human round-trip). Workspace-level methodology skills
(`beginner-usability-audit`, `expert-design-critique`) live in the parent dev workspace,
not in this product repo.
