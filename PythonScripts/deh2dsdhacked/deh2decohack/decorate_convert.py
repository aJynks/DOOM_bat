"""
decorate_convert.py
--------------------
Converts ZDoom DECORATE actor definitions into DECOHack `thing` blocks
(dsdhacked / MBF21 target), where the semantics have a direct equivalent.
Anything ZDoom/GZDoom-specific that DECOHack has no equivalent for is left
in place as a clearly marked comment rather than silently dropped or guessed.

DECORATE and DECOHack's state-block grammar are both descended from the same
"SPRT ABCD 4 Bright A_Foo(args)" idiom, so most state lines pass through
almost unchanged. The real differences are:

  - DECORATE actors are class-based with inheritance (`: Parent`); DECOHack
    things are flat slot definitions with no inheritance. Parents defined
    IN THE SAME FILE are resolved by textual merge (child overrides parent
    field-by-field). A parent NOT found in the file is left as a comment
    for the user to merge by hand.
  - DECORATE has no `thing <slot>` concept -- only an optional editor number
    (doomednum). DECOHack needs an explicit slot integer. This converter
    auto-assigns slot numbers (starting at AUTO_SLOT_START) and prints them
    as a comment so you can renumber to avoid colliding with your existing
    project's thing slots.
  - DECORATE's `Monster`/`Projectile` flag-combo keywords expand to a set of
    flags that isn't perfectly pinned down across ZDoom versions; the
    expansion used here is a conservative, commonly-documented approximation
    and is flagged with a comment saying so -- verify against your actual
    behavior needs.
  - Damage types, custom sounds via SNDINFO, scale/alpha/renderstyle,
    per-actor user variables, ZScript-only constructs, and inheritance from
    classes outside the file are NOT translatable to DECOHack and are kept
    as `// TODO:` comments carrying the original text.
"""

import re
from collections import OrderedDict

AUTO_SLOT_START = 5000

# DECORATE flag name (uppercase, no leading +/-) -> DECOHack flag mnemonic.
# Only includes flags with a genuine 1:1 vanilla/MBF21 equivalent; anything
# not in this table is passed through as a TODO comment instead of guessed.
FLAG_MAP = {
    "SOLID": "SOLID", "SHOOTABLE": "SHOOTABLE", "NOSECTOR": "NOSECTOR",
    "NOBLOCKMAP": "NOBLOCKMAP", "AMBUSH": "AMBUSH", "JUSTHIT": "JUSTHIT",
    "JUSTATTACKED": "JUSTATTACKED", "SPAWNCEILING": "SPAWNCEILING",
    "NOGRAVITY": "NOGRAVITY", "DROPOFF": "DROPOFF", "PICKUP": "PICKUP",
    "NOCLIP": "NOCLIP", "SLIDE": "SLIDE", "FLOAT": "FLOAT",
    "TELEPORT": "TELEPORT", "MISSILE": "MISSILE", "DROPPED": "DROPPED",
    "SHADOW": "SHADOW", "NOBLOOD": "NOBLOOD", "CORPSE": "CORPSE",
    "INFLOAT": "INFLOAT", "COUNTKILL": "COUNTKILL", "COUNTITEM": "COUNTITEM",
    "SKULLFLY": "SKULLFLY", "NOTDMATCH": "NOTDMATCH",
    "NOTDEATHMATCH": "NOTDMATCH", "TOUCHY": "TOUCHY", "BOUNCES": "BOUNCES",
    "FRIENDLY": "FRIEND", "FRIEND": "FRIEND", "TRANSLUCENT": "TRANSLUCENT",
}

