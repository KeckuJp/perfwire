# HARNESS_HEALTH.md

## Known gaps

| Date | Gap | Impact | Proposed fix | Status |
|---|---|---|---|---|
| 2026-06-23 | `parity_headless.mjs` requires a headless Chrome | The geometry-level parity check needs Chrome; it exits 0 (skips) where none is found | **Resolved in CI** — `ci.yml` installs Chrome via `browser-actions/setup-chrome`, so this gate now runs in GitHub CI; it still skips on a contributor machine without Chrome | Resolved (CI) / conditional (local) |
| 2026-06-23 | No eval/benchmark harness for plan/audit *quality* | The 7 gates verify correctness/contract/parity (computational sensors) but nothing measures placement/routing/audit *quality* against a reference set; quality regressions are invisible to CI | Build a small `evals/` set (e.g. golden board states + expected audit verdicts) once a recurring quality miss is observed; do not pre-build absent a signal (over-harnessing policy) | Open — deferred by policy |
| 2026-06-23 | Interpreter not guaranteed on PATH | Gates need `node` and a working Python 3; on Windows `python`/`python3` may be the Microsoft Store stub (not a real interpreter) | **Mitigated** — the parity gates auto-detect a working Python 3 and print a clear `set PERFWIRE_PYTHON` message instead of a stack trace; AGENTS.md documents the bash/PowerShell forms. `ci_smoke`/`consume_smoke` use `sys.executable` (self-consistent once launched) | Mitigated |
| 2026-06-23 | Claude Code auto memory not managed by this repo's harness | Workspace auto-memory may accumulate learnings that contradict AGENTS.md/CLAUDE.md | AGENTS.md is authoritative over auto memory; audit with `/memory` periodically and record contradictory entries here | Partially mitigated |
| 2026-07-03 | Harness baseline has no automated staleness tracking | This repo's harness docs were adapted by hand from an external template at a point in time; there is no mechanism that detects when that template has since changed, so drift is invisible unless someone re-checks by hand | Manual periodic re-audit only (this row documents that the 2026-07-03 pass found the baseline still sound — see HARNESS_DECISIONS.md D008/D009); re-check again if a large gap opens before the next deliberate review | Accepted (manual cadence, no automation planned) |

## Resolved / non-gaps (verified 2026-06-23)

- **GitHub Releases backfill — NOT a gap.** Tags `v0.6.0`–`v0.6.7` exist and `v0.6.7` is
  published as the Latest GitHub Release. (Listed here because it was flagged as a suspected
  gap; verification showed it is current. Re-flag only if a future tag ships without a Release.)

## Incidents

| Date | Incident | Root cause | Harness change | Eval added |
|---|---|---|---|---|

## Candidate improvements

| Candidate | Reason | Expected signal | Decision |
|---|---|---|---|
| First `.claude/settings.json` hook | Only if a recurring CI-invisible drift appears | A repeated failure no gate catches | Deferred (D002 — no signal yet) |
| `evals/` quality harness | Measure plan/audit quality, not just correctness | A real quality regression slips past CI | Deferred until signal (D002/over-harnessing) |
| Chrome in a CI job | Make `parity_headless` non-conditional in CI | Geometry parity bug ships because headless skipped | **Done (2026-06-23)** — `ci.yml` installs Chrome via `setup-chrome` |
| Diagnostic diff-size/complexity review agent | Flag hard-to-review diffs before merge | A diff proves genuinely hard to review in practice, not hypothetically | Deferred (D009 — no signal yet; would also require committing `.claude/settings.json`, conflicting with this repo's policy) |
| Skill-quality measurement loop (`/improve-skill`-style) for the product skill | Iteratively measure/improve `.claude/skills/perfwire/SKILL.md` quality | A concrete quality miss in the shipped skill is observed | Deferred (D009 — same settings.json conflict; the shipped form also enables a marketplace plugin) |

## Prune candidates

| Rule/Hook/Skill | Why remove | Last useful date | Decision |
|---|---|---|---|
