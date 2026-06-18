# Changelog

## [0.6.1] — 2026-06-18

### Added
- **`clampRisk` ERC — input ESD-clamp / latch-up risk** (warn-level). For each IC
  input pin (`role=in`), it walks cap-coupled (non-resistive) net adjacency; if an
  external I/O terminal (`single_lead_allowlist`) is reachable **without a series
  resistor**, it flags `{pin, net, via}`. An off-board signal that can exceed the IC
  rails `[Vss,Vdd]` would conduct the input ESD/clamp diode (effective short /
  latch-up); a series R limits that current. Nets driven on-board by an op-amp output
  (`out`/`pwr_out`, via caps) are rail-bounded and **excluded**, so a board *output*
  (e.g. `IF_MIC`) is not a false aggressor. Reuses `pinTypes` / `single_lead_allowlist`
  — **no new config**; summed into `ee_warn`, never `ee_ng`, so **fabReady is
  unaffected**. solver.py + byte-for-byte index.html mirror; covered by
  `parity_check.mjs` (FIELDS + MUST_COVER) and `ci_smoke.py`. v1 limits (documented):
  only `kind==r` blocks the path; resistor value is ignored.

[0.6.1]: https://github.com/YusukeAraiKecku/perfwire/releases/tag/v0.6.1

## [0.6.0] — 2026-06-15

A large editor/UX + component-model release focused on beginner usability and the
human ⇄ Claude Code loop. No EE-audit or solver math changed — JS↔Python parity stays
byte-for-byte across the whole release.

### Editing & interaction (direct manipulation)
- **Modeless "選択／移動"**: one tool grabs parts *and* terminals (wire ends / leads) by
  priority — no more switching between 端子/部品 modes to move different things.
- **Multi-select + group move**: Shift+click toggles, drag empty space box-selects, and
  dragging the selection moves it together (locked parts skipped).
- **On-board action bar + keys**: when something is selected, an action bar over the board
  shows "N個 選択中 · うちM個ロック" with Lock / Delete / Deselect; keys **L / Delete / Esc**
  do the same — no left-panel trips. Lock is the human↔AI "settled vs open" signal:
  `--propose` only re-places still-unlocked parts.
- **Side panel reordered** by what a beginner needs first (live audit → placement goal →
  legend on top; expert tools collapsed).
- **Confirmations are a visible toast** over the board instead of being buried in a panel.
- **Per-part dimensions in a selection-driven inspector** that scales to any number of
  parts/types (replaces the flat per-instance slider list).

### Component model & previews
- **Open component model**: `kind` is a geometric primitive, not a closed parts list —
  a **Raspberry Pi Pico, relay, connector, header** is modeled as `ic`; an **inductor /
  buzzer** as `r`/`disc`. An optional per-part `family` names it in the BOM & legend.
- **Data-driven 2.5D preview** for every kind (electrolytic can, ceramic disc, film box,
  resistor, IC/DIP footprint) — adding a kind is one table entry, no hardcoding.
- **Placement goals (plain-language methodology presets)**: Easy to build / Analog /
  Compact, shared by the editor dropdown and `solver.py --profile`.

### External connections
- **Off-board connections are now visualised**: external terminals (`W.*`) and the client-hardware
  **speaker / mic** I/O points get a boundary glyph (square tag + off-board arrow) and an
  "外部接続" legend that names *what* each connects to (Speaker / Mic / Power) and *where*.

### Config, provenance & Claude Code integration
- **Single config SSOT** (`config.example.json`) with a never-silent "EE audit degraded"
  warning; **one CI-verified dimension citation** (collapsed the old PHYSREF / physical_sources).
- **Round-trip handback**: `tools/read_link.py` (inverse of `make_link.py`) + a deep-link
  **Claude Code bar** (`make_link.py --task`) so the human ⇄ agent loop is self-explanatory.

### Fixes & hardening
- Adversarial-audit fixes for the dimension inspector + preview; load-time migration that
  strips stale per-instance resistor dims; legible standing resistors with cited dimensions.

[0.6.0]: https://github.com/YusukeAraiKecku/perfwire/releases/tag/v0.6.0