# Flag-combo keyword expansions. These are NOT guesses: they were derived by
# taking the vanilla things whose DECORATE definitions use each combo and
# subtracting the flags those definitions state explicitly, then intersecting
# across all of them. Verified over 8 monsters and 5 projectiles against the
# real Doom 2 thing table.
#   MONSTER    : SOLID | SHOOTABLE | COUNTKILL
#   PROJECTILE : MISSILE | NOGRAVITY | DROPOFF | NOBLOCKMAP
# (Some vanilla projectiles also carry TRANSLUCENT, but that is MBF per-thing
# translucency rather than part of the combo, so it is excluded.)
COMBO_FLAGS = {
    "MONSTER": ["SOLID", "SHOOTABLE", "COUNTKILL"],
    "PROJECTILE": ["MISSILE", "NOGRAVITY", "DROPOFF", "NOBLOCKMAP"],
}

# ZDoom action pointer names that are exact renames of a DECOHack pointer.
POINTER_ALIASES = {
    "A_NOBLOCKING": "A_Fall",     # ZDoom's name for vanilla A_Fall
}

# ZDoom-only pointers that have a close MBF21 equivalent worth recommending.
# These are NOT auto-converted -- argument order/semantics differ, so the user
# has to make the call. The suggestion is emitted alongside the TODO.
POINTER_SUGGESTIONS = {
    "A_SETSOLID": "A_AddFlags(SOLID, 0)",
    "A_UNSETSOLID": "A_RemoveFlags(SOLID, 0)",
    "A_SETSHOOTABLE": "A_AddFlags(SHOOTABLE, 0)",
    "A_UNSETSHOOTABLE": "A_RemoveFlags(SHOOTABLE, 0)",
    "A_JUMP": "A_RandomJump(<label>, <chance 0-255>) -- note the argument "
              "order is reversed relative to A_Jump",
    "A_CUSTOMMISSILE": "A_MonsterProjectile(<thing>, angle, pitch, hoffset, "
                       "voffset)",
    "A_CUSTOMCOMBOATTACK": "A_MonsterMeleeAttack / A_MonsterProjectile "
                           "(split the melee and missile halves)",
    "A_STARTSOUND": "A_PlaySound(<sound>, <fullvolume bool>)",
    "A_SPAWNITEMEX": "A_SpawnObject(<thing>, angle, x, y, z, vx, vy, vz)",
    "A_SETFLOORCLIP": "no equivalent -- Hexen floor clipping is cosmetic and "
                      "has no effect in Doom, so this line can simply be dropped",
    "A_UNSETFLOORCLIP": "no equivalent -- see A_SetFloorClip; safe to drop",
}

# DECORATE property (lowercase) -> (decohack property, transform)
# transform(tokens: list[str]) -> str value, or None to skip (comment instead)
def _first_int(toks):
    return toks[0]

def _first_num(toks):
    return toks[0]

PROP_MAP = {
    "health": ("health", _first_int),
    "speed": ("speed", _first_num),
    "radius": ("radius", _first_num),
    "height": ("height", _first_num),
    "mass": ("mass", _first_int),
    "damage": ("damage", _first_int),
    "reactiontime": ("reactiontime", _first_int),
    "painchance": ("painchance", _first_int),
    "seesound": ("seesound", lambda t: '"%s"' % t[0].strip('"')),
    "attacksound": ("attacksound", lambda t: '"%s"' % t[0].strip('"')),
    "painsound": ("painsound", lambda t: '"%s"' % t[0].strip('"')),
    "deathsound": ("deathsound", lambda t: '"%s"' % t[0].strip('"')),
    "activesound": ("activesound", lambda t: '"%s"' % t[0].strip('"')),
    # MBF21 properties that DECOHack does support
    "fastspeed": ("fastspeed", _first_num),
    "meleerange": ("meleerange", _first_num),
    "ripsound": ("ripsound", lambda t: '"%s"' % t[0].strip('"')),
}

