#!/usr/bin/env python3
"""
verify_stock.py -- ground-truth test for the DECORATE converter.

The ZDoom wiki publishes DECORATE definitions for the stock Doom monsters.
Those monsters already exist in the vanilla thing table, so converting their
DECORATE and comparing against the real thing is a true correctness check
rather than an eyeball test: properties, flags, and every state in every
chain can be diffed against known-good data.

Run:  python verify_stock.py [corpus.dec]

Reports per monster:
  PROP  mismatches in health/radius/height/mass/speed/damage/painchance
  FLAG  mismatches in the resulting flag set
  STATE mismatches walking each label's chain (sprite, frame, tics, bright,
        action pointer)

Sound properties are deliberately excluded: ZDoom uses SNDINFO logical names
("caco/sight") while DEH addresses sound lumps by index, so they cannot and
should not match.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from decorate_convert import parse_decorate, resolve_inheritance, COMBO_FLAGS, FLAG_MAP

DATA = os.path.join(ROOT, "data")


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


# DECORATE actor name -> vanilla DEH thing slot
EXPECT_SLOT = {
    "zombieman": 2,
    "shotgunguy": 3,
    "doomimp": 12,
    "demon": 13,
    "spectre": 14,
    "cacodemon": 15,
    "baronofhell": 16,
    "hellknight": 18,
    "lostsoul": 19,
    "spidermastermind": 20,
    "arachnotron": 21,
    "cyberdemon": 22,
    "revenant": 6,
    "fatso": 9,
    "chaingunguy": 11,
    "archvile": 4,
}

PROP_FIELDS = [
    # (decorate prop, mobjinfo field, scale) -- scale 65536 for fixed-point
    ("health", "spawnhealth", 1),
    ("radius", "radius", 65536),
    ("height", "height", 65536),
    ("mass", "mass", 1),
    ("speed", "speed", 1),
    ("damage", "damage", 1),
    ("painchance", "painchance", 1),
]

LABEL_TO_FIELD = {
    "spawn": "spawnstate", "see": "seestate", "melee": "meleestate",
    "missile": "missilestate", "pain": "painstate", "death": "deathstate",
    "xdeath": "xdeathstate", "raise": "raisestate",
}

# Places where ZDoom's actor definition intentionally differs from the vanilla
# thing. A mismatch here is a real engine/port difference, not a converter bug,
# so it is reported as a NOTE and does not fail the run.
KNOWN_DIVERGENCE = {
    ("lostsoul", "COUNTKILL"):
        "vanilla MT_SKULL carries no COUNTKILL -- Lost Souls do not add to a "
        "map's monster total in Doom -- while ZDoom's MONSTER combo grants it. "
        "If the stock wiki definition has an explicit -COUNTKILL, adding it to "
        "the corpus resolves this.",
}

# ZDoom pointer name -> DECOHack name, for state comparison
POINTER_RENAME = {"A_NOBLOCKING": "A_FALL"}
# ZDoom-only pointers that vanilla simply doesn't have; ignore when diffing
POINTER_IGNORE = {"A_SETFLOORCLIP", "A_UNSETFLOORCLIP"}


class Checker:
    def __init__(self):
        self.states = load("states.json")
        self.sprites = load("sprites.json")
        self.mobj = load("mobjinfo.json")
        self.flags = load("flags.json")["doom"]
        self.alias = load("aliases.json")["things"]
        self.fails = 0
        self.checks = 0
        self.notes = []

    def flag_names(self, value):
        return {n for b, n in self.flags.items() if value & int(b)}

    def base_state(self, i):
        b = self.states[i]
        return {
            "sprite": self.sprites[b["sprite"]] if b["sprite"] < len(self.sprites) else "?",
            "frame": b["frame"] & 0x7FFF,
            "bright": b["bright"] or bool(b["frame"] & 0x8000),
            "tics": b["tics"],
            "action": (b.get("action") or "").upper(),
            "next": b["next"],
        }

    def expand_decorate_states(self, actor):
        """Flatten a DECORATE actor's states into label -> [state dicts]."""
        out = {}
        for label, entries in actor.states.items():
            seq = []
            for e in entries:
                if "ctrl" in e:
                    continue
                for ch in e["frames"]:
                    seq.append({
                        "sprite": e["sprite"].upper(),
                        "frame": ord(ch.upper()) - ord("A"),
                        "bright": "Bright" in e["flags"],
                        "tics": e["dur"],
                        "action": self._norm_action(e.get("action")),
                    })
            out[label.lower()] = seq
        return out

    @staticmethod
    def _norm_action(action):
        if not action:
            return ""
        name = action.split("(")[0].strip().upper()
        name = POINTER_RENAME.get(name, name)
        if name in POINTER_IGNORE:
            return ""
        return name

    def decorate_flags(self, actor):
        out = set()
        for combo in actor.combos:
            out |= set(COMBO_FLAGS.get(combo, []))
        for f in actor.flag_add:
            m = FLAG_MAP.get(f.upper())
            if m:
                out.add(m)
        for f in actor.flag_remove:
            m = FLAG_MAP.get(f.upper())
            if m:
                out.discard(m)
        return out

    def check(self, actor):
        slot = EXPECT_SLOT.get(actor.name.lower())
        name = f"{actor.name} (thing {slot} {self.alias.get(str(slot), '?')})"
        if slot is None:
            print(f"  SKIP {actor.name}: not a known stock monster")
            return
        base = self.mobj[slot - 1]
        problems = []

        # properties
        for prop, field, scale in PROP_FIELDS:
            if prop not in actor.props:
                continue
            toks = actor.props[prop]
            if not toks:
                continue
            try:
                want = float(toks[0].strip('"'))
            except ValueError:
                continue
            got = base.get(field, 0)
            got_scaled = got / scale if scale != 1 else got
            self.checks += 1
            if abs(got_scaled - want) > 0.001:
                problems.append(f"PROP  {prop}: DECORATE={want:g} vanilla={got_scaled:g}")

        # flags
        self.checks += 1
        want_flags = self.decorate_flags(actor)
        got_flags = self.flag_names(base.get("flags", 0))
        if want_flags != got_flags:
            key = actor.name.lower()
            missing, extra, notes = [], [], []
            for f in sorted(got_flags - want_flags):
                (notes if (key, f) in KNOWN_DIVERGENCE else missing).append(f)
            for f in sorted(want_flags - got_flags):
                (notes if (key, f) in KNOWN_DIVERGENCE else extra).append(f)
            bits = []
            if missing:
                bits.append(f"vanilla has but DECORATE lacks: {missing}")
            if extra:
                bits.append(f"DECORATE has but vanilla lacks: {extra}")
            if bits:
                problems.append("FLAG  " + "; ".join(bits))
            for f in notes:
                self.notes.append(f"{actor.name}: {f} -- "
                                  f"{KNOWN_DIVERGENCE[(key, f)]}")

        # states
        dec_states = self.expand_decorate_states(actor)
        for label, seq in dec_states.items():
            field = LABEL_TO_FIELD.get(label)
            if not field or not seq:
                continue
            start = base.get(field, 0)
            if not start:
                problems.append(f"STATE {label}: vanilla has no {field}")
                continue
            cur = start
            for n, want in enumerate(seq):
                self.checks += 1
                got = self.base_state(cur)
                diffs = []
                if got["sprite"] != want["sprite"]:
                    diffs.append(f"sprite {want['sprite']}!={got['sprite']}")
                if got["frame"] != want["frame"]:
                    diffs.append(f"frame {chr(65+want['frame'])}!={chr(65+got['frame'])}")
                if got["tics"] != want["tics"]:
                    diffs.append(f"tics {want['tics']}!={got['tics']}")
                if got["bright"] != want["bright"]:
                    diffs.append(f"bright {want['bright']}!={got['bright']}")
                if got["action"] != want["action"]:
                    diffs.append(f"action {want['action'] or '-'}!={got['action'] or '-'}")
                if diffs:
                    problems.append(f"STATE {label}[{n}] (vanilla state {cur}): "
                                    + ", ".join(diffs))
                cur = got["next"]
                if not cur:
                    break

        if problems:
            self.fails += len(problems)
            print(f"  FAIL {name}")
            for p in problems:
                print(f"        {p}")
        else:
            print(f"  ok   {name}")


def main():
    corpus = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "stock_monsters.dec")
    with open(corpus, "r", encoding="latin-1", errors="replace") as f:
        actors = parse_decorate(f.read())
    resolved = resolve_inheritance(actors)
    print(f"Verifying {len(resolved)} DECORATE actor(s) against the vanilla "
          f"thing table\n")
    c = Checker()
    for _name, (actor, _notes) in resolved.items():
        c.check(actor)
    if c.notes:
        print("\nKnown ZDoom/vanilla divergences (not converter bugs):")
        for n in c.notes:
            print(f"  - {n}")
    print(f"\n{c.checks} comparison(s), {c.fails} mismatch(es), "
          f"{len(c.notes)} documented divergence(s)")
    return 1 if c.fails else 0


if __name__ == "__main__":
    sys.exit(main())
