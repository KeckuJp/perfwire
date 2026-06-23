# CLAUDE.md

Claude Code entrypoint for contributors working **on** perfwire. (This file is not loaded
for plugin consumers — only for someone who opens this repository.)

## Read first

- `AGENTS.md` — authoritative working agreements, the load-bearing repo rules (3-copies
  trap, parity invariant, i18n, plugin-consume paths, headless-verify), and the 7 verification gates.
- `docs/harness/HARNESS_DECISIONS.md` — why the harness is structured this way (no hooks; 7-gate sensor strategy; R2 + safety overlay).
- `docs/harness/HARNESS_HEALTH.md` — known gaps.
- `.claude/skills/perfwire/SKILL.md` — the product skill and source of truth for consumer/runtime behavior.

## Operating mode

- Start in plan mode for changes to ee/ERC math, the parity paths, or `solver.py`.
- Prefer small diffs. Never change ee/ERC math in only one engine (parity invariant).
- Do not invent verification commands — use the 7 gates in `AGENTS.md`.
- Do not add always-on rules or hooks unless a repeated, CI-invisible failure justifies it.

## Memory

`AGENTS.md` and this file are authoritative. If Claude Code auto memory contradicts an
instruction here, follow these files and surface the contradiction — do not silently act
on memory. Record stale/contradictory memory as a gap in `docs/harness/HARNESS_HEALTH.md`.

## Safety

perfwire output is advisory. Never claim a board is safe to power; the ERC is advisory and
requires an independent human pre-power inspection. There are no secrets, DB, or deploy
credentials in this repo; do not introduce them.