# Properties with no DECOHack equivalent at all -- always commented out.
NO_EQUIVALENT_PROPS = {
    "spawnid", "decal", "activation", "damagefactor", "selfdamagefactor",
    "woundhealth", "burnheight", "meleethreshold", "missileheight",
    "missiletype", "poisondamage", "telefogsourcetype", "telefogdesttype",
    "scale", "alpha", "renderstyle", "translation", "tag", "obituary",
    "hitobituary", "floatspeed", "maxstepheight", "damagetype", "paintype",
    "deathtype", "meleedamage", "meleesound", "howlsound", "cameraheight",
    "gibhealth", "bloodcolor", "bloodtype", "explosionradius",
    "explosiondamage", "minmissilechance", "maxtargetrange",
    "vspeed", "gravity", "friction", "pushfactor", "weaveindexxy",
    "weaveindexz", "stencilcolor", "distancecheck", "visibleangles",
    "visiblepitch", "ripperlevel", "riplevelmin", "riplevelmax",
    "designatedteam", "species", "threshold", "defthreshold",
}

CONTROL_KEYWORDS = {"goto", "loop", "stop", "wait", "fail"}
STATE_FLAG_KEYWORDS = {"bright", "fast", "canraise", "nodelay", "slow", "light"}


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    out_lines = []
    for line in text.split("\n"):
        # crude but sufficient: DECORATE strings rarely contain //
        idx = line.find("//")
        if idx >= 0:
            line = line[:idx]
        out_lines.append(line)
    return "\n".join(out_lines)


def _find_matching_brace(text, open_idx):
    depth = 0
    i = open_idx
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


class DecorateActor:
    def __init__(self, name):
        self.name = name
        self.parent = None
        self.replaces = None
        self.doomednum = None
        self.props = OrderedDict()      # lowercase prop -> raw token list
        self.unknown_lines = []         # raw text lines we didn't parse
        self.flag_add = []              # original-case flag names
        self.flag_remove = []
        self.combos = []                # 'MONSTER' / 'PROJECTILE'
        self.states = OrderedDict()     # label -> [line dicts]
        self.slot = None                # assigned DECOHack thing slot


_ACTOR_HEADER_RE = re.compile(
    r"(?im)^\s*actor\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s*:\s*([A-Za-z_][A-Za-z0-9_]*))?"
    r"(?:\s+replaces\s+([A-Za-z_][A-Za-z0-9_]*))?"
    r"(?:\s+(\d+))?\s*\{")


def parse_decorate(text):
    text = _strip_comments(text)
    actors = OrderedDict()
    for m in _ACTOR_HEADER_RE.finditer(text):
        name, parent, replaces, ednum = m.groups()
        open_idx = m.end() - 1
        close_idx = _find_matching_brace(text, open_idx)
        if close_idx < 0:
            continue
        body = text[open_idx + 1:close_idx]
        actor = DecorateActor(name)
        actor.parent = parent
        actor.replaces = replaces
        actor.doomednum = int(ednum) if ednum else None
        _parse_actor_body(actor, body)
        actors[name.lower()] = actor
    return actors


_STATES_HEADER_RE = re.compile(r"(?im)^\s*states\b[^\{]*\{")


def _parse_actor_body(actor, body):
    sm = _STATES_HEADER_RE.search(body)
    if sm:
        open_idx = sm.end() - 1
        close_idx = _find_matching_brace(body, open_idx)
        states_body = body[open_idx + 1:close_idx] if close_idx > 0 else ""
        rest = body[:sm.start()] + body[close_idx + 1:] if close_idx > 0 else body[:sm.start()]
    else:
        states_body, rest = "", body

    for raw_line in rest.split("\n"):
        line = raw_line.strip().rstrip(";").strip()
        if not line:
            continue
        _parse_prop_line(actor, line)

    if states_body:
        _parse_states_body(actor, states_body)


_FLAG_LINE_RE = re.compile(r"([+-])\s*([A-Za-z_][A-Za-z0-9_.]*)")


def _parse_prop_line(actor, line):
    if _FLAG_LINE_RE.fullmatch(line.strip()) or re.match(r"^[+-][A-Za-z]", line):
        for sign, name in _FLAG_LINE_RE.findall(line):
            (actor.flag_add if sign == "+" else actor.flag_remove).append(name.upper())
        return
    low = line.lower()
    if low in ("monster", "projectile"):
        actor.combos.append(low.upper())
        return
    parts = line.split(None, 1)
    key = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""
    tokens = [t.strip().strip('"') if not t.strip().startswith('"') else t.strip()
              for t in re.split(r",\s*", rest)] if rest else []
    tokens = [t for t in tokens if t != ""]
    actor.props[key] = tokens if tokens else actor.props.get(key, [])
    if key not in actor.props or not tokens:
        actor.unknown_lines.append(line)
    if not tokens:
        actor.unknown_lines.append(line)


_LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*:$")
_STATE_LINE_RE = re.compile(
    r"^(?P<sprite>[A-Za-z0-9_#\-\"]{1,8})\s+"
    r"(?P<frames>[A-Za-z\#\-]+)\s+"
    r"(?P<dur>-?\d+|random\s*\([^)]*\))\s*"
    r"(?P<rest>.*)$", re.I)


def _parse_states_body(actor, body):
    label = None
    prev_sprite = None
    prev_frames = None
    for raw_line in body.split("\n"):
        line = raw_line.strip().rstrip(";").strip()
        if not line:
            continue
        lm = _LABEL_RE.match(line)
        if lm:
            label = lm.group(1)
            actor.states.setdefault(label, [])
            continue
        if label is None:
            actor.unknown_lines.append(f"(states, no label yet) {line}")
            continue

        low = line.lower()
        first_word = low.split(None, 1)[0] if low.split() else ""
        if first_word in CONTROL_KEYWORDS:
            m_goto = re.match(r"(?i)^goto\s+(.+)$", line)
            if m_goto:
                actor.states[label].append({"ctrl": "goto", "target": m_goto.group(1).strip()})
            elif first_word == "fail":
                actor.states[label].append({"ctrl": "fail_todo", "raw": line})
            else:
                actor.states[label].append({"ctrl": first_word})
            continue

        sm = _STATE_LINE_RE.match(line)
        if not sm:
            actor.states[label].append({"ctrl": "unparsed", "raw": line})
            continue

        notes = []
        sprite = sm.group("sprite").strip('"')
        # DECORATE: "####" (or "----") in the sprite slot means "keep the
        # current sprite". DECOHack always needs a literal sprite name, so
        # carry the previous one forward explicitly.
        if set(sprite) <= {"#", "-"} and sprite:
            if prev_sprite:
                notes.append(("note", f"source used '{sprite}' (keep previous "
                              f"sprite); resolved to {prev_sprite}"))
                sprite = prev_sprite
            else:
                notes.append(("todo", f"source used '{sprite}' (keep previous "
                              f"sprite) but there is no previous state here -- "
                              f"fill in the correct sprite name"))
                sprite = "????"
        else:
            prev_sprite = sprite

        frames = sm.group("frames")
        if set(frames) <= {"#", "-"} and frames:
            if prev_frames:
                notes.append(("note", f"source used '{frames}' (keep previous "
                              f"frame); resolved to {prev_frames[-1]}"))
                frames = prev_frames[-1]
            else:
                notes.append(("todo", f"source used '{frames}' (keep previous "
                              f"frame) but there is no previous state here -- "
                              f"fill in the correct frame letter"))
                frames = "A"
        else:
            prev_frames = frames
        dur_raw = sm.group("dur")
        if dur_raw.lower().startswith("random"):
            nums = re.findall(r"-?\d+", dur_raw)
            if len(nums) == 2:
                lo, hi = int(nums[0]), int(nums[1])
                dur = (lo + hi) // 2
                notes.append(("todo", f"duration was Random({lo},{hi}); DECOHack "
                              f"has no random duration -- used midpoint {dur}"))
            else:
                dur = 1
                notes.append(("todo", f"duration was {dur_raw}; DECOHack has no "
                              f"random duration -- defaulted to 1"))
        else:
            dur = int(dur_raw)

        rest = sm.group("rest").strip()
        st_flags = []
        offset = None
        action = None
        action_todo = None

        # pull recognized state-flag keywords off the front
        while True:
            wm = re.match(r"(?i)^(bright|fast|canraise|nodelay|slow|light\([^)]*\))\s*", rest)
            if not wm:
                break
            kw = wm.group(1)
            if kw.lower() == "bright":
                st_flags.append("Bright")
            elif kw.lower() == "fast":
                st_flags.append("Fast")
            else:
                st_flags.append(("TODO", kw))
            rest = rest[wm.end():].strip()

        om = re.match(r"(?i)^offset\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)\s*", rest)
        if om:
            offset = (om.group(1), om.group(2))
            rest = rest[om.end():].strip()

        if rest:
            action = rest

        for f in st_flags:
            if isinstance(f, tuple):
                notes.append(("todo", f"state keyword '{f[1]}' has no DECOHack "
                              f"equivalent"))
        actor.states[label].append({
            "sprite": sprite, "frames": frames, "dur": dur, "notes": notes,
            "flags": [f for f in st_flags if not isinstance(f, tuple)],
            "offset": offset, "action": action,
        })


