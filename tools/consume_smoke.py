"""CI gate #7: prove perfwire works when CONSUMED as an installed plugin.

The failure this guards against: when perfwire is installed from the marketplace,
the plugin is copied to ~/.claude/plugins/cache/<marketplace>/perfwire/<version>/
while the consumer's working directory is an UNRELATED project. Any SKILL.md /
README command that calls solver.py / tools/*.py / config.example.json / index.html
by a bare cwd-relative path then fails ("can't open file 'solver.py'") because
those files are in the cache, not the consumer's cwd. ${CLAUDE_PLUGIN_ROOT} does
NOT help: it is not exported into the Bash tool's shell environment (only inline-
substituted in manifests/hooks). The fix is to drive every bundled-file reference
through an absolute plugin-root path.

This test reproduces the install layout deterministically (no `claude` CLI, no
network, no Chrome): it copies the bundled payload to a throwaway "cache" dir
OUTSIDE the repo, sets cwd to a SEPARATE "consumer project" dir, and asserts the
documented absolute-path invocations resolve and produce a real, NON-degraded
result. It also lints SKILL.md / README.md for the cwd-relative anti-pattern so
the docs cannot silently regress to the broken form.
"""

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAYLOAD_FILES = ["solver.py", "config.example.json", "index.html"]
PAYLOAD_DIRS = ["tools", "examples"]


def _run(args, cwd):
    # sys.executable == the interpreter CI already uses; mirrors an agent calling the bundled CLI by absolute path
    return subprocess.run([sys.executable, *args], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8")


def main() -> None:
    failures = []
    wires_a = None
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        cache = td / "cache" / "perfwire" / "0.0.0"  # mimic ~/.claude/plugins/cache/<mkt>/perfwire/<ver>/
        cache.mkdir(parents=True)
        for f in PAYLOAD_FILES:
            shutil.copy2(ROOT / f, cache / f)
        for d in PAYLOAD_DIRS:
            shutil.copytree(ROOT / d, cache / d)
        consumer = td / "consumer-project"  # the consumer's unrelated cwd (has NO solver.py/config in it)
        consumer.mkdir()
        sample = json.loads((cache / "examples" / "pico_motor_driver.json").read_text(encoding="utf-8"))
        prop = sample["proposals"][0]
        (consumer / "board.json").write_text(json.dumps(prop["state"]), encoding="utf-8")

        # 1) solver by ABSOLUTE cache path, NO --config, from the consumer cwd.
        r = _run([str(cache / "solver.py"), "board.json", "-o", "out.json"], cwd=consumer)
        if r.returncode != 0:
            failures.append(f"solver(no --config) exit {r.returncode}: {r.stderr[-400:]}")
        elif "DEGRADED" in (r.stderr or ""):
            failures.append("solver(no --config) emitted 'EE audit DEGRADED' — bundled config not self-resolved from cache")
        out_p = consumer / "out.json"
        if out_p.exists():
            res = json.loads(out_p.read_text(encoding="utf-8"))
            for key in ("grid", "leads", "parts", "padBridges", "wires", "stats", "ee"):
                if key not in res:
                    failures.append(f"out.json missing key '{key}'")
            wires_a = len(res.get("wires") or [])
            if not wires_a:
                failures.append("solver(no --config) produced no wires from the cache copy")
            if not (res.get("ee", {}).get("decouplingCoverage")):
                failures.append("EE audit ran empty (no decouplingCoverage) — config was not loaded from the cache copy")
            if res.get("ee", {}).get("degraded") is not False:
                failures.append(f"ee.degraded must be False on the auto-resolved-config consume path (got {res.get('ee', {}).get('degraded')!r})")
        else:
            failures.append("solver(no --config) wrote no out.json")

        # 2) solver WITH explicit --config (override form) -> identical wire count.
        r2 = _run([str(cache / "solver.py"), "board.json",
                   "--config", str(cache / "config.example.json"), "-o", "out2.json"], cwd=consumer)
        out2 = consumer / "out2.json"
        if r2.returncode == 0 and out2.exists():
            wires_b = len(json.loads(out2.read_text(encoding="utf-8")).get("wires") or [])
            if wires_a is not None and wires_a != wires_b:
                failures.append(f"wires differ with/without --config ({wires_a} vs {wires_b}) — config self-resolution inconsistent")
        else:
            failures.append(f"solver(--config) exit {r2.returncode}: {r2.stderr[-300:]}")

        # 3) make_link (absolute file:// base) -> read_link round-trip, from the consumer cwd.
        base = (cache / "index.html").resolve().as_uri()  # file:///C:/.../index.html (drive-letter on Windows)
        rl = _run([str(cache / "tools" / "make_link.py"), "out.json",
                   "--base", base, "--task", "consume-smoke"], cwd=consumer)
        link = (rl.stdout or "").strip()
        if rl.returncode != 0 or "#z=" not in link or not link.startswith("file:"):
            failures.append(f"make_link did not emit an absolute file:// #z= link: {link[:80]!r} {rl.stderr[-200:]}")
        else:
            rr = _run([str(cache / "tools" / "read_link.py"), link, "-o", "back.json"], cwd=consumer)
            back = consumer / "back.json"
            if rr.returncode != 0 or not back.exists():
                failures.append(f"read_link failed to decode the link: {rr.stderr[-200:]}")
            else:
                d = json.loads(back.read_text(encoding="utf-8"))
                if not all(k in d for k in ("grid", "parts", "leads")):
                    failures.append("round-trip JSON missing grid/parts/leads")
                if d.get("task") != "consume-smoke":
                    failures.append("round-trip lost the --task instruction")

    # 4) doc-consistency lint (SKILL.md only): the skill is loaded for BOTH the clone-and-open path
    #    (cwd == repo) AND the installed-plugin path (cwd == consumer project, scripts in cache), so it
    #    must drive every bundled-script call through an absolute plugin-root path — the absolute form
    #    works in both. (README is human prose where a clone-and-open `python3 solver.py` example is
    #    legitimate, so it is NOT linted.) Matches `python solver.py` / `python3 tools/make_link.py`
    #    but NOT `python "<PERFWIRE_ROOT>/solver.py"` / `"$PERFWIRE_PY" "$ROOT/tools/..."` (a quote or
    #    path sits before the script name).
    anti = re.compile(r'\bpython[0-9]?\s+(solver\.py|tools/(?:make_link|read_link)\.py)\b')
    for doc in (".claude/skills/perfwire/SKILL.md",):
        text = (ROOT / doc).read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            m = anti.search(line)
            if m:
                failures.append(f"{doc}:{i} invokes '{m.group(1)}' cwd-relative (consumer cwd != plugin dir; use the absolute PERFWIRE_ROOT form): {line.strip()[:90]}")

    if failures:
        print("\n".join("NG: " + f for f in failures))
        sys.exit(1)
    print(f"consume smoke: OK (cache-copy solver wires={wires_a}, --config parity, deep-link round-trip, docs consume-safe)")


if __name__ == "__main__":
    main()
