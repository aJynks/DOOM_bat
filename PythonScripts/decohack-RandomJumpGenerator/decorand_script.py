#!/usr/bin/env python3
"""
decorand_script.py

decorand: DECOHack random choice generator.
Generates DECOHack (MBF21) state code that picks one of N outcomes using
chained A_RandomJump calls. Linear cascade by default, weighted binary
tree with --tree. Supports weighting curves (-weight) and final
relative / absolute adjustments (-mod).

Standard library only (no dependency check needed).
Run with -h for the full guide.
"""

import argparse
import math
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

TOOL = "decorand"
FRAME = "TNT1 A 0"


# ---------------------------------------------------------------------------
# colour
# ---------------------------------------------------------------------------

def _enable_vt(handle_id: int) -> None:
    # turn on ANSI escape handling in the Windows console
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(handle_id)
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(h, ctypes.byref(mode)):
            k32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


def _colour_ok(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return stream.isatty()
    except Exception:
        return False


OUT_COLOUR = _colour_ok(sys.stdout)
ERR_COLOUR = _colour_ok(sys.stderr)
if os.name == "nt":
    if OUT_COLOUR:
        _enable_vt(-11)
    if ERR_COLOUR:
        _enable_vt(-12)


def _paint(code: str, text: str, on: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if on else text


def _pad(s: str, w: int) -> str:
    return s.ljust(w) if w else s


def _h(s: str) -> str:              # section header
    return _paint("1;96", s, OUT_COLOUR)


def _b(s: str, w: int = 0) -> str:  # bold
    return _paint("1", _pad(s, w), OUT_COLOUR)


def _k(s: str, w: int = 0) -> str:  # keyword / option (yellow)
    return _paint("93", _pad(s, w), OUT_COLOUR)


def _g(s: str, w: int = 0) -> str:  # example / good (green)
    return _paint("92", _pad(s, w), OUT_COLOUR)


def _code(s: str, w: int = 0) -> str:  # code (magenta)
    return _paint("95", _pad(s, w), OUT_COLOUR)


def _dim(s: str, w: int = 0) -> str:
    return _paint("2", _pad(s, w), OUT_COLOUR)


def _warn(s: str) -> str:
    return _paint("93;1", "warning: ", ERR_COLOUR) + s


def _err(s: str) -> str:
    return _paint("91;1", "error: ", ERR_COLOUR) + s


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------

def help_text() -> str:
    L: List[str] = []
    a = L.append

    a("")
    a(_h(f"  {TOOL}") + _dim("  :  DECOHack random choice generator (A_RandomJump)"))
    a("")

    # ---- what is this for
    a(_h("WHAT IS THIS FOR?"))
    a("  DECOHack has no \"pick one of these N things\" command. The only random")
    a("  tool you get is " + _code("A_RandomJump(Label, chance)") + ", which is " + _b("ONE") + " coin flip:")
    a("  it rolls a number from 0 to 255, and if the roll is under " + _k("chance") + " it")
    a("  jumps to " + _k("Label") + ". Otherwise it carries on to the next line.")
    a("")
    a("    chance " + _k("128") + " = 128/256 = " + _g("50%"))
    a("    chance " + _k("64") + "  =  64/256 = " + _g("25%"))
    a("    chance " + _k("1") + "   =   1/256 = " + _g("about 0.4%") + " (the smallest step there is)")
    a("")
    a("  To pick one of 5 outcomes you have to chain several flips together,")
    a("  with the right chance on each one, so every outcome ends up with the")
    a("  share you want. Working that out by hand is a pain. This tool does")
    a("  the maths and prints finished state code you can paste in.")
    a("")

    # ---- layouts
    a(_h("THE TWO LAYOUTS"))
    a("  " + _k("LINEAR") + _dim(" (default)") + "   one flip after another, like a queue")
    a("    Each line asks \"is it THIS one?\" If not, it falls to the next line.")
    a("")
    a("      " + _code("Spawn:"))
    a("        " + _code("TNT1 A 0 A_RandomJump(Option1, 51) ", 38) + _dim("51/256 = 1 in 5"))
    a("        " + _code("TNT1 A 0 A_RandomJump(Option2, 64) ", 38) + _dim("1 in 4 of what is left"))
    a("        " + _code("TNT1 A 0 A_RandomJump(Option3, 85) ", 38) + _dim("1 in 3 of what is left"))
    a("        " + _code("TNT1 A 0 A_RandomJump(Option4, 128)", 38) + _dim("1 in 2 of what is left"))
    a("        " + _code("Goto Option5", 38) + _dim("whatever made it this far"))
    a("")
    a("    The chances go UP each line because fewer outcomes are left to")
    a("    share the roll. The end result: every option gets 1 in 5.")
    a("    Easy to read. Worst case it rolls N-1 times.")
    a("")
    a("  " + _k("TREE") + _dim(" (--tree)") + "   split the group in two, then in two again")
    a("    The first flip picks \"left group or right group\", the next flip")
    a("    splits that group, and so on until one outcome is left. Groups are")
    a("    split by weight, not by count, so heavy outcomes sit near the top.")
    a("    Fewer rolls for big N (about log2 of N), harder to read by eye.")
    a("")
    a("  Both layouts give the same odds. Pick whichever you prefer reading.")
    a("")

    # ---- weighting
    a(_h("WEIGHTING") + _dim("  (-weight)"))
    a("  With no -weight, every outcome gets an equal share.")
    a("")
    a("    " + _k("easein", 12) + "shares " + _b("RISE") + ": Option1 is the rarest, the last is most common")
    a("    " + _k("easeout", 12) + "shares " + _b("FALL") + ": Option1 is the most common, the last is rarest")
    a("    " + _k(":P", 12) + "curve strength, e.g. " + _g("easein:3") + ". Default 2. Higher = steeper.")
    a("    " + " " * 12 + "1 gives a straight, even ramp.")
    a("    " + _k("40,25,15,..", 12) + "your own numbers, one per outcome, in " + _b("YOUR") + " order.")
    a("    " + " " * 12 + "They are ratios, so they do not need to add up to 100:")
    a("    " + " " * 12 + _g("2,1,1") + " means Option1 is twice as likely as each other one.")
    a("")
    a("  Example with 5 outcomes:")
    a("    " + _g("easein:1", 12) + _dim(" 4.0%   12.0%   20.0%   28.0%   36.0%"))
    a("    " + _g("easein", 12) + _dim(" 0.6%    5.5%   15.2%   29.7%   49.1%"))
    a("    " + _g("easeout", 12) + _dim("49.1%   29.7%   15.2%    5.5%    0.6%"))
    a("")

    # ---- mods
    a(_h("FINAL ADJUSTMENT") + _dim("  (-mod)"))
    a("  Applied " + _b("AFTER") + " -weight. Think of the odds as a pie cut into slices that")
    a("  always add up to 100%. A mod makes one slice bigger or smaller, then")
    a("  the pie is re-shared so it still adds up to 100%.")
    a("")
    a("  Format:  " + _k("<outcome><+ or -><amount>[pt]") + "     e.g.  " + _g("3+10   2-25   4+15pt"))
    a("")
    a("    " + _g("3+10", 9) + _b("RELATIVE") + ": make Option3 10% bigger than it currently is.")
    a("    " + " " * 9 + "A 20% slice becomes 22%, then everyone is squeezed a little")
    a("    " + " " * 9 + "to fit, so it ends near 21.6%. A gentle nudge. Small slices")
    a("    " + " " * 9 + "get small nudges.")
    a("")
    a("    " + _g("3+10pt", 9) + _b("ABSOLUTE") + ": add 10 points to Option3. A 20% slice becomes")
    a("    " + " " * 9 + "exactly 30%. Only the outcomes you did NOT mod shrink to")
    a("    " + " " * 9 + "make room. A big shove, the same size wherever the slice")
    a("    " + " " * 9 + "started.")
    a("")
    a("  Same mod, different starting slice:")
    a("    " + _dim("starting at", 14) + _dim("5%".rjust(6)) + _dim("20%".rjust(8)) + _dim("50%".rjust(8)))
    a("    " + _g("3+20", 14) + "6%".rjust(6) + "24%".rjust(8) + "60%".rjust(8) + _dim("   (then re-shared)"))
    a("    " + _g("3+20pt", 14) + "25%".rjust(6) + "40%".rjust(8) + "70%".rjust(8) + _dim("   (exact)"))
    a("")
    a("  Use - to make an outcome rarer: " + _g("2-15") + " (15% smaller) or " + _g("2-15pt") + " (15 points less).")
    a("")
    a("  Order of operations:")
    a("    " + _k("1.") + " -weight builds the starting shares (or equal shares)")
    a("    " + _k("2.") + " relative mods are applied, then everything is re-shared")
    a("    " + _k("3.") + " absolute mods are pinned to exact values, and every un-pinned")
    a("       outcome grows or shrinks evenly to fill the rest")
    a("    " + _k("4.") + " the shares are turned into A_RandomJump chances (1..255)")
    a("")

    # ---- gotchas
    a(_h("THINGS TO KNOW"))
    a("  " + _k("*") + " Chances snap to steps of 1/256 (about 0.4%), so the " + _b("actual") + " odds can")
    a("    be a little off your " + _b("target") + ". The summary shows both.")
    a("  " + _k("*") + " If an outcome is so rare its chance rounds to 0 it could never")
    a("    happen. It is clamped to 1/256 and you get a warning.")
    a("  " + _k("*") + " Doom's random numbers come from a fixed 256-entry table that is not")
    a("    perfectly even, so real-world results drift a little anyway.")
    a("  " + _k("*") + " The tool stops with an error if: an outcome number is outside 1..N,")
    a("    the same outcome is modded twice, a mod takes an outcome to 0 or")
    a("    below, or absolute mods need 100% or more between them.")
    a("  " + _k("*") + " Leave the % sign off. It is accepted, but in cmd two % signs on one")
    a("    line can be read as a %variable%.")
    a("")

    # ---- output
    a(_h("OUTPUT"))
    a("  The DECOHack code goes to the console, or to a file with " + _k("-o") + ".")
    a("  Labels are " + _code("Spawn") + ", " + _code("Node1..") + " (tree only) and " + _code("Option1..OptionN") + ".")
    a("  Each Option block ends in " + _code("Goto SomethingN") + ": replace it with your code.")
    a("  A summary of target vs actual odds is printed after the code.")
    a("")

    # ---- usage (last on screen)
    a(_h("USAGE"))
    a("  " + _b(TOOL) + " " + _k("N") + " [" + _k("--tree") + "] [" + _k("-weight SPEC") + "] [" + _k("-mod MOD ...") + "] [" + _k("-o FILE") + "]")
    a("")
    a(_h("OPTIONS"))
    a("  " + _k("N", 15) + "number of outcomes (2 or more)")
    a("  " + _k("--tree", 15) + "use the tree layout instead of linear")
    a("  " + _k("-weight SPEC", 15) + "easein[:P]  |  easeout[:P]  |  w1,w2,...,wN")
    a("  " + _k("-mod MOD ...", 15) + "3+10 (relative)   3+10pt (absolute)   2-5   2-5pt")
    a("  " + _k("-o FILE", 15) + "write the code to FILE instead of the console")
    a("  " + _k("-h, --help", 15) + "show this help")
    a("")
    a(_h("EXAMPLES"))
    ex = [
        (f"{TOOL} 5", "5 equal outcomes, linear"),
        (f"{TOOL} 5 --tree", "same odds, tree layout"),
        (f"{TOOL} 6 -weight easein", "Option1 rarest, Option6 most common"),
        (f"{TOOL} 6 -weight easeout:3 -o pick.txt", "steep falloff, saved to a file"),
        (f"{TOOL} 4 -weight 50,25,15,10", "your own shares"),
        (f"{TOOL} 5 -mod 3+10 5+10pt", "nudge Option3, pin Option5 up 10 pts"),
        (f"{TOOL} 8 --tree -weight easein:1.5 -mod 1+20 8-5pt", ""),
    ]
    for cmd, note in ex:
        line = "  " + _g(cmd, 48)
        if note:
            line += _dim(note)
        a(line.rstrip())
    a("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class UserError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):  # route argparse errors through our style
        raise UserError(message)


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------

def parse_weight(spec: Optional[str], n: int) -> Tuple[List[float], str]:
    if spec is None:
        return [1.0] * n, "uniform"

    s = spec.strip().lower()
    m = re.fullmatch(r"(easein|easeout)(?::(\d+(?:\.\d+)?))?", s)
    if m:
        kind = m.group(1)
        p = float(m.group(2)) if m.group(2) else 2.0
        if p <= 0:
            raise UserError("curve strength must be greater than 0 (e.g. easein:2)")
        w: List[float] = []
        for i in range(n):
            t = (i + 0.5) / n          # midpoint of this outcome's slot
            w.append(t ** p if kind == "easein" else (1.0 - t) ** p)
        return w, f"{kind} (strength {p:g})"

    parts = [x.strip().rstrip("%").strip() for x in s.split(",")]
    if len(parts) != n:
        raise UserError(
            f"-weight {spec!r}: expected easein, easeout, or a list of exactly {n} "
            f"comma-separated numbers (got {len(parts)})"
        )
    vals: List[float] = []
    for x in parts:
        try:
            v = float(x)
        except ValueError:
            raise UserError(f"-weight value {x!r} is not a number")
        if not math.isfinite(v) or v <= 0:
            raise UserError(f"-weight value {x!r} must be greater than 0")
        vals.append(v)
    return vals, "manual " + ",".join(parts)


def normalise(w: List[float]) -> List[float]:
    total = sum(w)
    return [100.0 * x / total for x in w]


# ---------------------------------------------------------------------------
# mods
# ---------------------------------------------------------------------------

MOD_RE = re.compile(r"(\d+)([+-])(\d+(?:\.\d+)?)\s*%?\s*(pt)?\s*%?", re.IGNORECASE)


@dataclass
class Mod:
    idx: int        # 0-based
    sign: int       # +1 / -1
    amount: float
    absolute: bool
    raw: str


def parse_mods(raw_list: List[str], n: int) -> List[Mod]:
    mods: List[Mod] = []
    seen = {}
    for raw in raw_list:
        mt = MOD_RE.fullmatch(raw.strip())
        if not mt:
            raise UserError(
                f"bad -mod value {raw!r}. Use outcome+amount or outcome-amount, "
                f"add pt for absolute (e.g. 3+10, 3+10pt, 2-5)"
            )
        num = int(mt.group(1))
        if num < 1 or num > n:
            raise UserError(f"-mod {raw}: there is no Option{num} (outcomes are 1 to {n})")
        if num in seen:
            raise UserError(
                f"Option{num} is modded more than once ({seen[num]} and {raw}). "
                f"Combine them into one mod."
            )
        seen[num] = raw
        mods.append(Mod(
            idx=num - 1,
            sign=1 if mt.group(2) == "+" else -1,
            amount=float(mt.group(3)),
            absolute=mt.group(4) is not None,
            raw=raw.strip(),
        ))
    return mods


def apply_mods(pct: List[float], mods: List[Mod]) -> List[float]:
    n = len(pct)
    p = pct[:]

    # step 2: relative mods, then re-share
    for md in mods:
        if md.absolute:
            continue
        f = 1.0 + md.sign * md.amount / 100.0
        if f <= 0:
            raise UserError(
                f"-mod {md.raw}: a relative cut of {md.amount:g}% would take "
                f"Option{md.idx + 1} to 0% or below"
            )
        p[md.idx] *= f
    p = normalise(p)

    # step 3: absolute pins, un-pinned outcomes fill the rest
    pinned = {}
    for md in mods:
        if not md.absolute:
            continue
        t = p[md.idx] + md.sign * md.amount
        if t <= 0:
            raise UserError(
                f"-mod {md.raw}: Option{md.idx + 1} is at {p[md.idx]:.2f}%, "
                f"so -{md.amount:g}pt would take it to 0% or below"
            )
        pinned[md.idx] = t

    if pinned:
        total_pin = sum(pinned.values())
        free = [i for i in range(n) if i not in pinned]
        if free:
            if total_pin >= 100.0:
                raise UserError(
                    f"absolute mods ask for {total_pin:.2f}% between them, leaving "
                    f"nothing for the other outcomes (must be under 100%)"
                )
            free_sum = sum(p[i] for i in free)
            scale = (100.0 - total_pin) / free_sum
            for i in free:
                p[i] *= scale
        elif abs(total_pin - 100.0) > 1e-6:
            raise UserError(
                f"every outcome is pinned with pt mods, but they add up to "
                f"{total_pin:.2f}%, not 100%"
            )
        for i, t in pinned.items():
            p[i] = t

    return p


# ---------------------------------------------------------------------------
# thresholds
# ---------------------------------------------------------------------------

def to_thr(ratio: float, where: str, warns: List[str]) -> int:
    raw = 256.0 * ratio
    t = int(round(raw))
    if t < 1:
        warns.append(
            f"chance at {where} rounded to 0 ({raw:.2f}/256), clamped to 1/256. "
            f"That branch will be slightly more likely than asked."
        )
        t = 1
    elif t > 255:
        warns.append(
            f"chance at {where} rounded to 256 ({raw:.2f}/256), clamped to 255/256. "
            f"What comes after it will be slightly more likely than asked."
        )
        t = 255
    return t


# ---------------------------------------------------------------------------
# linear
# ---------------------------------------------------------------------------

def gen_linear(p: List[float], warns: List[str]):
    n = len(p)
    thrs: List[int] = []
    for k in range(n - 1):
        remaining = sum(p[k:])
        thrs.append(to_thr(p[k] / remaining, f"Option{k + 1}", warns))

    actual: List[float] = []
    reach = 1.0
    for t in thrs:
        actual.append(100.0 * reach * t / 256.0)
        reach *= (256 - t) / 256.0
    actual.append(100.0 * reach)

    body = ["Spawn:"]
    for k, t in enumerate(thrs):
        body.append(f"\t{FRAME} A_RandomJump(Option{k + 1}, {t}) // Option{k + 1} ~{actual[k]:.2f}%")
    body.append(f"\tGoto Option{n} // Option{n} ~{actual[-1]:.2f}%")
    body.append("")

    thr_desc = ", ".join(str(t) for t in thrs)
    return body, actual, thr_desc


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------

@dataclass
class Leaf:
    idx: int
    weight: float


@dataclass
class Node:
    left: "Tree"
    right: "Tree"
    w_left: float
    w_total: float
    label: str = ""
    thr: int = 0


Tree = Union[Leaf, Node]


def build_tree(leaves: List[Leaf]) -> Tree:
    if len(leaves) == 1:
        return leaves[0]
    total = sum(x.weight for x in leaves)
    best_i, best_diff, running = 1, float("inf"), 0.0
    for i in range(1, len(leaves)):
        running += leaves[i - 1].weight
        diff = abs((total - running) - running)
        if diff < best_diff:
            best_diff, best_i = diff, i
    left, right = leaves[:best_i], leaves[best_i:]
    return Node(
        left=build_tree(left),
        right=build_tree(right),
        w_left=sum(x.weight for x in left),
        w_total=total,
    )


def label_of(t: Tree) -> str:
    return f"Option{t.idx + 1}" if isinstance(t, Leaf) else t.label


def gen_tree(p: List[float], warns: List[str]):
    n = len(p)
    tree = build_tree([Leaf(i, p[i]) for i in range(n)])

    # labels, preorder: root is Spawn, then Node1, Node2, ...
    counter = 0
    order: List[Node] = []

    def assign(t: Tree, root: bool) -> None:
        nonlocal counter
        if isinstance(t, Leaf):
            return
        if root:
            t.label = "Spawn"
        else:
            counter += 1
            t.label = f"Node{counter}"
        order.append(t)
        assign(t.left, False)
        assign(t.right, False)

    assign(tree, True)

    for nd in order:
        nd.thr = to_thr(nd.w_left / nd.w_total, nd.label, warns)

    actual = [0.0] * n

    def walk(t: Tree, reach: float) -> None:
        if isinstance(t, Leaf):
            actual[t.idx] += 100.0 * reach
            return
        walk(t.left, reach * t.thr / 256.0)
        walk(t.right, reach * (256 - t.thr) / 256.0)

    walk(tree, 1.0)

    body: List[str] = []
    for nd in order:
        share = 100.0 * nd.w_left / nd.w_total
        body.append(f"{nd.label}:")
        body.append(
            f"\t{FRAME} A_RandomJump({label_of(nd.left)}, {nd.thr}) "
            f"// {share:.1f}% left / {100.0 - share:.1f}% right"
        )
        body.append(f"\tGoto {label_of(nd.right)}")
        body.append("")

    thr_desc = ", ".join(f"{nd.label} {nd.thr}" for nd in order)
    return body, actual, thr_desc


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

def render_code(mode: str, n: int, weight_desc: str, mods: List[Mod],
                body: List[str], pct: List[float], actual: List[float]) -> str:
    mods_desc = " ".join(md.raw for md in mods) if mods else "none"
    out = [
        "/* =========================================================",
        f"   A_RandomJump CHOOSER ({mode})",
        f"   Outcomes: {n}",
        f"   Weight:   {weight_desc}",
        f"   Mods:     {mods_desc}",
        f"   Made with {TOOL}. Edit the Option blocks at the bottom.",
        "   ========================================================= */",
        "",
    ]
    out.extend(body)
    out.append("/* ----- outcome targets (edit these) ----- */")
    for i in range(n):
        out.append(f"Option{i + 1}: // target {pct[i]:.2f}%, actual {actual[i]:.2f}%")
        out.append(f"\tGoto Something{i + 1}")
        out.append("")
    return "\n".join(out)


def render_summary(mode: str, n: int, weight_desc: str, mods: List[Mod],
                   pct: List[float], actual: List[float], thr_desc: str,
                   outfile: Optional[str]) -> str:
    mods_desc = " ".join(md.raw for md in mods) if mods else "none"
    L = [_dim("-" * 60)]
    L.append(" " + _k("Mode", 10) + mode)
    L.append(" " + _k("Outcomes", 10) + str(n))
    L.append(" " + _k("Weight", 10) + weight_desc)
    L.append(" " + _k("Mods", 10) + mods_desc)
    if outfile:
        L.append(" " + _k("Written", 10) + _g(outfile))
    L.append("")
    L.append(" " + _b("Outcome", 12) + _b("target".rjust(9)) + _b("actual".rjust(10)))
    for i in range(n):
        tgt = f"{pct[i]:.2f}%".rjust(9)
        act = f"{actual[i]:.2f}%".rjust(10)
        colour = _g if abs(actual[i] - pct[i]) <= 0.5 else _k
        L.append(" " + f"Option{i + 1}".ljust(12) + tgt + colour(act))
    L.append("")
    L.append(" " + _k("Chances", 10) + thr_desc)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def build_parser() -> Parser:
    p = Parser(prog=TOOL, add_help=False, allow_abbrev=False)
    p.add_argument("n", type=int)
    p.add_argument("--tree", action="store_true")
    p.add_argument("-weight", "--weight", dest="weight", default=None)
    p.add_argument("-mod", "--mod", dest="mods", nargs="+", default=None)
    p.add_argument("-o", "--output", dest="output", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or any(x in ("-h", "--help", "/?") for x in argv):
        print(help_text())
        return 0

    try:
        args = build_parser().parse_args(argv)
        n = args.n
        if n < 2:
            raise UserError("N must be 2 or more")

        weights, weight_desc = parse_weight(args.weight, n)
        pct = normalise(weights)
        mods = parse_mods(args.mods or [], n)
        pct = apply_mods(pct, mods)

        warns: List[str] = []
        mode = "tree" if args.tree else "linear"
        if args.tree:
            body, actual, thr_desc = gen_tree(pct, warns)
        else:
            body, actual, thr_desc = gen_linear(pct, warns)

        code = render_code(mode, n, weight_desc, mods, body, pct, actual)

        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8", newline="\n") as f:
                    f.write(code + "\n")
            except OSError as e:
                raise UserError(f"could not write {args.output!r}: {e}")
        else:
            print(code)

        print(render_summary(mode, n, weight_desc, mods, pct, actual, thr_desc, args.output))

        for w in warns:
            print(_warn(w), file=sys.stderr)
        return 0

    except UserError as e:
        print(_err(str(e)), file=sys.stderr)
        print(f"run {TOOL} -h for the full guide", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
