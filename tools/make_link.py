#!/usr/bin/env python3
"""Generate a perfwire deep-link that preloads a board into the editor.

The editor (index.html) auto-imports a board from the URL fragment `#z=<payload>`,
where <payload> is the state JSON, raw-DEFLATE compressed and base64url-encoded.
This mirrors the in-browser "Share URL" feature byte-for-byte (CompressionStream
'deflate-raw' == zlib wbits -15).

INPUT MUST BE THE FLAT exportJSON SHAPE (singular keys: grid / netColors / leads /
parts / padBridges / wires / blockedHoles [, cfg]) — i.e. what `solver.py -o out.json`
emits, or the editor's "Export". It is NOT the proposals[] wrapper used by
examples/client-hardware_tap_buffer.json; the editor's loadHash reads flat fields only.
Opening the link APPENDS a new proposal and never overwrites the user's local work.

Usage:
  python3 tools/make_link.py out.json                       # -> index.html#z=...
  python3 tools/make_link.py out.json --base index.html     # custom base
  python3 tools/make_link.py out.json --base "file:///abs/path/index.html"
"""

import argparse
import base64
import json
import sys
import zlib


def perfwire_deeplink(state, base_url="index.html"):
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    co = zlib.compressobj(9, zlib.DEFLATED, -15)  # -15 = raw deflate, no zlib header
    comp = co.compress(raw) + co.flush()
    b = base64.b64encode(comp).decode("ascii").replace("+", "-").replace("/", "_").rstrip("=")
    return base_url + "#z=" + b


def main():
    ap = argparse.ArgumentParser(description="Make a perfwire #z= deep-link from a flat state JSON.")
    ap.add_argument("state", help="flat exportJSON / solver out.json")
    ap.add_argument("--base", default="index.html", help="base URL (default: index.html)")
    args = ap.parse_args()

    with open(args.state, encoding="utf-8") as f:
        state = json.load(f)
    if "proposals" in state:
        sys.exit(
            "error: input is the proposals[] wrapper (e.g. examples/client-hardware_tap_buffer.json). "
            "Pass a FLAT state — solver.py -o out.json output, or one proposal's .state."
        )
    print(perfwire_deeplink(state, args.base))


if __name__ == "__main__":
    main()
