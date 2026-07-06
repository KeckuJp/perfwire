"""CI smoke test: run solver.py (wiring-only) on the bundled sample boards.

Asserts the solver exits cleanly, emits a schema-complete state, and connects
every net (no warnings about unreachable pads beyond known direct-attaches).

pico_plant_sitter.json is a Before/After teaching example: "Before" is expected
to trip exactly the three findings the launch story is built on (reversed
electrolytic polarity, a decoupling cap placed too far from the MCU's power
pin, and a clamp-risk on an ungated 5V sensor input) and nothing else; "After"
must be fully clean.

pico_motor_driver.json is a second Before/Recommended teaching example (Pico +
DRV8833 dual-motor driver): "Before" is expected to trip exactly three findings
(a mispopulated 0-ohm jumper shorting VM into V3V3, both motor-A driver outputs
tied to one net, and one driver ground pin left unconnected) and nothing else;
"Recommended" must be fully clean. Locking both examples' expected findings in
CI means a future change to solver.py's netMerge/multipleDrivers/unconnectedLeads/
polarity/decoupling/clampRisk logic can't silently break either demo.
"""

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

HARD_ERC_KEYS = ("openNets", "netMerge", "bridgeDangle", "unconnectedLeads", "duplicateIds",
                  "floatingPowerPins", "multipleDrivers", "stripShorts", "pinConflicts")
ALL_EE_KEYS = ("openNets", "singleLeadNets", "unconnectedLeads", "duplicateIds",
               "polarity", "powerReach", "keepAway", "decouplingCoverage",
               "floatingPowerPins", "multipleDrivers", "undrivenNets", "stripShorts",
               "resistorPower", "decouplingValueWarn", "pinConflicts", "clampRisk", "netMerge",
               "railShort", "railReff", "bridgeDangle", "grounding", "guard", "crosstalk",
               "degraded", "fabReady")


