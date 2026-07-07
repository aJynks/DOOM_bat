"""
deco_emitter.py
---------------
Stage 3 of the DEH -> DECOHack converter.

Takes the DehIR from deh_parser plus the base tables from ./data/ and emits
structured, human-readable DECOHack source targeting the `dsdhacked` patch
format (MBF21 feature set, dsda-doom).

Core ideas
==========
* The DEH file is a set of DELTAS against the engine base tables. We overlay
  those deltas onto DECOHack's own base state table to get the "effective"
  state table, then reconstruct labeled state blocks per thing/weapon by
  walking next-state chains from each entry point (spawn/see/pain/...).

* Reconstructed chains are emitted INSIDE thing blocks ("floating" states,
  reallocated freely by DECOHack) whenever that is provably safe. A state
  must instead be PINNED to its original index (emitted via top-level
  `state <N> { ... }` fill blocks, referenced by `state <label> <N>` /
  `goto <N>`) when its index identity matters:
    - referenced by more than one thing/weapon,
    - referenced by a STATE-type action pointer arg from outside the one
      thing that owns it,
    - referenced by the next-pointer of a state outside its owner chain,
    - or not reachable from any DEH-declared entry point at all (orphans -
      e.g. edits to vanilla states of things the DEH never declares).

* MBF-era pointers (A_Spawn, A_RandomJump, ...) read misc1/misc2; MBF21
  pointers read Args1-8. We keep one unified 8-slot arg array per state
  (base misc1/misc2 seed slots 0/1) and let the pointer's signature decide
  how many slots to read.
"""

import json
import os
import re
from collections import defaultdict

from deh_parser import DehIR

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

DEHEXTRA_STATE_START = 1089  # first "blank" extended state index
TNT1_SPRITE_INDEX = 138

# DEH thing frame fields -> DECOHack state label (emission order)
THING_LABELS = [
    ("initial_frame", "spawn"),
    ("first_moving_frame", "see"),
    ("close_attack_frame", "melee"),
    ("far_attack_frame", "missile"),
    ("injury_frame", "pain"),
    ("death_frame", "death"),
    ("exploding_frame", "xdeath"),
    ("respawn_frame", "raise"),
]
# NOTE: the DEH field names are crosswise to DECOHack's labels (verified
# empirically against DECOHack-compiled output): DEH "Select frame" is the
# A_Lower/downstate chain = DECOHack `deselect`, and DEH "Deselect frame"
# is the A_Raise/upstate chain = DECOHack `select`.
WEAPON_LABELS = [
    ("bobbing_frame", "ready"),
    ("select_frame", "deselect"),
    ("deselect_frame", "select"),
    ("shooting_frame", "fire"),
    ("firing_frame", "flash"),
]

# DEH thing property -> (decohack property, kind)
# kind: int | fixed16 | speed (fixed if missile) | sound | thing
THING_PROPS = [
    ("hit_points", "health", "int"),
    ("speed", "speed", "speed"),
    ("width", "radius", "fixed16"),
    ("height", "height", "fixed16"),
    ("missile_damage", "damage", "int"),
    ("reaction_time", "reactiontime", "int"),
    ("pain_chance", "painchance", "int"),
    ("mass", "mass", "int"),
    ("alert_sound", "seesound", "sound"),
    ("attack_sound", "attacksound", "sound"),
    ("pain_sound", "painsound", "sound"),
    ("death_sound", "deathsound", "sound"),
    ("action_sound", "activesound", "sound"),
    # Extended
    ("dropped_item", "dropitem", "thing"),
    # MBF21
    ("fast_speed", "fastspeed", "speed"),
    ("melee_range", "meleerange", "fixed16"),
    ("infighting_group", "infightinggroup", "int"),
    ("projectile_group", "projectilegroup", "int"),
    ("splash_group", "splashgroup", "int"),
    ("rip_sound", "ripsound", "sound"),
]

WEAPON_PROPS = [
    ("ammo_type", "ammotype", "int"),
    ("ammo_per_shot", "ammopershot", "int"),
    ("min_ammo", "minammo", "int"),
]

MISC_PROPS = [
    ("initial_health", "initialHealth"),
    ("initial_bullets", "initialBullets"),
    ("max_health", "maxHealth"),
    ("max_armor", "maxArmor"),
    ("green_armor_class", "greenArmorClass"),
    ("blue_armor_class", "blueArmorClass"),
    ("max_soulsphere", "maxSoulsphereHealth"),
    ("soulsphere_health", "soulsphereHealth"),
    ("megasphere_health", "megasphereHealth"),
    ("god_mode_health", "godModeHealth"),
    ("idfa_armor", "idfaArmor"),
    ("idfa_armor_class", "idfaArmorClass"),
    ("idkfa_armor", "idkfaArmor"),
    ("idkfa_armor_class", "idkfaArmorClass"),
    ("bfg_cells_shot", "bfgCellsPerShot"),
    ("monsters_infight", "monsterInfighting"),
]

