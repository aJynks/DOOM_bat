#!/usr/bin/env python3
import argparse
import sys


def build_cascade_values(n: int) -> list[int]:
    if n < 2:
        raise ValueError("n must be at least 2")
    return [round(256 / i) for i in range(n, 1, -1)]


def print_help():
    print("usage: cascadeChange.py [-h] -n NUM_OPTIONS")
    print("example : py cascadeChange.py -n 12")


def main() -> None:
    if "-h" in sys.argv or "--help" in sys.argv:
        print_help()
        return

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-n", "--num-options", type=int, required=True)
    args = parser.parse_args()

    n = args.num_options
    values = build_cascade_values(n)

    # DECOHack layout first
    print("Spawn:")
    for i, value in enumerate(values, start=1):
        print(f'    TNT1 A 0 A_RandomJump("Option{i}", {value})')
    print(f"    Goto Option{n}")

    # separator
    print("--------------------")

    # summary after
    print(f"Options: {n}")
    print("A_RandomJump values:")
    print(", ".join(str(v) for v in values))


if __name__ == "__main__":
    main()