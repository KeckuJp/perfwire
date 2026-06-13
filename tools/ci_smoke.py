"""CI smoke test: run solver.py (wiring-only) on the bundled sample board.

Asserts the solver exits cleanly, emits a schema-complete state, and connects
every net (no warnings about unreachable pads beyond known direct-attaches).
"""

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    sample = json.loads((ROOT / "examples" / "client-hardware_tap_buffer.json").read_text(encoding="utf-8"))
    failures = []
    for prop in sample["proposals"]:
        with tempfile.TemporaryDirectory() as td:
            state_p = pathlib.Path(td) / "state.json"
            out_p = pathlib.Path(td) / "out.json"
            state_p.write_text(json.dumps(prop["state"]), encoding="utf-8")
            r = subprocess.run(
                # mirror the documented command: --config is required, else the EE audit runs empty
                [sys.executable, str(ROOT / "solver.py"), str(state_p),
                 "--config", str(ROOT / "config.example.json"), "-o", str(out_p)],
                capture_output=True,
                text=True,
            )
            name = prop["name"]
            if r.returncode != 0:
                failures.append(f"{name}: solver exit {r.returncode}\n{r.stderr[-500:]}")
                continue
            res = json.loads(out_p.read_text(encoding="utf-8"))
            for key in ("grid", "leads", "parts", "padBridges", "wires", "stats", "ee"):
                if key not in res:
                    failures.append(f"{name}: output missing key '{key}'")
            if not res.get("wires"):
                failures.append(f"{name}: solver produced no wires")
            ee = res.get("ee", {})
            for key in ("openNets", "singleLeadNets", "unconnectedLeads", "duplicateIds",
                        "polarity", "powerReach", "keepAway", "decouplingCoverage",
                        "floatingPowerPins", "multipleDrivers", "undrivenNets", "stripShorts",
                        "grounding", "guard", "crosstalk", "fabReady"):
                if key not in ee:
                    failures.append(f"{name}: ee missing ERC key '{key}'")
            # the bundled (perfboard) sample must have no hard ERC errors
            for key in ("openNets", "unconnectedLeads", "duplicateIds", "floatingPowerPins", "multipleDrivers", "stripShorts"):
                if ee.get(key):
                    failures.append(f"{name}: unexpected ERC error {key}={ee[key]}")
            if any(not p.get("ok") for p in ee.get("powerReach", [])):
                failures.append(f"{name}: unexpected power-reachability failure")
            if any(p.get("ok") is False for p in ee.get("polarity", [])):
                failures.append(f"{name}: unexpected reversed-polarity finding")
            print(f"OK: {name} -> wires={len(res.get('wires', []))} fabReady={ee.get('fabReady')} stats={res.get('stats')}")
    if failures:
        print("\n".join("NG: " + f for f in failures))
        sys.exit(1)
    print("solver smoke: all proposals OK")


if __name__ == "__main__":
    main()
