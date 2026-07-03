# Changelog

## [0.6.9] — 2026-07-03

### Added
- **3D isometric view (view-only)** — a "3D" toggle next to the back-view button shows the board from a fixed dimetric (yaw 45°/pitch 30°) angle on a new `<canvas id="pw-iso">`, rendered entirely independently of the existing 2D SVG editor (which is unchanged and remains the only way to edit). Component bodies (elec/disc/film/r/ic) reuse the same shading language as the existing part-preview panel (`PHYS_PREVIEW`), extended to full-board world coordinates via a new `ISO_DRAW` dispatch table. Click to select (synced with the 2D selection/lock state), drag to pan, Ctrl+wheel to zoom, hover a legend row to dim other nets — all read/write the same `selPart`/`selSet`/`hoverNet` globals the 2D view uses, so switching between 2D and 3D never loses your place. Editing (drag, bridge/block/probe/cut modes, lock/delete keys) is disabled in 3D by design; switching to any edit action returns to 2D automatically. The design (projection formulas, depth-sort strategy, bake/cache layering, performance budget) went through a research + adversarial-review pass before implementation; the review caught and the implementation fixes several correctness issues that would otherwise have shipped (wires crossing over an IC being hidden underneath it instead of drawn on top; click targets going stale after panning; a devicePixelRatio double-scaling bug on HiDPI displays; a wheel-zoom event leaking into the 2D view's zoom state). Known v1 limitation, called out in code comments: two components placed immediately adjacent to each other (e.g. a decoupling capacitor next to an IC) can occasionally sort into the wrong front/back order — a rare, cosmetic-only artifact of using a simple depth key rather than full visibility ordering. (Rendering-only; reads board state, writes only selection/hover — no `ee`/ERC/`solver.py`/parity-path change.)

## [0.6.8] — 2026-07-01

### Added
- **Launch-readiness pass**: a "Clear saved data" confirmation dialog (previously a single misclick silently wiped all local edits with no undo); the audit banner and its "総合" (overall) line no longer contradict each other (the banner could say "safe to solder, only a wire-length note" while a red NG line showed right below it — found by an adversarial usability + design-critique pass, not just code review); the audit panel is now a bordered card/row layout instead of one long `<br>`-joined text block; a new original example board, **Pico Plant Sitter** (a Raspberry Pi Pico plant-watering/monitoring board with a "Before" proposal carrying three real, solver-verified mistakes — reversed electrolytic polarity, a misplaced decoupling cap, an ungated 5V-into-GPIO clamp risk — and a clean "Recommended" proposal), replaces the previous default board shown on first open (which was derived from a client engagement and wasn't clean to publish; it remains available as `examples/client-hardware_tap_buffer.json`, just no longer the cold-start default); the welcome screen gained a "start from a blank board" option that applies the beginner-recommended placement profile automatically.
- **CI**: `ci_smoke.py` now locks in the Pico Plant Sitter example's exact expected findings (2 hard NG + 1 warn on "Before", `fabReady:true` on "Recommended") so a future `solver.py` change can't silently break the demo.

### Fixed
- **IC/module bodies now render for named-pin and single-row/single-column parts** (they used to silently disappear). The editor's part-draw loop indexed pins by the literal keys `'1'`/`'2'` to decide orientation, so a part whose `pins` are keyed by NAME (`VCC`/`GND`/`SDA`/`GPIO18_SCK`/`E`-`B`-`C`/…) — how MCU dev-boards, sensor breakouts and connectors are naturally modeled — threw and **aborted the entire parts layer, leaving a board of just wires with no visible components** (while `solver.py` still reported `fabReady`). It now takes the first two pins by insertion order (pin-key-agnostic). Separately, a single-row / single-column multi-pin part (pin header / single-edge module) computed a **negative** body cross-dimension, emitted as a `<rect>` with negative width/height that SVG does not paint; the body thickness is now clamped to a visible minimum. Multi-row DIPs are unchanged and still render correctly in **both** landscape and portrait. Found by headless (Chrome `--dump-dom` + screenshot) rendering verification. (Rendering-only; parity-safe — no `ee`/ERC/`solver.py`/parity-path change.)

### Added
- **SKILL.md §4b "build-type physical-caution checklist"** — a part-triggered guidance table the agent must fold into the plain-language audit summary, because these recurring implementation pitfalls are not visible from board geometry / `ee` alone (even a clean `fabReady` board can omit them). Covers: inductive-load coils (relay/solenoid/motor → drive via transistor + **flyback diode with correct orientation** + **separate the switching return from signal/sensor ground at a single star point**); motor drivers / H-bridges (split VM vs logic supply, don't float nSLEEP/EN, star ground); RF / solar / outdoor power (**reverse-flow/reverse-polarity Schottky with correct orientation**, **antenna/RF keep-away**, supply decoupling); **SSR/relay switching AC mains** (refuse the mains layout + redirect to a certified isolated module, and warn that an **SSR still leaks when commanded off so the load stays partly live** — kill power at the breaker before servicing); Li-ion/LiPo charging (charge-management IC required, electrolytic polarity); 5V-sensor-into-3.3V-GPIO (never direct — divider/level-shifter, and correct the user if they assume direct is fine). All advisory; never claim a board is safe to power. (Parity-safe: docs-only, no change to `ee`/ERC math, `solver.py`, or the parity paths.)

## [0.6.7] — 2026-06-23

### Fixed
- **Plugin-consume robustness — the bundled skill now works when perfwire is installed as a Claude Code plugin** (cwd = the user's own project, scripts in `~/.claude/plugins/cache/…`), not only in the clone-and-open path. `SKILL.md` previously invoked `solver.py` / `tools/*.py` / `config.example.json` / `index.html` by bare cwd-relative paths, which fail for an installed-plugin consumer (`$CLAUDE_PLUGIN_ROOT` is **not** exported to the Bash tool — only inline-substituted in manifests/hooks). SKILL.md now has a "前提: PLUGIN_ROOT" step that discovers the plugin root (newest installed version by mtime, `.in_use`-preferred, with a clone-and-open fallback and an actionable "not installed" message) and drives every bundled call through an absolute path.
- **A degraded EE audit no longer reports `fabReady: true`.** When no config is loaded (genuinely missing / mistyped `--config`), the core EE checks run empty; the solver now sets `ee.degraded: true` and forces `ee.fabReady: false` (and `stats.fabReady`), so an agent cannot tell a beginner "safe to solder" on an unaudited board. The `DEGRADED` stderr warning is unchanged; SKILL.md §4 instructs the agent to distrust `fabReady` when degraded. (Parity-safe: the browser always carries a populated config, so this only affects the config-less CLI path.)
- **`tools/make_link.py` / `tools/read_link.py` force UTF-8 stdout**, so a piped/redirected deep-link or state JSON is not mangled under a non-UTF-8 Windows locale.

### Added
- **CI gate #7 `tools/consume_smoke.py`** — copies the bundled payload to a throwaway "cache" dir outside the repo, runs the documented commands from a separate "consumer" cwd by absolute path, and asserts wires>0, a non-degraded audit, `--config` parity, and a deep-link round-trip. It also lints `SKILL.md` so a bundled-script invocation can never regress to the cwd-relative form.

### Notes
- `README.md` plugin section clarifies that the marketplace/plugin path needs repo **read access** (the repo is private), that third-party marketplaces don't auto-update (the install block always runs `/plugin marketplace update perfwire`), and adds a Windows `python3`-stub / "can't open solver.py" troubleshooting note.

## [0.6.6] — 2026-06-21

### Added
- **Non-isolated board topologies — `grid.type` now models the board's own copper.**
  perfwire previously assumed isolated pads (`perf`) or strips (`strip`). A real
  failure — a board that "won't power on" because it was built on a **十字配線
  (cross-wired) universal board** whose every hole is bonded to its 4 neighbors —
  exposed the gap: the substrate shorted V3V3 to GND (and every other net) and the
  isolated-pad model could not see it. The stripboard segment primitive is
  generalized into one `board_links` / `boardLinks` generator that feeds the **same**
  ERC union-find, so a design routed assuming isolation is caught by `netMerge`
  (hard NG) when the board copper shorts its nets. New `grid.type` values:
  `mesh` (十字/格子, ships as one net — cut to isolate), `breadboard` (column
  segments + power-rail strips), `cluster` (2/3連ランド bonded groups), and
  `custom` (explicit `boardLinks` edge list). `perf`/`strip` unchanged.
- **Editor support for cross-wired boards.** The board-type command cycles
  `perf → strip → mesh → breadboard → cluster`; the renderer draws the intrinsic
  copper bridges (and cut marks); **cut mode (key 6)** now toggles a cut on any of
  the 4 mesh edges (not just the strip axis); and a new command
  **auto-generates the required-cut list** that isolates every net (region-grow,
  cut the boundaries) — applied to the board, written to the export box, and
  downloaded as a `.md` checklist for cutting the physical board.

### Fixed
- The strip-only ERC union block and render path are now general (`board_links`
  dispatch); `stripShorts` is still emitted for the segment-bounded types
  (`strip`/`breadboard`/`cluster`) and the whole-mesh case rides on `netMerge`.

## [0.6.5] — 2026-06-19

### Added
- **`bridgeDangle` (HARD NG) — a wire endpoint whose solder-bridge points at a
  hole that is anchored to nothing.** The connectivity solver unconditionally
  trusts a wire endpoint's `bridgeTo` (it unions the landing hole with the bridge
  target), so a wire shifted one hole onto an empty cell with a bridge to a
  dead hole still reports `openNets: []` — a silent open the existing checks miss.
  `bridgeDangle` flags an endpoint when its `bridgeTo` target is **not** anchored
  by any of: a part lead, the endpoint's own tap pad, a `padBridge`, or another
  wire endpoint landing there. The normal "land adjacent + bridge to the pad"
  idiom (used by ~95% of endpoints on a real board) is always anchored, so it
  does not fire — only a genuinely dangling bridge does. Mirrored byte-for-byte
  in `solver.py` and `index.html`; wiring-dependent (skipped on the synthetic
  parity fixtures, asserted empty on the bundled samples).

### Fixed
- `netMerge` (galvanic cross-net short) and the new `bridgeDangle` are now both
  counted by `ercHardCount()` and reflected in `#eedump`/`auditState`, so the
  editor verdict treats them as the hard NGs they are (previously `netMerge`
  reached the verdict only via the aggregate NG count, not `auditState`).

## [0.6.4] — 2026-06-18

### Fixed
- **Non-finite resistor `value` (Infinity/NaN)** is no longer echoed into the
  solver's `out.json` as a bare `Infinity` token (invalid JSON that would crash a
  downstream `JSON.parse`). It is coerced to `null` at intake and treated as
  "unspecified" by every rail-leak check; the JS engine adds an `isFinite()` guard
  so both engines exclude non-finite values identically.
- **A 0-ohm part** (`kind:"r", value:0`) modeled as a component rather than a
  jumper previously fell through *all* rail-leak checks. A 0-ohm resistor is a
  galvanic jumper, so `netMerge`'s union-find now unions the two lead holes of any
  2-lead `value:0` part — a 0-ohm part bridging two distinct nets now correctly
  fires `netMerge` (hard short). Mirrored in both engines.

## [0.6.3] — 2026-06-18

### Added
- **`railReff` (WARN) — full-network rail-to-rail effective short.** Computes the
  effective resistance `R_eff` of the resistor network between each pair of power
  rails and warns when `I = |ΔV|/R_eff` exceeds `rail_short_ma` (default 50). This
  catches what per-resistor `railShort` structurally misses: **series chains**
  (22+22Ω = 44Ω = 75 mA), **parallel** low-R paths (120∥120 = 60Ω = 55 mA, where
  each branch alone is 27.5 mA = ok), and arbitrary **meshes** (Wheatstone
  bridges). `R_eff` is solved by a reduced nodal Laplacian via no-pivot Gaussian
  elimination over a sorted node index — the grounded Laplacian of a connected
  resistor net is SPD, so no-pivot elimination is stable *and* bit-deterministic.
  With fixed node/edge/summation order and no FMA, the float solve is
  **byte-identical across the JS and Python engines** (the gate also compares only
  `{pair, ok}`, as for `railShort`). Per-pair de-dup defers single direct resistors
  to `railShort`; reuses `rail_short_ma` (no new config); WARN-only (`fabReady`
  unchanged). Designed via a parity-feasibility workflow and passed a 3-angle
  adversarial audit (R_eff verified vs hand-computed values incl. an unbalanced
  bridge = 17000/71).

### Fixed
- `topology_audit` return-rail (GND) selection: the JS engine now breaks ties by
  lexicographically-smallest net name, matching Python's `min((rank, name))`, so a
  future multi-rank-0 power config (e.g. AGND + DGND) cannot diverge between engines.

## [0.6.2] — 2026-06-18

### Added — effective-short ERC checks
Three netlist checks for "current concentrating into an effective short" (no
hard solder bridge required), plus an analog-reference grounding refinement:

- **`netMerge` (HARD NG)** — two distinct intended nets joined into one galvanic
  node: a real short that was undetected on perfboards (`stripShorts` only
  covered strip boards; `openNets` is the inverse — one net split). Catches
  bridge/wire merges *and* same-hole multi-net shorts (per-hole net set, since
  `node_net` is last-write-wins). Editor-path by design — the solver re-routes
  per-net and never emits a merge — so it is `WIRING_DEP` in parity like `openNets`.
- **`railShort` (WARN)** — a resistor bridging two rails that draws excess
  quiescent current (`I = |ΔV|/R > rail_short_ma`, default 50 mA): an effective
  partial short *even when it stays under its power rating* (the gap
  `resistorPower` misses). Per-resistor v1; full-network R_eff / series chains
  are deferred to keep cross-engine float parity stable.
- **Reference-rail grounding** — the star/daisy return-topology analysis now also
  evaluates internal reference rails that have no external feed (new optional
  config `reference_rails`, e.g. `VMID` rooted at its bypass cap), flagging a
  daisy-chained analog mid-rail (common-impedance coupling). Return-topology
  depth now counts **component-lead hops**, not routing-hole hops, so a
  board-spanning but electrically-star rail no longer false-reads as daisy.

All WARN-level checks leave `fabReady` unchanged; `netMerge` is the only hard NG.
Each ships a byte-for-byte `solver.py` / `index.html` mirror, parity coverage,
and passed an adversarial audit loop. The CLI `ee.fixes` list now also covers
`clampRisk` / `netMerge` / `railShort`.

[0.6.2]: https://github.com/YusukeAraiKecku/perfwire/releases/tag/v0.6.2

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
