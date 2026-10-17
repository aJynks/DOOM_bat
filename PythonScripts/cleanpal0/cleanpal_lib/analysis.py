"""Exact / similar colour analysis and distance-pair tables."""

import heapq

from .colour import dist_de2000, dist_lab, dist_rgb, srgb_to_lab
from .constants import ENTRIES, METRICS


# ============================================================ union-find
class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # lower index becomes root (cosmetic; groups are sorted anyway)
            if ra < rb:
                self.p[rb] = ra
            else:
                self.p[ra] = rb



def build_pairs(rgbs):
    """Sorted (distance, a, b) lists for every metric, exact pairs excluded."""
    labs = [srgb_to_lab(*c) if c is not None else None for c in rgbs]
    out = {m: [] for m in METRICS}
    for a in range(ENTRIES):
        if rgbs[a] is None:
            continue
        for b in range(a + 1, ENTRIES):
            if rgbs[b] is None or rgbs[a] == rgbs[b]:
                continue
            out["de2000"].append((dist_de2000(labs[a], labs[b]), a, b))
            out["lab"].append((dist_lab(labs[a], labs[b]), a, b))
            out["rgb"].append((dist_rgb(rgbs[a], rgbs[b]), a, b))
    for v in out.values():
        v.sort()
    return labs, out


# ============================================================ analysis
def analyse(rgbs, pairs, do_exact, do_similar, tol, selection=None, deleted=None):
    """rgbs may contain None (empty slots). selection: None = similar matching
    works on the whole palette; a set = only those colours (they can only
    merge with each other; an empty set culls nothing)."""
    status = ["kept" if c is not None else "empty" for c in rgbs]
    for i in deleted or ():
        if status[i] == "kept":
            status[i] = "deleted"  # manual delete: out of all matching
    owner = list(range(ENTRIES))
    identical, similar = [], []

    if do_exact:
        first = {}
        groups = {}
        for i, c in enumerate(rgbs):
            if status[i] != "kept":
                continue
            if c in first:
                status[i] = "exact"
                owner[i] = first[c]
                groups[first[c]].append(i)
            else:
                first[c] = i
                groups[i] = [i]
        identical = sorted(g for g in groups.values() if len(g) > 1)

        if do_similar:
            alive = [status[i] == "kept" and (selection is None or i in selection)
                     for i in range(ENTRIES)]
            uf = UF(ENTRIES)
            for d, a, b in pairs:
                if d > tol:
                    break
                if alive[a] and alive[b]:
                    uf.union(a, b)
            clusters = {}
            for i in range(ENTRIES):
                if alive[i]:
                    clusters.setdefault(uf.find(i), []).append(i)
            for g in clusters.values():
                if len(g) > 1:
                    similar.append(g)
                    for i in g[1:]:
                        status[i] = "similar"
                        owner[i] = g[0]
            similar.sort()

    kept = [i for i in range(ENTRIES) if status[i] == "kept"]
    return {"status": status, "owner": owner, "identical": identical,
            "similar": similar, "kept": kept,
            "exact_all": identical, "similar_all": similar}


def result_entries(rgbs, res, align):
    if align:
        out = [rgbs[i] for i in res["kept"]]
        return out + [None] * (ENTRIES - len(out))
    return [rgbs[i] if res["status"][i] == "kept" else None for i in range(ENTRIES)]



def update_pairs(rgbs, labs, pairs, changed):
    """New (labs, pairs) after the colours at `changed` indices changed.
    Much faster than build_pairs when few entries change."""
    changed = set(changed)
    labs = list(labs)
    for i in changed:
        labs[i] = srgb_to_lab(*rgbs[i]) if rgbs[i] is not None else None
    out = {}
    for m in METRICS:
        keep = [t for t in pairs[m] if t[1] not in changed and t[2] not in changed]
        new = []
        for a in changed:
            if rgbs[a] is None:
                continue
            for b in range(ENTRIES):
                if b == a or rgbs[b] is None or rgbs[a] == rgbs[b]:
                    continue
                if b in changed and b < a:
                    continue                  # pair already done from b's side
                if m == "de2000":
                    d = dist_de2000(labs[a], labs[b])
                elif m == "lab":
                    d = dist_lab(labs[a], labs[b])
                else:
                    d = dist_rgb(rgbs[a], rgbs[b])
                new.append((d, min(a, b), max(a, b)))
        new.sort()
        out[m] = list(heapq.merge(keep, new))
    return labs, out
