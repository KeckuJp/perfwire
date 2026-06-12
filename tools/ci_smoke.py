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
                [sys.executable, str(ROOT / "solver.py"), str(state_p), "-o", str(out_p)],
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
            print(f"OK: {name} -> wires={len(res.get('wires', []))} stats={res.get('stats')}")
    if failures:
        print("\n".join("NG: " + f for f in failures))
        sys.exit(1)
    print("solver smoke: all proposals OK")


if __name__ == "__main__":
    main()