MBF21_WEAPON_FLAGS = {
    1: "NOTHRUST", 2: "SILENT", 4: "NOAUTOFIRE", 8: "FLEEMELEE",
    16: "AUTOSWITCHFROM", 32: "NOAUTOSWITCHTO",
}

# MBF21 per-thing default flag words (deh thing number -> value).
# Derived from the MBF21 spec's vanilla-behavior replication; cyberdemon's
# value (303720) verified byte-identical against DECOHack's own tables.
MBF21_BASE_FLAGS = {
    4: 0x00086,    # Archvile: SHORTMRANGE|DMGIGNORED|NOTHRESHOLD
    6: 0x00140,    # Revenant: RANGEHALF|LONGMELEE
    9: 0x00400,    # Mancubus: MAP07BOSS1
    16: 0x01000,   # Baron of Hell: E1M8BOSS
    19: 0x00040,   # Lost Soul: RANGEHALF
    20: 0x54248,   # Spider Mastermind: NORADIUSDMG|RANGEHALF|BOSS|E3M8BOSS|E4M8BOSS|FULLVOLSOUNDS
    21: 0x00800,   # Arachnotron: MAP07BOSS2
    22: 0x4A268,   # Cyberdemon: NORADIUSDMG|HIGHERMPROB|RANGEHALF|BOSS|E2M8BOSS|E4M6BOSS|FULLVOLSOUNDS
}


def _load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


class Tables:
    def __init__(self):
        self.states = _load("states.json")          # list of dicts
        self.sprites = _load("sprites.json")        # list of names
        self.sounds = _load("sounds.json")          # list of names (0..114)
        self.mobjinfo = _load("mobjinfo.json")      # list of dicts
        self.pointers = _load("pointers.json")      # name -> sig
        self.flags = _load("flags.json")            # {"doom": bit->name, "mbf21": ...}
        self.strings = _load("strings.json")        # default text -> mnemonic
        # BEX codeptr names come without A_; build lookup
        self.ptr_by_bare = {k[2:].upper(): k for k in self.pointers}


