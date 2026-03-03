#!/usr/bin/env python3
import argparse
import sys
from dataclasses import dataclass
from typing import List, Optional, Union, Tuple


# -------------------------
# helpers
# -------------------------

def parse_bias(bias_str: str, n: int) -> List[int]:
    parts = bias_str.split(",")
    if len(parts) != n:
        raise ValueError(f"-bias must have exactly {n} comma-separated integers (got {len(parts)}).")

    vals: List[int] = []
    for p in parts:
        p = p.strip()
        if p == "":
            raise ValueError("Empty value in -bias.")
        if not p.isdigit():
            raise ValueError(f"Bias values must be whole numbers only (bad value: {p!r}).")
        vals.append(int(p))

    total = sum(vals)
    if total > 100:
        raise ValueError(f"Bias values add up to {total} (> 100).")

    if total < 100:
        vals[-1] += (100 - total)

    # reorder so Outcome_0 has most chance, Outcome_last has least
    vals.sort(reverse=True)
    return vals


def thr_from_ratio(w_left: int, w_total: int) -> int:
    # A_RandomJump threshold 0..255 ~ w_left/w_total
    if w_total <= 0:
        return 0
    thr = int(round(256.0 * (w_left / w_total)))
    if thr < 0:
        thr = 0
    if thr > 255:
        thr = 255
    return thr


# -------------------------
# tree
# -------------------------

@dataclass
class Leaf:
    idx: int
    weight: int

@dataclass
class Node:
    left: "Tree"
    right: "Tree"
    w_left: int
    w_total: int
    label: str = ""

Tree = Union[Leaf, Node]


def build_weighted_tree(leaves: List[Leaf]) -> Tree:
    # split list into two groups with closest total weight (keeps tree sensible)
    if len(leaves) == 1:
        return leaves[0]

    total = sum(x.weight for x in leaves)
    best_i = 1
    best_diff = 10**9
    running = 0
    for i in range(1, len(leaves)):
        running += leaves[i-1].weight
        diff = abs((total - running) - running)
        if diff < best_diff:
            best_diff = diff
            best_i = i

    left_list = leaves[:best_i]
    right_list = leaves[best_i:]

    w_left = sum(x.weight for x in left_list)
    return Node(
        left=build_weighted_tree(left_list),
        right=build_weighted_tree(right_list),
        w_left=w_left,
        w_total=total
    )


def assign_labels(tree: Tree) -> None:
    # Root is RJ_Entry; then RJ_Node_1.. etc
    counter = 0

    def rec(t: Tree, is_root: bool) -> None:
        nonlocal counter
        if isinstance(t, Leaf):
            return
        if is_root:
            t.label = "RJ_Entry"
        else:
            counter += 1
            t.label = f"RJ_Node_{counter}"
        rec(t.left, False)
        rec(t.right, False)

    rec(tree, True)


def label_of(t: Tree) -> str:
    if isinstance(t, Leaf):
        return f"RJ_Outcome_{t.idx + 1}"
    return t.label


# -------------------------
# emit
# -------------------------

def emit_nodes(tree: Tree, header: str, out: List[str]) -> None:
    # explicit else (Goto right) so order is irrelevant
    def rec(t: Tree) -> None:
        if isinstance(t, Leaf):
            return
        left_lbl = label_of(t.left)
        right_lbl = label_of(t.right)
        thr = thr_from_ratio(t.w_left, t.w_total)

        out.append(f"{t.label}:")
        out.append(f"\t{header} A_RandomJump({left_lbl}, {thr}) // ~{t.w_left}/{t.w_total}")
        out.append(f"\tGoto {right_lbl}")
        out.append("")
        rec(t.left)
        rec(t.right)

    rec(tree)


def generate(n: int, compact: bool, bias: Optional[List[int]]) -> str:
    header = "PLAY A 0"

    if bias is None:
        leaves = [Leaf(i, 1) for i in range(n)]
        mode = "Uniform"
    else:
        leaves = [Leaf(i, bias[i]) for i in range(n)]
        mode = f"Biased (sorted): {bias}"

    tree = build_weighted_tree(leaves)
    assign_labels(tree)

    out: List[str] = []
    out.append("/* =========================================================")
    out.append("   WEIGHTED BINARY CHOOSER (EXPLICIT ELSE BRANCHES)")
    out.append(f"   Outcomes: {n}")
    out.append(f"   Mode:     {mode}")
    out.append("   Notes:")
    out.append("     - Every node does A_RandomJump(left, thr) then Goto right.")
    out.append("     - This is correct regardless of label ordering in the file.")
    out.append("   ========================================================= */")
    out.append("")

    emit_nodes(tree, header, out)

    out.append("/* ----- RJ_Outcome_* targets (edit these) ----- */")
    for i in range(n):
        out.append(f"RJ_Outcome_{i+1}:")
        if bias is not None:
            out.append(f"\t// weight: {bias[i]}%")
        if compact:
            out.append(f"\t// put your spawn code here")
            out.append(f"\tGoto spawn_Something_{i+1}")
        else:
            out.append(f"\tGoto spawn_Something_{i+1}")
        out.append("")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("number", type=int, help="Number of outcomes (N).")
    ap.add_argument("-o", "--output", required=True, help="Output filename.")
    ap.add_argument("-compact", action="store_true", help="Keep outcomes as editable blocks; no extra indirection.")
    ap.add_argument("-bias", type=str, default=None,
                    help="Comma-separated whole-number %s (count must equal N). Error if sum>100. Remainder goes to last, then sorted desc.")
    args = ap.parse_args()

    n = args.number
    if n < 1:
        print("Error: number must be >= 1")
        return 2

    bias_vals: Optional[List[int]] = None
    if args.bias is not None:
        try:
            bias_vals = parse_bias(args.bias, n)
        except ValueError as e:
            print(f"Error: {e}")
            return 2

    text = generate(n, compact=args.compact, bias=bias_vals)
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
