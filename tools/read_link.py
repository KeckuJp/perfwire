#!/usr/bin/env python3
"""Decode a perfwire deep-link (#z=...) back into the flat board-state JSON.

This is the inverse of tools/make_link.py — it closes the human -> agent half of
the round-trip loop. A beginner using the editor's **URL共有 / Share URL** button
gets a `index.html#z=<payload>` link copied to their clipboard; they paste it into
Claude Code, and the agent runs this to recover the exact board they were looking
at, then audits it (e.g. `solver.py - --config config.example.json` on the result).

The payload is raw-DEFLATE-compressed, base64url-encoded JSON (CompressionStream
'deflate-raw' == zlib wbits -15), byte-for-byte what make_link.py / the editor emit.

Accepts, in order of convenience for the human:
  - a full URL            "file:///.../index.html#z=AAAA..."  or  "https://host/index.html#z=..."
  - just the fragment     "#z=AAAA..."   or   "z=AAAA..."
  - the bare payload      "AAAA..."
read from an argument, from --in <file>, or from stdin.

Usage:
  python3 tools/read_link.py "index.html#z=..."            # -> state JSON to stdout
  python3 tools/read_link.py "#z=..." -o state.json        # -> file
  pbpaste | python3 tools/read_link.py                     # from clipboard via stdin
  python3 tools/read_link.py --in link.txt | python3 solver.py /dev/stdin --config config.example.json -o out.json
"""

import argparse
import base64
import json
import sys
import zlib


def payload_of(text):
    """Pull the base64url payload out of whatever form the human pasted."""
    s = (text or "").strip().strip('"').strip("'")
    if "#z=" in s:
        s = s.split("#z=", 1)[1]
    elif s.startswith("z="):
        s = s[2:]
    elif s.startswith("#z="):
        s = s[3:]
    # a pasted URL may carry trailing whitespace/newlines or a stray query — keep only token chars
    return s.split()[0] if s.split() else s


def decode_deeplink(text):
    p = payload_of(text)
    if not p:
        raise ValueError("no #z= payload found in input")
    pad = "=" * (-len(p) % 4)  # base64url is emitted without padding; restore it
    try:
        comp = base64.urlsafe_b64decode(p + pad)
    except (ValueError, TypeError) as e:
        raise ValueError("payload is not valid base64url: %s" % e)
    try:
        raw = zlib.decompress(comp, -15)  # -15 = raw deflate, matches make_link.py
    except zlib.error as e:
        raise ValueError("payload did not raw-inflate (is this a perfwire #z= link?): %s" % e)
    return json.loads(raw.decode("utf-8"))


def main():
    try:  # force UTF-8 stdout so non-ASCII state JSON isn't mangled when piped/redirected under a non-UTF-8 locale (Windows cp932)
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Decode a perfwire #z= deep-link into flat state JSON.")
    ap.add_argument("link", nargs="?", help="URL / #z=… fragment / bare payload (else read --in or stdin)")
    ap.add_argument("--in", dest="infile", help="read the link from a file instead of the argument")
    ap.add_argument("-o", dest="out", help="write state JSON here (default: stdout)")
    args = ap.parse_args()

    if args.link is not None:
        text = args.link
    elif args.infile:
        with open(args.infile, encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    try:
        state = decode_deeplink(text)
    except ValueError as e:
        sys.exit("error: %s" % e)

    out = json.dumps(state, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        sys.stderr.write("read_link: wrote %s\n" % args.out)
    else:
        print(out)


if __name__ == "__main__":
    main()
