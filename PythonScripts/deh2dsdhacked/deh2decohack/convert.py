#!/usr/bin/env python3
"""
convert.py -- DeHackEd (.deh/.bex) to DECOHack (.dh) converter.

Target: DECOHack `dsdhacked` patch format, MBF21 feature set, dsda-doom.

Usage:
    python convert.py input.deh [-o output.dh]

If -o is omitted, output is written next to the input with a .dh extension.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deco_emitter import convert


def main():
    ap = argparse.ArgumentParser(
        description="Convert a DeHackEd patch to human-readable DECOHack "
                    "source (dsdhacked / MBF21 / dsda-doom).")
    ap.add_argument("input", help="input .deh/.bex file")
    ap.add_argument("-o", "--output", help="output .dh file "
                    "(default: input name with .dh extension)")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1

    out_path = args.output or os.path.splitext(args.input)[0] + ".dh"

    try:
        text = convert(args.input)
    except Exception as e:
        print(f"error: conversion failed: {e}", file=sys.stderr)
        raise

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    warn_count = text.count("\n//   ")
    print(f"wrote {out_path} ({text.count(chr(10))} lines)")
    if warn_count:
        print(f"NOTE: {warn_count} converter warning(s) -- see the end of the "
              f"output file.")
    print("Remember to compile the result with DECOHack to validate it:")
    print(f"    decohack {os.path.basename(out_path)} -o dehacked.deh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