class Emitter:
    def __init__(self, ir: DehIR, tables: Tables):
        self.ir = ir
        self.t = tables
        self.warnings = []
        self.out = []

        # sprite renames (boom-style name->name in [SPRITES], old Text blocks)
        self.sprite_rename = {}
        self.sprite_by_index = {}   # dsdhacked numeric [SPRITES] entries
        for k, v in ir.sprites.items():
            if isinstance(k, int):
                self.sprite_by_index[k] = v
            else:
                self.sprite_rename[k.upper()] = v.upper()
        for old, new in ir.text_renames:
            if len(old) == 4 and len(new) == 4 and old.isupper():
                self.sprite_rename[old] = new.upper()

        self.sound_rename = {}
        self.sound_by_index = {}
        for k, v in ir.sound_names.items():
            if isinstance(k, int):
                self.sound_by_index[k] = v
            else:
                self.sound_rename[k.lower()] = v.lower()

        self._build_effective_states()

    # ------------------------------------------------------------------
    # Effective state table
    # ------------------------------------------------------------------

    def _blank_state(self, i):
        return {"sprite": TNT1_SPRITE_INDEX, "frame": 0, "bright": False,
                "tics": -1, "next": i, "args": [0] * 8, "mbfflags": 0,
                "action": None}

    def _build_effective_states(self):
        self.eff = {}
        self.modified = set()

        base_len = len(self.t.states)
        touched = set(self.ir.frames) | set(self.ir.codeptr)
        for i in touched:
            if i < base_len:
                b = self.t.states[i]
                st = {"sprite": b["sprite"], "frame": b["frame"] & 0x7FFF,
                      "bright": b["bright"] or bool(b["frame"] & 0x8000),
                      "tics": b["tics"], "next": b["next"],
                      "args": [b.get("misc1", 0), b.get("misc2", 0), 0, 0, 0, 0, 0, 0],
                      "mbfflags": b.get("mbfflags", 0),
                      "action": b.get("action")}
            else:
                st = self._blank_state(i)

            f = self.ir.frames.get(i, {})
            if "sprite_number" in f:
                st["sprite"] = f["sprite_number"]
            if "sprite_subnumber" in f:
                sub = f["sprite_subnumber"]
                st["frame"] = sub & 0x7FFF
                st["bright"] = bool(sub & 0x8000)
            if "duration" in f:
                st["tics"] = f["duration"]
            if "next_frame" in f:
                st["next"] = f["next_frame"]
            if "mbf21_bits" in f:
                st["mbfflags"] = f["mbf21_bits"]
            if "args" in f:
                for slot, val in enumerate(f["args"]):
                    if val is not None:
                        st["args"][slot] = val
            if i in self.ir.codeptr:
                bare = self.ir.codeptr[i].upper()
                if bare in ("NULL", ""):
                    st["action"] = None
                else:
                    ptr = self.t.ptr_by_bare.get(bare)
                    if ptr is None:
                        self.warn(f"Frame {i}: unknown codepointer '{self.ir.codeptr[i]}' kept verbatim")
                        ptr = "A_" + self.ir.codeptr[i]
                    st["action"] = ptr

            self.eff[i] = st
            self.modified.add(i)

    def base_state(self, i):
        """Effective view of an UNMODIFIED base state (for chain walking)."""
        if i in self.eff:
            return self.eff[i]
        if i < len(self.t.states):
            b = self.t.states[i]
            return {"sprite": b["sprite"], "frame": b["frame"] & 0x7FFF,
                    "bright": b["bright"] or bool(b["frame"] & 0x8000),
                    "tics": b["tics"], "next": b["next"],
                    "args": [b.get("misc1", 0), b.get("misc2", 0), 0, 0, 0, 0, 0, 0],
                    "mbfflags": b.get("mbfflags", 0), "action": b.get("action")}
        return self._blank_state(i)

    # ------------------------------------------------------------------
    # Name resolution helpers
    # ------------------------------------------------------------------

    def sprite_name(self, idx):
        if idx < len(self.t.sprites):
            name = self.t.sprites[idx]
        elif idx in self.sprite_by_index:
            name = self.sprite_by_index[idx]
        else:
            self.warn(f"sprite index {idx} has no name (missing [SPRITES] entry?); using XX{idx % 100:02d}")
            name = f"XX{idx % 100:02d}"
        return self.sprite_rename.get(name, name)

    def sound_name(self, idx):
        if idx == 0:
            return None
        if idx < len(self.t.sounds):
            name = self.t.sounds[idx]
        elif 500 <= idx <= 699:
            name = "fre%03d" % (idx - 500)
        elif idx in self.sound_by_index:
            name = self.sound_by_index[idx]
        else:
            self.warn(f"sound index {idx} out of known range; emitted as fre-style guess")
            return None
        return self.sound_rename.get(name, name)

    def thing_display_name(self, num):
        if num in self.ir.things_names:
            return self.ir.things_names[num]
        if 1 <= num <= len(self.t.mobjinfo):
            return self.t.mobjinfo[num - 1]["name"]
        return f"Thing{num}"

    def base_thing(self, num):
        if 1 <= num <= len(self.t.mobjinfo):
            return self.t.mobjinfo[num - 1]
        return {}

    def warn(self, msg):
        self.warnings.append(msg)

    # ------------------------------------------------------------------
    # Ownership / pinning analysis
    # ------------------------------------------------------------------

    def analyze(self):
        # entry points: (owner_key, label, state)
        self.entries = []
        for num in sorted(self.ir.things):
            for field, label in THING_LABELS:
                if field in self.ir.things[num]:
                    self.entries.append((("thing", num), label, self.ir.things[num][field]))
        for num in sorted(self.ir.weapons):
            for field, label in WEAPON_LABELS:
                if field in self.ir.weapons[num]:
                    self.entries.append((("weapon", num), label, self.ir.weapons[num][field]))

        # Walk chains from every entry, recording owners per modified state.
        owners = defaultdict(set)
        for owner, _label, start in self.entries:
            for s in self._chain_states(start):
                owners[s].add(owner)

        # STATE-typed pointer args: record referencing owner (or None if
        # the referencing state is itself unowned).
        state_arg_refs = defaultdict(set)   # target -> set(referencing state idx)
        for i in self.modified:
            st = self.eff[i]
            if not st["action"]:
                continue
            sig = self.t.pointers.get(st["action"], {}).get("params", [])
            for slot, ptype in enumerate(sig):
                if ptype == "STATE" and st["args"][slot]:
                    state_arg_refs[st["args"][slot]].add(i)

        # Fixpoint: a jump-target chain reachable ONLY through STATE args of
        # states owned by exactly one thing belongs to that thing. This lets
        # A_RandomJump / A_HealChase / A_JumpIf* decision sub-chains float
        # inside the owner's states block with synthesized labels instead of
        # being pinned by index.
        self.pseudo_entries = defaultdict(list)   # owner -> [target state]
        changed = True
        while changed:
            changed = False
            for tgt, refs in list(state_arg_refs.items()):
                if tgt in owners or tgt not in self.modified or tgt == 0:
                    continue
                ref_owners = set()
                for r in refs:
                    ref_owners |= owners.get(r, set())
                if len(ref_owners) == 1:
                    owner = next(iter(ref_owners))
                    for s in self._chain_states(tgt):
                        owners[s].add(owner)
                    self.pseudo_entries[owner].append(tgt)
                    changed = True

        # next-references between modified states (for cross-chain pinning)
        next_refs = defaultdict(set)
        for i in self.modified:
            nxt = self.eff[i]["next"]
            if nxt in self.modified and nxt != i:
                next_refs[nxt].add(i)

        self.pinned = set()
        for s in self.modified:
            owns = owners.get(s, set())
            if len(owns) == 0:
                self.pinned.add(s)                       # orphan
            elif len(owns) > 1:
                self.pinned.add(s)                       # shared
            else:
                owner = next(iter(owns))
                # state-arg reference from a state not owned by same owner?
                for ref in state_arg_refs.get(s, ()):
                    if owners.get(ref, set()) != {owner}:
                        self.pinned.add(s)
                        break
                else:
                    # next-reference from outside the owner's own states
                    for ref in next_refs.get(s, ()):
                        if owners.get(ref, set()) != {owner}:
                            self.pinned.add(s)
                            break

        self.owners = owners
        self.state_arg_refs = state_arg_refs

    def _chain_states(self, start):
        """All MODIFIED states reachable from `start` by next-links without
        passing through an unmodified base state."""
        seen = []
        cur = start
        visited = set()
        while cur not in visited:
            visited.add(cur)
            if cur == 0 or cur not in self.modified:
                break
            seen.append(cur)
            cur = self.eff[cur]["next"]
        return seen

    # ------------------------------------------------------------------
    # Rendering primitives
    # ------------------------------------------------------------------

    @staticmethod
    def frame_letter(sub):
        return chr(ord("A") + sub)

    @staticmethod
    def fmt_fixed(v):
        if v % 65536 == 0:
            return "%d.0" % (v // 65536)
        # shortest decimal that round-trips back to the exact fixed value
        for nd in range(1, 6):
            d = round(v / 65536.0, nd)
            if int(round(d * 65536)) == v:
                s = ("%%.%df" % nd) % d
                return s.rstrip("0").rstrip(".") if "." in s else s
        return repr(v / 65536.0)

    def fmt_arg(self, ptype, value, ctx):
        if ptype in ("FIXED", "ANGLEFIXED"):
            return self.fmt_fixed(value)
        if ptype == "SOUND":
            name = self.sound_name(value)
            return f'"{name}"' if name else "0"
        if ptype in ("THING", "THINGMISSILE"):
            if value:
                name = self.thing_display_name(value)
                if not name.startswith("Thing"):
                    ctx.setdefault("comments", []).append(
                        f"thing {value} = {name}")
            return str(value)
        if ptype == "STATE":
            return self._state_ref(value, ctx)
        return str(value)

    def _state_ref(self, target, ctx):
        """Resolve a STATE pointer arg to a label (same thing) or raw index."""
        labels = ctx.get("labels", {})
        if target in labels:
            return labels[target]
        multi = ctx.get("multi", {})
        if target in multi and multi[target]:
            return multi[target][0]
        if target in self.modified and target not in self.pinned:
            # modified but floating and not label-resolvable here: this should
            # not happen if analysis was right; fall back with a warning
            self.warn(f"STATE arg -> {target}: floating state referenced by "
                      f"index; behavior may break (pin analysis gap)")
        return str(target)

    def render_state_line(self, idx, ctx, letters=None):
        st = self.eff[idx] if idx in self.eff else self.base_state(idx)
        parts = [self.sprite_name(st["sprite"])]
        parts.append(letters or self.frame_letter(st["frame"]))
        parts.append(str(st["tics"]))
        if st["bright"]:
            parts.append("Bright")
        if st["mbfflags"] & 1:
            parts.append("Fast")
        if st["action"]:
            sig = self.t.pointers.get(st["action"], {}).get("params", [])
            if sig:
                argstrs = [self.fmt_arg(pt, st["args"][i], ctx)
                           for i, pt in enumerate(sig)]
                # trim trailing zero-ish args for readability
                while argstrs and argstrs[-1] in ("0", "0.0"):
                    argstrs.pop()
                call = st["action"]
                if argstrs:
                    call += "(" + ", ".join(argstrs) + ")"
                parts.append(call)
            else:
                parts.append(st["action"])
                # non-parameterized pointer with stray misc values = Offset
                if st["args"][0] or st["args"][1]:
                    parts.append(f"Offset({st['args'][0]}, {st['args'][1]})")
        elif st["args"][0] or st["args"][1]:
            parts.append(f"Offset({st['args'][0]}, {st['args'][1]})")
        comment = ""
        if ctx.get("comments"):
            comment = "\t// " + "; ".join(ctx.pop("comments"))
        return "\t\t" + " ".join(parts) + comment

    # ------------------------------------------------------------------
    # Chain emission inside a thing/weapon block
    # ------------------------------------------------------------------

    def emit_states_block(self, owner, label_entries):
        """
        label_entries: list of (label, start_state).
        Returns (lines, used_raw_assignments) where lines is the states {}
        body, and used_raw_assignments is a list of (label, index) pairs for
        entries that point at pinned/unmodified states.
        """
        raw_assign = []
        chains = {}          # label -> [state indices]
        claimed = {}         # state -> label owning its rendering

        # Phase A: build chains
        for label, start in label_entries:
            if start == 0:
                raw_assign.append((label, 0))
                continue
            if start not in self.modified or start in self.pinned:
                raw_assign.append((label, start))
                continue
            if start in claimed:
                # label aliases another label's chain start or middle
                chains[label] = []
                continue
            seq = []
            cur = start
            while (cur in self.modified and cur not in self.pinned
                   and cur not in claimed and cur not in seq and cur != 0):
                seq.append(cur)
                nxt = self.eff[cur]["next"]
                if nxt == cur:
                    break
                cur = nxt
            for s in seq:
                claimed[s] = label
            chains[label] = seq

        # Phase B: compute needed synthetic labels (goto targets mid-chain
        # + STATE-arg targets inside this owner's chains)
        labels = {}          # state index -> primary label name
        multi = {}           # state index -> [additional stacked labels]
        for label, start in label_entries:
            if chains.get(label):
                if chains[label][0] in labels:
                    multi.setdefault(chains[label][0], []).append(label)
                else:
                    labels[chains[label][0]] = label

        synth_needed = set()
        all_owned = set(claimed)
        for label, seq in chains.items():
            if not seq:
                continue
            last = seq[-1]
            nxt = self.eff[last]["next"]
            if nxt != last and nxt in all_owned and nxt not in labels:
                synth_needed.add(nxt)
        for i in all_owned:
            st = self.eff[i]
            if st["action"]:
                sig = self.t.pointers.get(st["action"], {}).get("params", [])
                for slot, ptype in enumerate(sig):
                    if ptype == "STATE":
                        tgt = st["args"][slot]
                        if tgt in all_owned and tgt not in labels:
                            synth_needed.add(tgt)
        for s in sorted(synth_needed):
            labels[s] = f"st{s}"

        # entries that landed on states claimed by an earlier label:
        # stack the label at that state (rendered as an extra 'label:' line)
        for label, start in label_entries:
            if not chains.get(label) and start in claimed:
                multi.setdefault(start, [])
                if label not in multi[start]:
                    multi[start].append(label)

        # Phase C: render
        ctx = {"labels": labels, "multi": multi}
        lines = []
        label_order = [l for l, s in label_entries if chains.get(l)]
        for label in label_order:
            seq = chains[label]
            if not seq:
                continue
            lines.append(f"\t{label}:")
            for extra in multi.get(seq[0], []):
                if extra != label:
                    lines.append(f"\t{extra}:")
            i = 0
            while i < len(seq):
                idx = seq[i]
                if i > 0:
                    if idx in labels and labels[idx] != label:
                        lines.append(f"\t{labels[idx]}:")
                    for extra in multi.get(idx, []):
                        lines.append(f"\t{extra}:")
                # letter-run compression
                run = [idx]
                j = i + 1
                while j < len(seq):
                    a, b = self.eff[seq[j - 1]], self.eff[seq[j]]
                    if (self.eff[seq[j-1]]["next"] == seq[j]
                            and seq[j] not in labels
                            and seq[j] not in multi
                            and seq[j] not in self.state_arg_refs
                            and a["sprite"] == b["sprite"]
                            and a["tics"] == b["tics"]
                            and a["bright"] == b["bright"]
                            and a["mbfflags"] == b["mbfflags"]
                            and a["action"] == b["action"]
                            and a["args"] == b["args"]):
                        run.append(seq[j]); j += 1
                    else:
                        break
                letters = "".join(self.frame_letter(self.eff[s]["frame"]) for s in run)
                lines.append(self.render_state_line(idx, ctx, letters=letters))
                i = j

            # terminator
            last = seq[-1]
            st = self.eff[last]
            nxt = st["next"]
            if nxt == last:
                if st["tics"] < 0:
                    lines.append("\t\tstop")
                elif last == seq[0]:
                    lines.append("\t\tloop")   # single-state self-loop
                else:
                    lines.append("\t\twait")
            elif nxt == 0:
                lines.append("\t\tstop")
            elif nxt in labels:
                if nxt == seq[0] and labels[nxt] == label:
                    lines.append("\t\tloop")
                else:
                    lines.append(f"\t\tgoto {labels[nxt]}")
            elif nxt == 1:
                lines.append("\t\tgoto LightDone")
            else:
                note = ""
                if nxt not in self.modified and nxt < len(self.t.states):
                    note = f"\t// -> base state {nxt}"
                elif nxt in self.pinned:
                    note = f"\t// -> pinned state {nxt}"
                lines.append(f"\t\tgoto {nxt}{note}")
        return lines, raw_assign

    # ------------------------------------------------------------------
    # Block emitters
    # ------------------------------------------------------------------

    def emit_thing(self, num):
        d = self.ir.things[num]
        name = self.thing_display_name(num)
        base = self.base_thing(num)
        w = []
        w.append(f'thing {num} "{name}"' + (f"\t// {base.get('name')}" if base.get("name") else ""))
        w.append("{")

        body = []
        for old, new in getattr(self, "reskins", {}).get(num, []):
            body.append(f"\treskin {old} to {new}")
        for deh_key, prop, kind in THING_PROPS:
            if deh_key not in d:
                continue
            v = d[deh_key]
            body.append(self._prop_line(prop, kind, v, d, base, num))

        # flags
        body.extend(self._flag_lines(d, base, num))

        # entry states
        label_entries = [(label, d[f]) for f, label in THING_LABELS if f in d]
        for tgt in sorted(getattr(self, "pseudo_entries", {}).get(("thing", num), [])):
            label_entries.append((f"st{tgt}", tgt))
        state_lines, raw_assign = self.emit_states_block(("thing", num), label_entries)
        for label, target in raw_assign:
            if isinstance(target, tuple):
                body.append(f"\tstate {label} {target[1]}\t// alias of local label")
            elif target == 0:
                body.append(f"\tstate {label} 0\t// removed")
            else:
                note = self._pin_note(target)
                body.append(f"\tstate {label} {target}{note}")
        if state_lines:
            body.append("")
            body.append("\tstates")
            body.append("\t{")
            body.extend(state_lines)
            body.append("\t}")

        # unknown fields warning
        known = {k for k, _, _ in THING_PROPS} | {f for f, _ in THING_LABELS} | {"bits", "mbf21_bits", "id"}
        for k in d:
            if k not in known:
                body.append(f"\t// TODO: unhandled DEH field '{k}' = {d[k]}")
                self.warn(f"thing {num}: unhandled field {k}={d[k]}")

        w.extend(body)
        w.append("}")
        return w

    def _prop_line(self, prop, kind, v, d, base, num):
        if kind == "int":
            return f"\t{prop} {v}"
        if kind == "fixed16":
            if v % 65536 == 0:
                return f"\t{prop} {v // 65536}"
            return f"\t{prop} {self.fmt_fixed(v)}"
        if kind == "speed":
            flags = d.get("bits", base.get("flags", 0))
            if flags & 0x10000 and v % 65536 == 0 and abs(v) >= 65536:  # MISSILE
                return f"\t{prop} {v // 65536}"
            if flags & 0x10000 and v % 65536 != 0:
                return f"\t{prop} {self.fmt_fixed(v)}"
            return f"\t{prop} {v}"
        if kind == "sound":
            name = self.sound_name(v)
            if name is None:
                return f'\t{prop} ""\t// cleared (0) -- verify empty-string is accepted'
            return f'\t{prop} "{name}"'
        if kind == "thing":
            comment = ""
            if 1 <= v <= len(self.t.mobjinfo):
                comment = f"\t// {self.thing_display_name(v)}"
            return f"\t{prop} {v}{comment}"
        return f"\t{prop} {v}"

    def _flag_lines(self, d, base, num):
        lines = []
        doom_bits = d.get("bits")
        mbf21_bits = d.get("mbf21_bits")
        if doom_bits is not None:
            lines.append("")
            lines.append("\tclear flags")
            for bit_str, name in sorted(self.t.flags["doom"].items(), key=lambda kv: int(kv[0])):
                if doom_bits & int(bit_str):
                    lines.append(f"\t+{name}")
            # clear flags nukes BOTH sets; re-assert mbf21 flags
            eff_mbf21 = mbf21_bits if mbf21_bits is not None else MBF21_BASE_FLAGS.get(num, 0)
            for bit_str, name in sorted(self.t.flags["mbf21"].items(), key=lambda kv: int(kv[0])):
                if eff_mbf21 & int(bit_str):
                    lines.append(f"\t+{name}")
        elif mbf21_bits is not None:
            lines.append("")
            base_mbf = MBF21_BASE_FLAGS.get(num, 0)
            for bit_str, name in sorted(self.t.flags["mbf21"].items(), key=lambda kv: int(kv[0])):
                bit = int(bit_str)
                if (mbf21_bits & bit) and not (base_mbf & bit):
                    lines.append(f"\t+{name}")
                elif (base_mbf & bit) and not (mbf21_bits & bit):
                    lines.append(f"\t-{name}")
        return lines

    def base_thing_states(self, num):
        """All base states reachable from a base thing's default entry points."""
        base = self.base_thing(num)
        out = set()
        for field in ("spawnstate", "seestate", "painstate", "meleestate",
                      "missilestate", "deathstate", "xdeathstate", "raisestate"):
            cur = base.get(field, 0)
            steps = 0
            while cur and cur not in out and steps < 2000:
                out.add(cur)
                cur = self.base_state(cur)["next"]
                steps += 1
        return out

    def compute_reskins(self):
        """Map sprite renames onto per-thing reskin clauses for renames that
        would otherwise be lost on unmodified base states."""
        self.reskins = defaultdict(list)     # thing num -> [(old, new)]
        if not self.sprite_rename:
            return
        covered = set()
        for num in range(1, len(self.t.mobjinfo) + 1):
            owned = self.base_thing_states(num)
            needed = set()
            for s in owned:
                if s in self.modified:
                    continue           # re-rendered with the new name already
                spr = self.t.sprites[self.base_state(s)["sprite"]] \
                    if self.base_state(s)["sprite"] < len(self.t.sprites) else None
                if spr in self.sprite_rename:
                    needed.add(spr)
                    covered.add(s)
            for spr in sorted(needed):
                self.reskins[num].append((spr, self.sprite_rename[spr]))
        # warn about renamed sprites on base states owned by no thing
        for i in range(len(self.t.states)):
            if i in self.modified or i in covered:
                continue
            spr_idx = self.t.states[i]["sprite"]
            spr = self.t.sprites[spr_idx] if spr_idx < len(self.t.sprites) else None
            if spr in self.sprite_rename and i not in covered:
                # owned by weapons or unreferenced; only warn once per sprite
                pass
        weapon_like = {s for s in range(90)}   # weapon states live in 0..89
        for spr in self.sprite_rename:
            for i in weapon_like:
                b = self.t.states[i]
                if b["sprite"] < len(self.t.sprites) and \
                        self.t.sprites[b["sprite"]] == spr and i not in self.modified:
                    self.warn(f"sprite rename {spr}->{self.sprite_rename[spr]} "
                              f"touches base WEAPON state {i}; add a "
                              f"'weapon N reskin {spr} to {self.sprite_rename[spr]}' manually")
                    break

    def _pin_note(self, target):
        if target in self.pinned:
            return f"\t// pinned states below"
        if target not in self.modified:
            return f"\t// unmodified base state"
        return ""

    def emit_weapon(self, num):
        d = self.ir.weapons[num]
        name = self.ir.weapons_names.get(num, f"Weapon{num}")
        w = [f'weapon {num} "{name}"', "{"]
        for deh_key, prop, kind in WEAPON_PROPS:
            if deh_key in d:
                w.append(f"\t{prop} {d[deh_key]}")
        if "mbf21_bits" in d:
            for bit, fname in sorted(MBF21_WEAPON_FLAGS.items()):
                if d["mbf21_bits"] & bit:
                    w.append(f"\t+{fname}")
        label_entries = [(label, d[f]) for f, label in WEAPON_LABELS if f in d]
        for tgt in sorted(getattr(self, "pseudo_entries", {}).get(("weapon", num), [])):
            label_entries.append((f"st{tgt}", tgt))
        state_lines, raw_assign = self.emit_states_block(("weapon", num), label_entries)
        for label, target in raw_assign:
            if isinstance(target, tuple):
                w.append(f"\tstate {label} {target[1]}")
            else:
                w.append(f"\tstate {label} {target}{self._pin_note(target) if target else ''}")
        if state_lines:
            w.append("")
            w.append("\tstates")
            w.append("\t{")
            w.extend(state_lines)
            w.append("\t}")
        known = {k for k, _, _ in WEAPON_PROPS} | {f for f, _ in WEAPON_LABELS} | {"mbf21_bits"}
        for k in d:
            if k not in known:
                w.append(f"\t// TODO: unhandled DEH weapon field '{k}' = {d[k]}")
        w.append("}")
        return w

    def emit_pinned_blocks(self):
        """Group pinned states into maximal consecutive-index runs whose
        next-links are sequential, emit as `state fill N { ... }` blocks,
        single states as `state N { ... }`."""
        if not self.pinned:
            return []
        out = ["", "//" + "-" * 70,
               "// Pinned states: these must keep their original indices because",
               "// they are shared between things, referenced by index, or edits",
               "// to states of things the DEH never (re)declares.",
               "//" + "-" * 70]
        ctx = {"labels": {}}
        done = set()
        for s in sorted(self.pinned):
            if s in done:
                continue
            run = [s]
            cur = s
            while True:
                nxt = self.eff[cur]["next"]
                if nxt == cur + 1 and nxt in self.pinned and nxt not in done \
                        and nxt not in run:
                    run.append(nxt)
                    cur = nxt
                else:
                    break
            done.update(run)
            head = "state fill %d" % s if len(run) > 1 else "state %d" % s
            out.append("")
            owners = self.owners.get(s, set())
            if owners:
                out.append("// reached from: " + ", ".join(f"{k} {n}" for k, n in sorted(owners)))
            out.append(head)
            out.append("{")
            i = 0
            while i < len(run):
                idx = run[i]
                r = [idx]
                j = i + 1
                while j < len(run):
                    a, b = self.eff[run[j-1]], self.eff[run[j]]
                    if (a["next"] == run[j] and a["sprite"] == b["sprite"]
                            and a["tics"] == b["tics"] and a["bright"] == b["bright"]
                            and a["action"] == b["action"] and a["args"] == b["args"]
                            and a["mbfflags"] == b["mbfflags"]
                            and run[j] not in self.state_arg_refs):
                        r.append(run[j]); j += 1
                    else:
                        break
                letters = "".join(self.frame_letter(self.eff[x]["frame"]) for x in r)
                line = self.render_state_line(idx, ctx, letters=letters)
                out.append(line.replace("\t\t", "\t", 1))
                i = j
            last = run[-1]
            st = self.eff[last]
            nxt = st["next"]
            if nxt == last:
                out.append("\tstop" if st["tics"] < 0 else "\twait")
            elif nxt == 0:
                out.append("\tstop")
            else:
                note = "" if nxt in self.modified else "\t// -> base state"
                out.append(f"\tgoto {nxt}{note}")
            out.append("}")
        return out

    # ------------------------------------------------------------------
    # Top-level document
    # ------------------------------------------------------------------

    def emit(self):
        o = self.out
        o.append("#include <dsdhacked>")
        o.append("")
        o.append("/*")
        o.append("   Converted from DeHackEd by deh2decohack")
        o.append(f"   Source: Doom version = {self.ir.doom_version}, "
                 f"Patch format = {self.ir.patch_format}")
        o.append("   Target: DECOHack `dsdhacked` patch (MBF21 / dsda-doom)")
        o.append("*/")

        self.analyze()
        self.compute_reskins()

        # strings
        strings_out = dict(self.ir.strings)
        for old, new in self.ir.text_renames:
            if len(old) == 4 and len(new) == 4 and old.isupper():
                continue  # sprite rename, handled via resolution
            mnem = self.t.strings.get(old)
            if mnem:
                strings_out[mnem] = new
            else:
                self.warn(f"Text rename: no mnemonic found for source string "
                          f"{old[:40]!r}; add manually")
                o.append(f"// TODO: unmatched Text rename: {old[:60]!r} -> {new[:60]!r}")
        if strings_out:
            o.append("")
            o.append("strings")
            o.append("{")
            for k, v in strings_out.items():
                escaped = v.replace('"', '\\"')
                o.append(f'\t{k} "{escaped}"')
            o.append("}")

        # pars
        if self.ir.pars:
            o.append("")
            o.append("pars")
            o.append("{")
            for line in self.ir.pars:
                o.append(f"\t{line}")
            o.append("}")

        # misc
        if self.ir.misc:
            o.append("")
            o.append("misc")
            o.append("{")
            deh_to_deco = dict(MISC_PROPS)
            for k, v in self.ir.misc.items():
                prop = deh_to_deco.get(k)
                if prop:
                    o.append(f"\t{prop} {v}")
                else:
                    o.append(f"\t// TODO: unhandled Misc field '{k}' = {v}")
            o.append("}")

        # ammo
        for num in sorted(self.ir.ammo):
            d = self.ir.ammo[num]
            o.append("")
            o.append(f"ammo {num}")
            o.append("{")
            if "max_ammo" in d:
                o.append(f"\tmax {d['max_ammo']}")
            if "per_ammo" in d:
                o.append(f"\tpickup {d['per_ammo']}")
            o.append("}")

        # weapons
        for num in sorted(self.ir.weapons):
            o.append("")
            o.extend(self.emit_weapon(num))

        # things
        for num in sorted(self.ir.things):
            o.append("")
            o.extend(self.emit_thing(num))

        # reskin-only blocks for base things untouched by the DEH
        extra_reskins = [n for n in sorted(getattr(self, "reskins", {}))
                         if n not in self.ir.things and self.reskins[n]]
        if extra_reskins:
            o.append("")
            o.append("// Sprite renames carried by the original patch's Text/[SPRITES]")
            o.append("// blocks, applied to otherwise-untouched things via reskin:")
            for n in extra_reskins:
                clauses = " ".join(f"reskin {a} to {b}" for a, b in self.reskins[n])
                o.append(f'thing {n} {clauses}\t// {self.thing_display_name(n)}')

        # pinned state blocks
        o.extend(self.emit_pinned_blocks())

        # sound table edits ([SOUNDS] with numeric keys need no output --
        # names resolve inline; name->name renames were applied likewise)

        if self.warnings:
            o.append("")
            o.append("//" + "=" * 70)
            o.append("// Converter warnings:")
            for wmsg in self.warnings:
                o.append("//   " + wmsg)
        return "\n".join(o) + "\n"


def convert(deh_path, tables=None):
    from deh_parser import parse_deh
    ir = parse_deh(deh_path)
    t = tables or Tables()
    return Emitter(ir, t).emit()
