#!/usr/bin/env python3
"""
deh_parser.py -- DeHackEd (.deh/.bex) to DECOHack (.dh) converter.
(CLI entry point / driver script -- despite the name, the actual DEH
tokenizer/parser lives in deh_ir.py; this file is the one you run.)

Target: DECOHack `dsdhacked` patch format, MBF21 feature set, dsda-doom.

Usage (works from any current directory -- call it by full or relative path,
just like your other Doom scripts):
    python /path/to/deh_parser.py input.deh [-o output.dh]
    python /path/to/deh_parser.py C:\\mods\\mymod\\dehacked.deh

If -o is omitted, output is written next to the INPUT file (not next to this
script) with a .dh extension.

This script locates its sibling modules (deco_emitter.py, deh_ir.py) and the
data/ table folder relative to its OWN location on disk, not the caller's
current working directory -- so it behaves the same no matter where you run
it from.
"""
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from deco_emitter import convert


def main():
    ap = argparse.ArgumentParser(
        description="Convert a DeHackEd patch to human-readable DECOHack "
                    "source (dsdhacked / MBF21 / dsda-doom). Can be run "
                    "from any directory.")
    ap.add_argument("input", help="input .deh/.bex file (relative paths are "
                    "resolved against your current directory, as usual)")
    ap.add_argument("-o", "--output", help="output .dh file "
                    "(default: input name with .dh extension, written "
                    "alongside the input file)")
    args = ap.parse_args()

    in_path = os.path.abspath(args.input)
    if not os.path.isfile(in_path):
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1

    out_path = (os.path.abspath(args.output) if args.output
                else os.path.splitext(in_path)[0] + ".dh")

    data_dir = os.path.join(SCRIPT_DIR, "data")
    if not os.path.isdir(data_dir):
        print(f"error: base tables not found at {data_dir}", file=sys.stderr)
        print("       (data/*.json must live next to deh_parser.py, "
              "deco_emitter.py, and deh_ir.py)", file=sys.stderr)
        return 1

    try:
        text = convert(in_path)
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
