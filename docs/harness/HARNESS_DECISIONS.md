# HARNESS_DECISIONS.md

## Current harness version

- Baseline: minimal harness, frontend-app profile
- Applied date: 2026-06-23
- Project risk: R2 (customer-facing) + physical-build safety overlay
- Project type: frontend-app (single-file browser editor) + Python stdlib CLI

## Decisions

### D001: Keep AGENTS.md short and contributor-facing

Reason:
- Always-loaded instructions should not crowd context.
- A plugin repo's root AGENTS.md/CLAUDE.md is NOT loaded for plugin consumers (only for
  contributors who open the repo), so it is scoped to contributor guidance; runtime/consumer
  behavior is owned by `.claude/skills/perfwire/SKILL.md`.
- Detailed workflows belong in the product skill, not in always-on rules.

### D002: No new hooks (`.claude/settings.json` deliberately absent)

Reason (add a control only with a concrete, recurring, otherwise-undetectable failure):
- perfwire already has **7 deterministic computational sensors** in CI
  (`extract_check`, `check_manifests`, `i18n_check`, `ci_smoke`, `consume_smoke`,
  `parity_check`, `parity_headless` — `ci.yml` installs Chrome via `setup-chrome` so all 7
  run in CI). These are higher-priority than any inferential or hook-based control and
  already cover the drift a hook would catch.
- The classic destructive-command-guard hook protects against data/infra loss; perfwire
  has **no DB, no secrets, no deploy, no production data** — the failure class a guard
  targets does not exist here.
- The parity gates already prevent the one repo-specific catastrophe (ee/ERC math
  diverging between `index.html` and `solver.py`) more reliably than a hook could.
- A `PostToolUse` formatter hook adds no value: there is no configured formatter and the
  single-file `index.html` is hand-maintained.
- Therefore a hook would be an unvalidated hypothesis (cost > benefit, no observable
  signal it would catch anything the 7 gates miss). Revisit only if a concrete drift
  recurs that CI cannot catch.

### D003: Do not require missing or invented commands

Reason:
- Inventing commands causes false confidence.
- The verification section lists exactly the 7 existing CI gates and nothing else.
- Any gate that cannot run (e.g. `parity_headless` without Chrome) is recorded as a
  conditional in HARNESS_HEALTH.md rather than presented as always-available.

### D004: Parity is a hard invariant; ee/ERC math is mirrored or not touched

Reason:
- The product's correctness contract is that the browser ERC and `solver.py` agree
  byte-for-byte on ee / EE-limit results.
- UI / render / guide / legend changes are parity-safe; math changes must be mirrored in
  both engines in the same change or the parity gates (D002's strongest sensor) fail.

### D005: Plugin-consume absolute-path rule

Reason:
- When installed, the plugin runs from a foreign cwd in the plugin cache, so SKILL.md
  must not reference bundled scripts cwd-relative. `consume_smoke.py` lints this; the rule
  is encoded as a sensor, not just guidance.

### D006: Risk classification = R2 + safety overlay (not R4)

Reason:
- perfwire emits an **advisory** plan a human hand-solders; it performs no actuation and
  no irreversible action under AI control, so R4 (hardware/safety-critical, which forbids
  autonomous actuation and mandates simulation-first / ops log / safety envelope) does not
  apply.
- R2 requirements (lint/test/build-equivalent gates, CI, secrets protection) are met and
  exceeded by the 7 gates.
- R4 *vocabulary* is borrowed only as a guide-level safety overlay: never claim a board is
  safe to power; the ERC is advisory; require an independent human pre-power inspection.

### D007: Stdlib-only solver is a protected design property

Reason:
- `solver.py` is intentionally dependency-free so it runs anywhere Python 3 exists and in
  the plugin cache without install. Adding a third-party dependency requires explicit human
  approval (recorded as a protected operation).

## Verification commands

```bash
node tools/extract_check.mjs
node tools/check_manifests.mjs
node tools/i18n_check.mjs
python tools/ci_smoke.py
python tools/consume_smoke.py
PERFWIRE_PYTHON=python node tools/parity_check.mjs
PERFWIRE_PYTHON=python node tools/parity_headless.mjs   # skips if no Chrome
```

## Protected operations

- Editing `config.example.json` ee/limit values (changes audit results in both engines).
- Changing ee/ERC math in only one of `index.html` / `solver.py` (parity invariant).
- Adding a Python dependency to `solver.py` (stdlib-only by design).
- Bumping `plugin.json` / `marketplace.json` versions out of agreement.
- Editing the IVR copy or the installed plugin-cache copy as if canonical (3-copies trap).

## Open questions

- When (if ever) does a recurring CI-invisible drift justify adding the first hook? (D002
  revisit trigger.)
- Should an eval/benchmark harness be built to measure plan/audit quality, or do the 7
  computational gates suffice? (Tracked in HARNESS_HEALTH.md.)