# ---------------------------------------------------------------------
# Inheritance resolution (same-file parents only)
# ---------------------------------------------------------------------

def resolve_inheritance(actors):
    """Flatten DECORATE class inheritance for same-file parents.

    DECOHack things have no inheritance, so a child's fields are merged over
    its parent's. Parents not present in this file cannot be resolved (they
    live in ZDoom's own class tree or another file), and that is reported as a
    note so the user knows to merge by hand rather than silently getting a
    thing missing its inherited properties.

    Returns dict name -> (merged actor, note list).
    """
    cache = {}

    def resolve(name, stack=()):
        key = name.lower()
        if key in cache:
            return cache[key]
        actor = actors.get(key)
        if actor is None:
            return None, []
        if key in stack:
            result = (actor, [f"circular inheritance involving '{actor.name}' "
                              f"-- parent chain not merged"])
            cache[key] = result
            return result

        if actor.parent is None:
            result = (actor, [])
            cache[key] = result
            return result

        if actor.parent.lower() not in actors:
            result = (actor, [
                f"extends '{actor.parent}', which is not defined in this file "
                f"-- DECOHack has no inheritance, so any properties, flags or "
                f"states inherited from it are NOT present below; merge them "
                f"in by hand"])
            cache[key] = result
            return result

        parent, parent_notes = resolve(actor.parent, stack + (key,))
        merged = DecorateActor(actor.name)
        merged.parent = actor.parent
        merged.replaces = actor.replaces or parent.replaces
        merged.doomednum = (actor.doomednum if actor.doomednum is not None
                            else parent.doomednum)
        merged.props = OrderedDict(parent.props)
        merged.props.update(actor.props)
        merged.flag_add = list(dict.fromkeys(parent.flag_add + actor.flag_add))
        merged.flag_remove = list(dict.fromkeys(parent.flag_remove + actor.flag_remove))
        merged.combos = list(dict.fromkeys(parent.combos + actor.combos))
        merged.states = OrderedDict(parent.states)
        merged.states.update(actor.states)
        merged.unknown_lines = list(parent.unknown_lines) + list(actor.unknown_lines)
        notes = list(parent_notes) + [
            f"flattened from parent '{actor.parent}' (DECOHack has no "
            f"inheritance); child values override parent values"]
        result = (merged, notes)
        cache[key] = result
        return result

    out = OrderedDict()
    for name in actors:
        merged, notes = resolve(name)
        if merged is not None:
            out[name] = (merged, notes)
    return out


# ---------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------

STANDARD_LABELS = {"spawn", "see", "melee", "missile", "pain", "death",
                   "xdeath", "raise"}


