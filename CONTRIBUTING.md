# Contributing

perfwire is maintained by one person working with Claude Code — replies may take a few days,
but every issue and PR gets read.

## Before you file

- **Bug?** Use the [bug report template](../../issues/new?template=1_bug_report.yml). Attaching
  the board state (JSON or a `#z=` link) makes it reproducible immediately — the audit is
  deterministic, so exact input reproduces the exact output.
- **Think the ERC/audit verdict is wrong?** Use the
  [ERC dispute template](../../issues/new?template=2_erc_dispute.yml) — this is a first-class
  category, not a regular bug. A wrong verdict is a bug in the rule engine, and fixing it improves
  the checker for everyone.
- **Feature idea?** Use the [feature request template](../../issues/new?template=3_feature_request.yml).
  Describe the problem before the solution.
- **Using perfwire through Claude Code?** You don't need to open GitHub yourself — just tell your
  agent, e.g. *"report this to perfwire."* The bundled skill drafts the issue and asks for your
  approval before filing anything. See `.claude/skills/perfwire/SKILL.md`.

## Product philosophy (please read before proposing a change)

- **Single file, zero dependencies.** `index.html` is the entire app — no build step, no npm, no
  server. Changes that would require introducing a build step or a runtime dependency are a hard
  sell; we'd rather discuss the trade-off honestly than accept quietly.
- **Deterministic verification, not an LLM judge.** The ERC/audit rule engine ships identically in
  browser JS and `solver.py`, and CI checks the two agree. This is the project's core
  differentiator — proposals that would blur it (e.g. having an LLM approve a board instead of the
  rule engine) need a very good reason.
- **Advisory, not a safety guarantee.** The audit catches wiring/electrical-rule mistakes it's
  designed to catch; it is not a certification that a board is safe to power. See `SAFETY.md`.

## Making a change

1. Fork, branch, make your change.
2. Run the 7 verification gates from the repo root before opening a PR:
   ```bash
   node tools/extract_check.mjs
   node tools/i18n_check.mjs
   node tools/check_manifests.mjs
   node tools/parity_check.mjs
   node tools/parity_headless.mjs   # needs Chrome; skips gracefully if none is found
   python tools/ci_smoke.py
   python tools/consume_smoke.py
   ```
   `parity_check.mjs` and `parity_headless.mjs` exist because the ERC engine is duplicated in
   JS and Python — if you touch electrical-rule logic, you almost certainly need to touch **both**
   `index.html`'s inline `ercAudit()` and `solver.py`, or these gates will fail.
3. New UI text must go through `tr()`/`trf()`/`L()` with a matching entry in the `JE` dictionary —
   `tools/i18n_check.mjs` enforces this so an English-locale user never sees a stray Japanese
   string.
4. Open a PR describing what changed and why.

## Translations

The English `README.md` is canonical. `README.ja.md` is the first translation; more languages are
planned. If you're adding or updating a translation:

- Name new translations `README.<BCP 47 language tag, lowercase>.md` (e.g. `README.zh-cn.md`) —
  note **`ja`, not `jp`**.
- Put a language-switcher line as the very first line of the file (see the top of `README.md` /
  `README.ja.md` for the exact format), followed by a blank line before the `# perfwire` heading —
  GitHub's Markdown renderer needs that blank line or the heading won't render.
- Add a `SYNC: README.md @ <version>` HTML comment near the top so readers know which English
  version a translation was last synced against. A translation is allowed to lag behind English by
  one release — update what you can, and it's fine to leave the rest summarized with a link back
  to the English section rather than blocking on a full re-translation.
- perfwire doesn't maintain a separate glossary — the canonical term list is the `JE` dictionary
  embedded in `index.html` (the UI's own English/Japanese pairs). Match its terminology where a
  concept overlaps.
- Add your new file's link to the language-switcher line in **every existing** README language
  file, not just the new one.

## License

Apache License 2.0 — see `LICENSE` and `NOTICE`. By contributing, you agree your contribution is licensed under the same terms.
