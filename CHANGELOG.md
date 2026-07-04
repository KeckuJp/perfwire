# Changelog

## [0.6.10] — 2026-07-03

### Fixed
- **Drag→undo could desync the editor from what was actually drawn.** `snap()` (the undo-checkpoint push) ran *after* a drag's mutation instead of before it in one code path, so `Ctrl+Z` could restore a stale board while the visible SVG kept the just-dragged position — and a specific drag sequence could register as a false "revert" that silently duplicated a part. Fixed the snapshot timing and the duplicate-detection check that depended on it.
- **A brand-new standalone board (no starter proposal) had no way to reach a power-connected, auditable state.** Adding parts one at a time from a blank board could leave a net with no path to a supply/ground rail and no UI action to fix it — a beginner following the guide hit a dead end. Added a UI entry point (also reachable from the audit panel's own NG-fix suggestions) to place an external power/ground terminal directly on the board.
- **`importObj()` (paste/upload a board JSON) crashed uncaught on a structurally malformed part** (e.g. an IC missing `pins`) and wedged the board for the rest of the session — every subsequent `render()` call (any mouse move, any mode switch) hit the same exception again, with no error toast telling the user what happened. It also gave no feedback at all on a successful import, and JSON-parse failures showed only the raw parser message. Malformed parts are now dropped (with a toast reporting how many), successful imports report exact part/wire counts, and parse failures point at the likely cause (truncated paste / re-export) alongside the raw error.
- **Bulk board-changing actions (reset a proposal, re-place & route, cycle board type) gave no indication of what changed**, so a wrong click was hard to assess or recover from beyond blind trust in "元に戻す". They now report a concrete before/after diff (parts/wires moved or added/removed, or the resulting change in audit NG count) in the confirmation toast.
- **Board rendering: labels and wires could be hidden underneath opaque part bodies**, and dense boards showed no distinction between a covered pad and empty space. Part/pin labels now always paint after (on top of) pads, wire paths now paint after (on top of) part bodies instead of before, and wires using a very dark net color get a subtle white halo so they stay legible against dark IC bodies.
- **The pass banner ("組んで大丈夫です") didn't say what it does and doesn't check** — it reads only the automated ERC/EE audit, not physical realities like component orientation. Its text now says so explicitly. The empty-board state (no parts placed) previously showed a generic pass banner instead of guidance to get started.
- **`locked:true` parts (excluded from auto re-placement) had no visible indicator** beyond a small marker with no explanation, and toggling a lock didn't refresh the board legend. Lock markers now carry a tooltip explaining the contract, the legend shows a lock-usage row when any part is locked, and re-place/route results report how many locked parts were skipped.
- **The first-run welcome screen was a one-shot dialog** — dismiss it (by mistake or otherwise) and "start from a blank board" was gone for the rest of the session, along with the guide's board-type explanation. Added a permanent "新規（空の基板）" button and command-palette entry that does the same thing at any time.
- **Keyboard accessibility: board editing was pointer-only (zero keyboard paths, WCAG 2.1.1).** The SVG board is now a keyboard-operable composite widget (Tab into it, arrow keys cycle part selection, Shift+Arrow moves the selected part one grid hole using the same placement-validity checks as mouse drag). The welcome modal and command palette declared `role="dialog"`/`aria-modal` without actually trapping focus or restoring it on close — both now use a shared focus-trap helper. The guide panel's step text is now an `aria-live` region, and weight-slider inputs are correctly associated with their visible labels via `aria-labelledby`.
- **Toast notifications auto-dismissed on a fixed timer with no way to re-read one that scrolled past**, and the audit verdict banner wasn't exposed as a live region for screen readers. Toasts now pause on hover and can be dismissed by click; the last notification stays visible in the status bar; the 5 verdict-banner variants are `role="status"`.
- **Undo had no matching Redo** — an accidental `Ctrl+Z` had no way back except manually redoing the work. Added a symmetric redo stack, a "やり直す" button (`Ctrl+Y`/`Ctrl+Shift+Z`), and a command-palette entry.
- **The current edit mode (move/bridge/block/probe/cut) wasn't visible anywhere outside the toolbar buttons**, making it easy to lose track of which click-action was active. Added a status-bar chip showing the current mode and a matching cursor style per mode.
- **Two independent sources of truth for command names/keywords/keybindings** (the command palette's list and the mode-switch buttons/keydown handler) could drift out of sync. Consolidated into one `CMDS` registry that both derive from.
- **Adversarial review of the above fixes** (independent 4-dimension pass: state-mutation, new-feature correctness, render/a11y, i18n/parity — each finding cross-checked by a second skeptic before acceptance) caught two data-integrity blockers that shipped in earlier commits of this same body of work: `delProp()` (delete a proposal) remapped the undo stack's indices but not the newly-added redo stack, so deleting a proposal after an undo/redo sequence could crash on the next `Ctrl+Y` or silently overwrite an unrelated surviving proposal's content; and the external-power-terminal feature above registered into a global settings object keyed only against the *currently viewed* proposal, so simply switching to look at a different proposal (including the app's own second bundled sample) would silently and permanently un-register the terminal even though it was still sitting on the original board — quietly undoing the fix it shipped as. Also fixed: the guide panel wasn't included in the new keyboard-focus-trap work, so Tab could leak from a guided walkthrough onto the live board and the new arrow-key nudge could edit it invisibly under the guide's overlay; a "new blank board" action left a permanent no-op undo entry that never got cleaned up by `Ctrl+Z`; and a duplicate i18n dictionary key silently broke the English-locale guide's first-step label. (All parity-safe — no `ee`/ERC/`solver.py`/parity-path change; confirmed via byte-identical gate output before/after.)

- **Smaller polish**: the zoom buttons now clarify they scale only the board diagram, not on-screen text size (browser Ctrl+/Ctrl- does that); a duplicate i18n dictionary key and 5 hardcoded-English `aria-label`s were closed; the two bundled sample proposals' names now route through the same translation path as everything else instead of being hardcoded English; the welcome screen and share-link toast wording were rewritten to lead with what the reader actually needs to know; "進め方" (an ambiguous label shared by two different UI sections) was renamed to "ショートカット" in the one that means keyboard shortcuts; the primary-button gradient's dark stop was darkened to meet WCAG AA contrast (was 3.69:1, now 4.83:1); and `scrollIntoView`/`scrollTo` calls now respect `prefers-reduced-motion`.

### Added
- **Proposal provenance and lifecycle.** Each proposal now tracks where it came from (verified/sample/solver/shared/import/blank/saved) and whether it's been edited since, shown as a badge; proposals can be renamed and deleted (with confirmation) from the sidebar.

## [0.6.9] — 2026-07-03

### Added
- **3D isometric view (view-only)** — a "3D" toggle next to the back-view button shows the board from a fixed dimetric (yaw 45°/pitch 30°) angle on a new `<canvas id="pw-iso">`, rendered entirely independently of the existing 2D SVG editor (which is unchanged and remains the only way to edit). Component bodies (elec/disc/film/r/ic) reuse the same shading language as the existing part-preview panel (`PHYS_PREVIEW`), extended to full-board world coordinates via a new `ISO_DRAW` dispatch table. Click to select (synced with the 2D selection/lock state), drag to pan, Ctrl+wheel to zoom, hover a legend row to dim other nets — all read/write the same `selPart`/`selSet`/`hoverNet` globals the 2D view uses, so switching between 2D and 3D never loses your place. Editing (drag, bridge/block/probe/cut modes, lock/delete keys) is disabled in 3D by design; switching to any edit action returns to 2D automatically. The design (projection formulas, depth-sort strategy, bake/cache layering, performance budget) went through a research + adversarial-review pass before implementation; the review caught and the implementation fixes several correctness issues that would otherwise have shipped (wires crossing over an IC being hidden underneath it instead of drawn on top; click targets going stale after panning; a devicePixelRatio double-scaling bug on HiDPI displays; a wheel-zoom event leaking into the 2D view's zoom state). Known v1 limitation, called out in code comments: two components placed immediately adjacent to each other (e.g. a decoupling capacitor next to an IC) can occasionally sort into the wrong front/back order — a rare, cosmetic-only artifact of using a simple depth key rather than full visibility ordering. (Rendering-only; reads board state, writes only selection/hover — no `ee`/ERC/`solver.py`/parity-path change.)

## [0.6.8] — 2026-07-01

### Added
- **Launch-readiness pass**: a "Clear saved data" confirmation dialog (previously a single misclick silently wiped all local edits with no undo); the audit banner and its "総合" (overall) line no longer contradict each other (the banner could say "safe to solder, only a wire-length note" while a red NG line showed right below it — found by an adversarial usability + design-critique pass, not just code review); the audit panel is now a bordered card/row layout instead of one long `<br>`-joined text block; a new original example board, **Pico Plant Sitter** (a Raspberry Pi Pico plant-watering/monitoring board with a "Before" proposal carrying three real, solver-verified mistakes — reversed electrolytic polarity, a misplaced decoupling cap, an ungated 5V-into-GPIO clamp risk — and a clean "Recommended" proposal), replaces the previous default board shown on first open (which wasn't clean to publish as the cold-start default); the welcome screen gained a "start from a blank board" option that applies the beginner-recommended placement profile automatically.
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
- **Off-board connections are now visualised**: external terminals (`W.*`) and single-lead
  audio-style **speaker / mic** I/O points get a boundary glyph (square tag + off-board arrow)
  and an "外部接続" legend that names *what* each connects to (Speaker / Mic / Power) and *where*.

### Config, provenance & Claude Code integration
- **Single config SSOT** (`config.example.json`) with a never-silent "EE audit degraded"
  warning; **one CI-verified dimension citation** (collapsed the old PHYSREF / physical_sources).
- **Round-trip handback**: `tools/read_link.py` (inverse of `make_link.py`) + a deep-link
  **Claude Code bar** (`make_link.py --task`) so the human ⇄ agent loop is self-explanatory.

### Fixes & hardening
- Adversarial-audit fixes for the dimension inspector + preview; load-time migration that
  strips stale per-instance resistor dims; legible standing resistors with cited dimensions.

[0.6.0]: https://github.com/YusukeAraiKecku/perfwire/releases/tag/v0.6.0