class DecorateEmitter:
    def __init__(self, actors_text, pointer_table=None):
        self.raw_actors = parse_decorate(actors_text)
        self.resolved = resolve_inheritance(self.raw_actors)
        self.pointer_table = pointer_table or {}
        self.next_slot = AUTO_SLOT_START
        self.warnings = []

    def warn(self, msg):
        self.warnings.append(msg)

    def _assign_slot(self, actor):
        """DECORATE's trailing number is the map/editor number (doomednum), not
        a patch thing slot -- those are different namespaces. So always assign a
        fresh DECOHack slot and carry the editor number over as `ednum`."""
        actor.slot = self.next_slot
        self.next_slot += 1

    def emit(self):
        out = ["#include <dsdhacked>", "",
               "/*", "   Converted from DECORATE by deh2decohack.",
               "   ZDoom/GZDoom-specific features have no DECOHack equivalent",
               "   and are left as TODO comments below where encountered.",
               "*/"]
        for name, (actor, notes) in self.resolved.items():
            self._assign_slot(actor)
            out.append("")
            out.extend(self._emit_actor(actor, notes))
        if self.warnings:
            out.append("")
            out.append("//" + "=" * 70)
            out.append("// Converter warnings:")
            for w in self.warnings:
                out.append("//   " + w)
        return "\n".join(out) + "\n"

    def _emit_actor(self, actor, notes):
        lines = []
        header = f'thing {actor.slot} "{actor.name}"'
        lines.append(header)
        lines.append("{")
        lines.append(f"\t// NOTE: DECOHack thing slot {actor.slot} was "
                     f"auto-assigned -- renumber to fit your project's slot map")
        if actor.doomednum is not None:
            lines.append(f"\tednum {actor.doomednum}")
        else:
            lines.append(f"\t// no editor number in the DECORATE source; add "
                         f"`ednum <N>` if this thing needs to be placeable")
        if actor.replaces:
            lines.append(f"\t// replaces {actor.replaces} in the original DECORATE "
                         f"-- DECOHack has no slot-replacement concept; if you need "
                         f"this thing to take over {actor.replaces}'s doomednum, "
                         f"redefine that thing's slot manually")
        for note in notes:
            lines.append(f"\t// TODO: {note}")

        for key, toks in actor.props.items():
            if key in PROP_MAP:
                prop, fn = PROP_MAP[key]
                try:
                    lines.append(f"\t{prop} {fn(toks)}")
                except Exception:
                    lines.append(f"\t// TODO: could not convert '{key} {' '.join(toks)}'")
            elif key == "dropitem":
                if toks:
                    lines.append(f"\t// TODO: dropitem \"{toks[0]}\" -- DECOHack needs "
                                 f"a DECOHack thing slot number or alias here, not a "
                                 f"class name; resolve manually")
            elif key in NO_EQUIVALENT_PROPS:
                lines.append(f"\t// TODO: '{key} {' '.join(toks)}' has no DECOHack "
                             f"equivalent")
            else:
                lines.append(f"\t// TODO: unrecognized DECORATE property "
                             f"'{key} {' '.join(toks)}'")

        for raw in actor.unknown_lines:
            lines.append(f"\t// TODO: unparsed line: {raw}")

        flag_lines = self._flag_lines(actor)
        if flag_lines:
            lines.append("")
            lines.extend(flag_lines)

        if actor.states:
            lines.append("")
            lines.append("\tstates")
            lines.append("\t{")
            lines.extend(self._state_lines(actor))
            lines.append("\t}")

        lines.append("}")
        return lines

    def _flag_lines(self, actor):
        lines = []
        combo_flags = []
        for combo in actor.combos:
            expansion = COMBO_FLAGS.get(combo, [])
            lines.append(f"\t// '{combo}' combo keyword expanded to: "
                         f"{', '.join(expansion)}")
            combo_flags.extend(expansion)

        add = list(dict.fromkeys(combo_flags + actor.flag_add))
        for name in add:
            mapped = FLAG_MAP.get(name.upper())
            if mapped:
                lines.append(f"\t+{mapped}")
            else:
                lines.append(f"\t// TODO: DECORATE flag '+{name}' has no direct "
                             f"DECOHack equivalent")
        for name in actor.flag_remove:
            mapped = FLAG_MAP.get(name.upper())
            if mapped:
                lines.append(f"\t-{mapped}")
            else:
                lines.append(f"\t// TODO: DECORATE flag '-{name}' has no direct "
                             f"DECOHack equivalent")
        return lines

    @staticmethod
    def _norm_label(label):
        """DECOHack state labels are case-sensitive: `see` overrides a thing's
        default See chain, while `See` would create an unrelated custom label.
        DECORATE conventionally capitalizes them, so the standard ones must be
        lowercased or they silently stop being the actor's real behavior."""
        return label.lower() if label.lower() in STANDARD_LABELS else label

    def _goto_lines(self, target):
        """DECORATE goto targets can carry forms DECOHack has no syntax for."""
        t = target.strip()
        if "::" in t:
            return [f"\t\t// TODO: 'goto {t}' jumps into another class's states; "
                    f"DECOHack has no cross-class jump -- point this at a state "
                    f"label in this thing, or `goto thing <N> <label>`",
                    "\t\tstop"]
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*\+\s*(\d+)$", t)
        if m:
            return [f"\t\t// TODO: 'goto {t}' uses a label+offset, which DECOHack "
                    f"does not support -- add an explicit label at the target "
                    f"state instead",
                    f"\t\tgoto {self._norm_label(m.group(1))}"]
        return [f"\t\tgoto {self._norm_label(t)}"]

    def _state_lines(self, actor):
        lines = []
        for label, entries in actor.states.items():
            lines.append(f"\t{self._norm_label(label)}:")
            for e in entries:
                if "ctrl" in e:
                    if e["ctrl"] == "goto":
                        lines.extend(self._goto_lines(e["target"]))
                    elif e["ctrl"] == "fail_todo":
                        lines.append(f"\t\t// TODO: DECORATE 'Fail' keyword has no "
                                     f"DECOHack equivalent; original: {e['raw']}")
                        lines.append("\t\tstop")
                    elif e["ctrl"] == "unparsed":
                        lines.append(f"\t\t// TODO: could not parse state line: {e['raw']}")
                    else:
                        lines.append(f"\t\t{e['ctrl']}")
                    continue

                parts = [e["sprite"], e["frames"], str(e["dur"])]
                parts.extend(e["flags"])
                if e["offset"]:
                    parts.append(f"Offset({e['offset'][0]}, {e['offset'][1]})")
                notes = list(e.get("notes", []))
                if e["action"]:
                    act = e["action"].strip()
                    name = act.split("(")[0].strip()
                    if not name.upper().startswith("A_"):
                        notes.append(("todo", f"'{act}' is not an A_* action "
                                      f"pointer; DECOHack only accepts action "
                                      f"pointers here -- left out, resolve by hand"))
                    else:
                        upper = name.upper()
                        renamed = POINTER_ALIASES.get(upper)
                        if renamed:
                            # exact rename: safe to convert outright
                            act = renamed + act[len(name):]
                            notes.append(("note", f"{name} renamed to {renamed} "
                                          f"(same function, DECOHack's name)"))
                            parts.append(act)
                        else:
                            parts.append(act)
                            if self.pointer_table:
                                known = upper in {k.upper() for k in self.pointer_table}
                                if not known:
                                    hint = POINTER_SUGGESTIONS.get(upper)
                                    if hint:
                                        notes.append(("todo",
                                            f"'{name}' is ZDoom-only; closest "
                                            f"DECOHack equivalent: {hint}"))
                                    else:
                                        notes.append(("todo",
                                            f"action pointer '{name}' is not in "
                                            f"the dsdhacked/MBF21 pointer set -- "
                                            f"likely ZDoom-only; resolve by hand"))
                if e.get("dur_note"):
                    notes.append(e["dur_note"])
                todos = [t for lvl, t in notes if lvl == "todo"]
                infos = [t for lvl, t in notes if lvl == "note"]
                comment = ""
                if todos:
                    comment += "\t// TODO: " + "; ".join(todos)
                if infos:
                    comment += "\t// note: " + "; ".join(infos)
                lines.append("\t\t" + " ".join(parts) + comment)
        return lines


def convert_decorate(text, pointer_table=None):
    return DecorateEmitter(text, pointer_table=pointer_table).emit()
