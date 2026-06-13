# perfwire

**AI-assisted wiring planner for hand-soldered perfboards** — designed to be used together with [Claude Code](https://claude.com/claude-code).

Perfboard (ユニバーサル基板) builds fail in a predictable way: the netlist is right, but the physical execution — which hole each jumper goes into, which pads get solder-bridged, where the decoupling caps actually sit — drifts from the plan. perfwire splits the work the way it should be split:

- **The AI agent** generates the board state from a netlist, allocates jumper endpoints to free holes (a copper wire can never share a hole with a component lead), proposes placements under physical and electrical constraints, and audits the result.
- **The human** drags things to match physical reality — locked parts, blocked holes, actual component positions — directly in a browser editor, then feeds the state back to the agent.

Everything lives in one JSON state file that both sides read and write.

## Quick start

1. Clone this repo.
2. Open `index.html` in any modern browser (no install, no server, single file). A sample project (a dual op-amp audio tap buffer) is embedded.
3. Drag wire endpoints / parts, set thresholds with the sliders, hit **配線を再計算** (re-route) or **配置を再提案** (re-place & route).
4. **書き出し** exports the full state JSON — hand it to Claude Code for deeper audits, or commit it to your project repo.

### Use with Claude Code

**Primary — clone and open as a project** (lowest friction; works for a private repo):

```bash
git clone https://github.com/YusukeAraiKecku/perfwire.git
cd perfwire
claude .
```

Accept the workspace-trust prompt once; the bundled skill (`.claude/skills/perfwire/SKILL.md`) auto-loads and triggers on perfboard / wiring requests. It teaches the agent the state schema and the collaboration loop:

```
you:    "この回路をユニバーサル基板に組みたい"（ネットリスト/回路図を渡す）
agent:  state JSON を生成 → solver.py で配置+配線+監査 → index.html#z= リンクで盤面を渡す
you:    実物に合わせてドラッグ修正 → 書き出し JSON を渡す
agent:  監査（短絡・デカップリング距離・配線長・本体重なり）→ 確定図/チェックリスト生成
```

**Alternative — install as a plugin** (the repo doubles as its own single-plugin marketplace). Needs git auth for this private repo (`gh auth login`, or an SSH key in your agent):

```
/plugin marketplace add YusukeAraiKecku/perfwire
/plugin install perfwire@perfwire
```

The plugin bundles the same skill (namespaced `perfwire:perfwire`; `plugin.json` points its `skills` path at `.claude/skills/`, so there is one copy, not two). For background auto-update of an installed private plugin, export `GH_TOKEN` (scope `repo`) — otherwise updates silently fail.

> **Solver note:** use `python3` on macOS/Linux, `python` on Windows; `solver.py` is standard-library only (no install). Always pass `--config config.example.json` — without it the EE audit (decoupling distance, wire length) silently runs empty. To hand a board to the human pre-loaded, generate a deep link with `python3 tools/make_link.py out.json` and have them open the printed `index.html#z=…` URL.

## Features

- **Hole-accurate model** — one hole holds one lead or one wire end; jumper endpoints are auto-allocated to free holes adjacent to their target net, bridged with solder; falls back to direct-soldering a lead only when no hole is free.
- **Physical footprints** — resistor capsules, electrolytic circles (per-part diameter override), film-cap boxes; bodies block holes; tall×tall overlaps are errors, tall×flat are warnings; lead span min/max derived from body length + bend margin; vertical (standing) resistor mounting.
- **EE constraints** — net classes (high-Z / signal / output / power) with per-class wire-length limits and adjacency penalties, decoupling-cap proximity constraints, input/output separation, max solder joints per pad.
- **In-browser solver** — greedy placement + net connection + live audit, all client-side JS. Tune thresholds with sliders, recalculate instantly. The same solver ships as `solver.py` for CLI / CI use.
- **Photo underlay** — drop a photo of the real board under the grid (opacity / scale / fine rotation / mirror for backside shots, drag to align) and trace reality by dragging parts onto it. AI guessing hole positions from photos fails; a human tracing over a photo doesn't.
- **Guided soldering mode** — walk the build one joint at a time (parts → bridges → wires) on a dimmed board with the current step highlighted and named (e.g. `6B`). Arrow keys to navigate, Enter to check off (progress persists), mirror view for soldering from the back side.
- **Virtual continuity tester** — probe mode: click two holes, see whether the plan connects them (and the whole connected group). Exports a markdown beep-out checklist per net — including the adjacent different-net pairs that must NOT beep — to verify the real board with a multimeter.
- **Shareable URLs** — the full state compresses into `#z=...` (~4KB for the sample board); paste the link anywhere, no server needed. Opening a link adds the board as a new proposal — it never overwrites your local work.
- **Parts palette** — add parts (R / film / ceramic / electrolytic / DIP-8 IC) from a form with footprint-checked auto-placement, edit labels and per-lead net assignment with autocomplete, delete parts. No agent required to start a board from scratch.
- **KiCAD netlist import** — open or drop a `.net` (s-expression) file: 2-pin and DIP-8 components are placed on a fresh board with nets and colors, ready for the solver.
- **1:1 print** — print at exact 2.54mm pitch and lay the sheet on the real board to verify; combine with mirror view for a backside (solder-side) sheet.
- **Diff view** — live overlay comparing the current board against its unedited original (plan vs as-built) or any other proposal (pick from Ctrl+K): moved parts, added/removed wires and bridges, with a delta summary in the status bar.
- **Editor UX** — segmented modes (1-5 keys), command palette (Ctrl+K), undo (Ctrl+Z), zoom / pinch zoom, hover inspector (hole / net), layer toggles, lock parts, block holes, proposals as switchable tabs, autosave to localStorage, JSON drag & drop. English / Japanese UI (auto-detected, toggle in header).

## State schema (v1)

```jsonc
{
  "grid": { "cols": 17, "rows": 14 },
  "netColors": { "VCC": "#d62839" },
  "leads":  { "U1.8": { "net": "VCC", "at": [6, 2] } },     // every occupied hole
  "parts": [
    { "id": "U1", "kind": "ic", "label": "U1", "pins": { "1": [6,5] }, "locked": true },
    { "id": "R1", "kind": "r", "label": "R1 1M", "leads": [[13,2],[16,2]],
      "leadNames": ["R1.a","R1.b"], "locked": false, "standing": false }
  ],
  "padBridges": [ [[5,1],[5,2]] ],                           // adjacent solder bridges
  "wires": [ { "net": "VCC",
    "a": { "tap": "U1.8", "pad": [6,2], "hole": [6,1], "bridgeTo": [6,2], "direct": false },
    "b": { "tap": "U2.8", "pad": [12,10], "hole": [12,9], "bridgeTo": [12,10], "direct": false } } ],
  "blockedHoles": [ [3,7] ]                                  // physically unusable holes
}
```

A wire endpoint is a `hole` (where the copper wire is inserted) plus a `bridgeTo` (the adjacent same-net hole it is solder-bridged to). `hole == pad` with `direct: true` means the wire is soldered straight onto the lead.

Files: `examples/client-hardware_tap_buffer.json` (sample project, 2 proposals), `config.example.json` / `perfwire_config.json` (threshold file for the Python solver — same content; `perfwire_config.json` is the default the solver loads when `--config` is omitted), `tools/make_link.py` (state JSON → `#z=` editor deep link).

## CI

`.github/workflows/ci.yml` runs on every push / PR:

- `tools/extract_check.mjs` — parses the inline script of `index.html` (syntax gate) and validates the embedded sample data.
- `tools/check_manifests.mjs` — validates `.claude-plugin/plugin.json` + `marketplace.json` (required fields, marketplace description, version agreement, and that the skill exists at the path `plugin.json` points to).
- `tools/ci_smoke.py` — runs `solver.py` on every sample proposal and asserts a schema-complete, fully-wired output.

## Background

Extracted from a real project: a 2× opamp-ic active buffer for a telephone-client-hardware audio tap, hand-built on a cut piece of perfboard. Photo-based position guessing failed three times; the drag-editor + solver + audit loop is what actually worked. The sample data is that real board.

## Roadmap

- Stripboard (Veroboard) support — copper strips + track cuts instead of solder bridges
- JS↔Python solver parity (golden tests) — requires factoring the in-browser solver into an importable module first
- Crosstalk model for parallel wire runs, ground-topology (star) scoring, guard rings
- i18n: UI chrome (buttons, sliders, hints, commands) ships in English/Japanese — auto-detected from the browser, toggle in the header. Generated reports (audit panel, guide steps, continuity checklist) are still Japanese-only.

## License

MIT