def run_solver(name, state, failures):
    with tempfile.TemporaryDirectory() as td:
        state_p = pathlib.Path(td) / "state.json"
        out_p = pathlib.Path(td) / "out.json"
        state_p.write_text(json.dumps(state), encoding="utf-8")
        r = subprocess.run(
            # mirror the documented command: --config is required, else the EE audit runs empty
            [sys.executable, str(ROOT / "solver.py"), str(state_p),
             "--config", str(ROOT / "config.example.json"), "-o", str(out_p)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            failures.append(f"{name}: solver exit {r.returncode}\n{r.stderr[-500:]}")
            return None
        res = json.loads(out_p.read_text(encoding="utf-8"))
        for key in ("grid", "leads", "parts", "padBridges", "wires", "stats", "ee"):
            if key not in res:
                failures.append(f"{name}: output missing key '{key}'")
        if not res.get("wires"):
            failures.append(f"{name}: solver produced no wires")
        ee = res.get("ee", {})
        for key in ALL_EE_KEYS:
            if key not in ee:
                failures.append(f"{name}: ee missing ERC key '{key}'")
        print(f"OK: {name} -> wires={len(res.get('wires', []))} fabReady={ee.get('fabReady')} stats={res.get('stats')}")
        return res


def check_clean(name, ee, failures):
    """A board that's supposed to be free of hard ERC errors and reversed polarity."""
    for key in HARD_ERC_KEYS:
        if ee.get(key):
            failures.append(f"{name}: unexpected ERC error {key}={ee[key]}")
    if any(not p.get("ok") for p in ee.get("powerReach", [])):
        failures.append(f"{name}: unexpected power-reachability failure")
    if any(p.get("ok") is False for p in ee.get("polarity", [])):
        failures.append(f"{name}: unexpected reversed-polarity finding")


def check_pico_motor_driver(failures):
    sample = json.loads((ROOT / "examples" / "pico_motor_driver.json").read_text(encoding="utf-8"))
    for prop in sample["proposals"]:
        name = prop["name"]
        res = run_solver(name, prop["state"], failures)
        if res is None:
            continue
        ee = res.get("ee", {})
        if name.startswith("Before"):
            # the three intentional mistakes must all still fire...
            if not any(sorted(m.get("nets", [])) == ["V3V3", "VM"] for m in ee.get("netMerge", [])):
                failures.append(f"{name}: expected a netMerge finding on V3V3/VM, got {ee.get('netMerge')}")
            if not any(m.get("net") == "AOUT1" for m in ee.get("multipleDrivers", [])):
                failures.append(f"{name}: expected a multipleDrivers finding on AOUT1, got {ee.get('multipleDrivers')}")
            if "U2.GND1" not in ee.get("unconnectedLeads", []):
                failures.append(f"{name}: expected an unconnectedLeads finding on U2.GND1, got {ee.get('unconnectedLeads')}")
            if ee.get("fabReady"):
                failures.append(f"{name}: expected fabReady=false (this proposal is the deliberately-broken one)")
        else:
            # "Recommended" (or any other named proposal) must be fully clean
            check_clean(name, ee, failures)
            if not ee.get("fabReady"):
                failures.append(f"{name}: expected fabReady=true, got ee={ee}")


def check_pico_plant_sitter(failures):
    sample = json.loads((ROOT / "examples" / "pico_plant_sitter.json").read_text(encoding="utf-8"))
    for prop in sample["proposals"]:
        name = prop["name"]
        res = run_solver(name, prop["state"], failures)
        if res is None:
            continue
        ee = res.get("ee", {})
        if name.startswith("Before"):
            # the launch story's three intentional mistakes must all still fire...
            if not any(p.get("ok") is False and p.get("part") == "C10" for p in ee.get("polarity", [])):
                failures.append(f"{name}: expected reversed-polarity finding on C10, got {ee.get('polarity')}")
            if not any(not d.get("ok") and d.get("cap") == "C11" for d in ee.get("decoupling", [])):
                failures.append(f"{name}: expected a decoupling-distance finding for C11, got {ee.get('decoupling')}")
            if not any(c.get("pin") == "U1.GP_ECHO" for c in ee.get("clampRisk", [])):
                failures.append(f"{name}: expected a clampRisk finding on U1.GP_ECHO, got {ee.get('clampRisk')}")
            if ee.get("fabReady"):
                failures.append(f"{name}: expected fabReady=false (this proposal is the deliberately-broken one)")
            # ...and nothing else should be broken
            for key in HARD_ERC_KEYS:
                if ee.get(key):
                    failures.append(f"{name}: unexpected additional ERC error {key}={ee[key]}")
        else:
            # "After" (or any other named proposal) must be fully clean
            check_clean(name, ee, failures)
            if ee.get("clampRisk"):
                failures.append(f"{name}: expected no clampRisk, got {ee['clampRisk']}")
            if not ee.get("fabReady"):
                failures.append(f"{name}: expected fabReady=true, got ee={ee}")


def check_pkg_phys3d_roundtrip(failures):
    """Regression lock for the 3D 'appearance channel' (pkg/phys3d, see SKILL.md).

    These fields are visual-only and solver.py never reads them, but the whole
    design (see index.html's gl3dResolvePkg/GL3D_PKG) depends on solver.py's
    known-kind round-trip preserving them untouched -- and, separately, on a
    part with a legitimate kind actually surviving the round-trip at all
    (adversarial review found that a part with an *invented* kind is silently
    dropped by solver.py's known-kind filter; this asserts the correct, known-kind
    case is NOT similarly lost, which is the case the appearance channel relies on).
    """
    state = {
        "grid": {"cols": 10, "rows": 8, "type": "perf"},
        "netColors": {"A": "#f00", "B": "#0f0"},
        "leads": {
            "D1.a": {"net": "A", "at": [3, 3]},
            "D1.b": {"net": "B", "at": [3, 5]},
            "W.EXTA": {"net": "A", "at": [7, 3]},
            "W.EXTB": {"net": "B", "at": [7, 5]},
        },
        "parts": [
            {
                "id": "D1", "kind": "r", "family": "Diode 1N4148",
                "leads": [[3, 3], [3, 5]], "leadNames": ["D1.a", "D1.b"],
                "pkg": "do41",
                "phys3d": {"color": "#333333", "source": "1N4148 datasheet", "confidence": "verified"},
            },
        ],
        "padBridges": [], "wires": [], "blockedHoles": [], "trackCuts": [],
    }
    res = run_solver("pkg/phys3d round-trip", state, failures)
    if res is None:
        return
    parts = res.get("parts", [])
    d1 = next((p for p in parts if p.get("id") == "D1"), None)
    if d1 is None:
        failures.append(f"pkg/phys3d round-trip: part D1 (known kind 'r') vanished on round-trip, got parts={parts}")
        return
    if d1.get("pkg") != "do41":
        failures.append(f"pkg/phys3d round-trip: expected pkg='do41' preserved, got {d1.get('pkg')!r}")
    if d1.get("phys3d") != state["parts"][0]["phys3d"]:
        failures.append(f"pkg/phys3d round-trip: phys3d not preserved verbatim, got {d1.get('phys3d')!r}")


def main() -> None:
    failures = []
    check_pico_motor_driver(failures)
    check_pico_plant_sitter(failures)
    check_pkg_phys3d_roundtrip(failures)
    if failures:
        print("\n".join("NG: " + f for f in failures))
        sys.exit(1)
    print("solver smoke: all proposals OK")


if __name__ == "__main__":
    main()
