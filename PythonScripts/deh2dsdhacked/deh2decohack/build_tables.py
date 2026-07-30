"""
build_tables.py (v2)
--------------------
Builds base data tables for the DEH -> DECOHack (dsdhacked) converter.

Sources of truth:
  - DECOHack's own base patch tables (DoomTools Java sources) for the
    state table 0-1088 (incl. pointer assignments) and sprite names.
    This guarantees our "what differs from base" logic matches what
    DECOHack itself compiles against.
  - dsda-doom sources for mobjinfo defaults and the sound name order.
  - DoomTools pointer enums for action pointer signatures/param types.
  - d_englsh.h for default English strings -> BEX mnemonic mapping.

Outputs JSON files into ./data/ .
Everything is landmark-verified at the end; build fails loudly on drift.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(HERE, "src_ref")
DATA = os.path.join(HERE, "data")

def read(name, enc="utf-8"):
    with open(os.path.join(SRC, name), "r", encoding=enc, errors="replace") as f:
        return f.read()

# ---------------------------------------------------------------- pointers
# doom19 entries: NAME (int, [true,] "Mnemonic", usage(...
# mbf/mbf21 entries: NAME (false, "Mnemonic", params(...), usage(...
_PTR_ENTRY_RE = re.compile(
    r"^\t([A-Z0-9_]+)\s*\(\s*"
    r"(?:(\d+)\s*,\s*)?"          # optional doom19 slot number
    r"(?:(true|false)\s*,\s*)?"    # optional weapon/flag boolean
    r"\"(\w+)\"\s*"
    r"(?:,\s*params\(([^)]*)\))?", re.M)

def parse_pointers():
    out, enum_to_name = {}, {}
    for fname, tag in (("DEHActionPointerDoom19.java", "doom19"),
                       ("DEHActionPointerMBF.java", "mbf"),
                       ("DEHActionPointerMBF21.java", "mbf21")):
        text = read(fname)
        for m in _PTR_ENTRY_RE.finditer(text):
            enum_name, slot, weapon, mnem, params = m.groups()
            if mnem == "NULL":
                enum_to_name[enum_name] = None
                continue
            plist = [p.strip() for p in params.split(",") if p.strip()] if params else []
            out["A_" + mnem] = {"params": plist, "weapon": weapon == "true", "source": tag}
            enum_to_name[enum_name] = "A_" + mnem
    return out, enum_to_name

# ---------------------------------------------------------------- states
_STATE_RE = re.compile(
    r"State\.create\(DEHState\.create\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*,\s*"
    r"([A-Za-z0-9_]+|null)\s*\)")

def _split_state_args(argstr):
    # split top-level commas (there can be `new int[]{...}` containing commas)
    parts, depth, cur = [], 0, ""
    for ch in argstr:
        if ch in "{([": depth += 1
        elif ch in "})]": depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip(): parts.append(cur.strip())
    return parts

def parse_states(enum_to_name):
    table = []
    for fname in ("ConstantsBoom.java", "ConstantsMBF.java", "ConstantsExtended.java"):
        text = read(fname)
        # isolate the state array region to avoid matching thing definitions
        for m in _STATE_RE.finditer(text):
            args = _split_state_args(m.group(1))
            spr, frm, bright, nxt, tics = (args + ["0"]*5)[:5]
            misc1 = misc2 = 0; mbfflags = 0
            def _flagval(s):
                s = s.strip()
                if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                    return int(s)
                return 1 if "SKILL5FAST" in s else 0
            if len(args) == 6:
                mbfflags = _flagval(args[5])
            elif len(args) >= 7:
                misc1, misc2 = int(args[5]), int(args[6])
                if len(args) >= 9: mbfflags = _flagval(args[8])
            ptr = m.group(2)
            table.append({
                "sprite": int(spr), "frame": int(frm),
                "bright": bright == "true",
                "next": int(nxt), "tics": int(tics),
                "misc1": misc1, "misc2": misc2, "mbfflags": mbfflags,
                "action": enum_to_name.get(ptr) if ptr != "null" else None,
            })
    return table

# ---------------------------------------------------------------- sprites
def parse_sprites():
    text = read("PatchDoom19.java")
    # contiguous run of quoted 4-char uppercase names starting at "TROO"
    all_quoted = re.findall(r'"([A-Z0-9]{4})"', text)
    i = all_quoted.index("TROO")
    base = []
    for name in all_quoted[i:]:
        base.append(name)
        if name == "TLP2":  # last vanilla doom2 sprite (index 137)
            break
    boom = re.findall(r'"([A-Z0-9]{4})"', read("PatchBoom.java"))
    boom = [s for s in boom if s == "TNT1"]
    mbf_text = read("PatchMBF.java")
    mbf = []
    for name in re.findall(r'"([A-Z0-9]{4})"', mbf_text):
        if name in ("DOGS", "PLS1", "PLS2", "BON3", "BON4"):
            mbf.append(name)
    # DEHEXTRA: BLD2 (colored blood) at 144, then SP00-SP99 at 145-244
    ext = ["BLD2"] + ["SP%02d" % i for i in range(100)]
    return base + boom + mbf + ext

# ---------------------------------------------------------------- sounds
def parse_sounds():
    text = read("sounds.c")
    start = text.index("doom_S_sfx")
    body = text[start:text.index("\n};", start)]
    names = re.findall(r'\{\s*"([a-z0-9]*)"', body)
    # dsda stores full lump names ("dspistol"); strip the ds prefix, keep [0]=""
    out = []
    for i, n in enumerate(names):
        if i == 0: out.append("")           # sfx_None
        elif n.startswith("ds"): out.append(n[2:])
        else: out.append(n)
    # truncate at deh index 114 (secret); the fre range is synthesized by rule
    return out[:115]

# ---------------------------------------------------------------- mobjinfo
_MOBJ_HDR_RE = re.compile(r"\{\s*//\s*(MT_[A-Z0-9_]+)")

# Field order verified against dsda-doom's info.h mobjinfo_t. The
# doom_mobjinfo[] initializers supply values up to droppeditem and rely on C
# zero-initialization for the heretic/mbf21 tail, so we only read this far.
_MOBJ_FIELD_ORDER = [
    "doomednum", "spawnstate", "spawnhealth", "seestate", "seesound",
    "reactiontime", "attacksound", "painstate", "painchance", "painsound",
    "meleestate", "missilestate", "deathstate", "xdeathstate", "deathsound",
    "speed", "radius", "height", "mass", "damage", "activesound", "flags",
    "raisestate", "droppeditem",
]


def _split_top_level(text):
    """Split on commas that are not inside brackets."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _strip_c_comments(text):
    """Remove block comments and line comments.

    This must happen BEFORE reading values positionally: dsda's info.c has
    entries like

        MF_SOLID|MF_SHOOTABLE|MF_COUNTKILL, // killough |MF_TRANSLUCENT,   // flags

    where a disabled flag sits inside a comment. Anchoring on the trailing
    "// fieldname" markers instead of position reads the commented-out text as
    the real value, which silently corrupts the flag word.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in text.split("\n"))


def parse_mobjinfo(flag_bits):
    text = read("info.c")
    start = text.index("doom_mobjinfo[")
    body = text[start:text.index("\n};", start)]

    s_index = build_s_index()
    sfx_index = build_sfx_index()

    # Grab entry names from the "{ // MT_FOO" headers before comments are
    # stripped, then parse each entry body positionally.
    marks = [(m.start(), m.group(1)) for m in _MOBJ_HDR_RE.finditer(body)]
    mobjs = []
    for i, (pos, name) in enumerate(marks):
        chunk_end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        chunk = body[pos:chunk_end]
        chunk = chunk[chunk.index("{") + 1:]
        brace = chunk.rfind("}")
        if brace >= 0:
            chunk = chunk[:brace]
        vals = _split_top_level(_strip_c_comments(chunk))
        entry = {"name": name}
        for field, val in zip(_MOBJ_FIELD_ORDER, vals):
            entry[field] = _mobj_value(field, val, s_index, sfx_index, flag_bits)
        mobjs.append(entry)
    return mobjs


def _mobj_value(field, val, s_index, sfx_index, flag_bits):
    val = val.strip()
    if field == "flags":
        total = 0
        for part in val.split("|"):
            part = part.strip()
            if part and part != "0":
                total |= flag_bits.get(part, 0)
        return total
    if val.startswith("S_"):
        return s_index.get(val, 0)
    if val.startswith("sfx_"):
        return sfx_index.get(val, 0)
    m = re.match(r"^(-?\d+)\s*\*\s*FRACUNIT$", val)
    if m:
        return int(m.group(1)) * 65536
    if val == "FRACUNIT":
        return 65536
    if re.match(r"^-?\d+$", val):
        return int(val)
    return val


def build_s_index():
    text = read("info.h")
    start = text.index("S_NULL"); end = text.index("DOOM_NUMSTATES", start)
    body = re.sub(r"/\*.*?\*/", "", text[start:end], flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    names, idx = {}, 0
    for token in body.split(","):
        token = token.strip()
        if not token: continue
        m = re.match(r"^([A-Za-z0-9_]+)\s*=\s*([A-Za-z0-9_]+)\s*\+\s*(\d+)$", token)
        if m:  # e.g. S_OLDBFG42 = S_OLDBFG1+41  (alias, consumes no slot)
            base, off = m.group(2), int(m.group(3))
            if base in names: names[m.group(1)] = names[base] + off
            continue
        m = re.match(r"^([A-Za-z0-9_]+)(?:\s*=\s*0)?$", token)
        if m:
            names[m.group(1)] = idx; idx += 1
    return names

def build_sfx_index():
    text = read("sounds.h")
    start = text.index("sfx_None"); end = text.index("DOOM_NUMSFX", start)
    body = re.sub(r"/\*.*?\*/", "", text[start:end], flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    out, idx = {}, 0
    for token in body.split(","):
        token = token.strip()
        if not token: continue
        m = re.match(r"^([A-Za-z0-9_]+)(?:\s*=\s*0)?$", token)
        if m: out[m.group(1)] = idx; idx += 1
    return out

# ---------------------------------------------------------------- flags
def doom_flag_values():
    names = ["MF_SPECIAL","MF_SOLID","MF_SHOOTABLE","MF_NOSECTOR","MF_NOBLOCKMAP",
             "MF_AMBUSH","MF_JUSTHIT","MF_JUSTATTACKED","MF_SPAWNCEILING",
             "MF_NOGRAVITY","MF_DROPOFF","MF_PICKUP","MF_NOCLIP","MF_SLIDE",
             "MF_FLOAT","MF_TELEPORT","MF_MISSILE","MF_DROPPED","MF_SHADOW",
             "MF_NOBLOOD","MF_CORPSE","MF_INFLOAT","MF_COUNTKILL","MF_COUNTITEM",
             "MF_SKULLFLY","MF_NOTDMATCH","MF_TRANSLATION1","MF_TRANSLATION2",
             "MF_TOUCHY","MF_BOUNCES","MF_FRIEND","MF_TRANSLUCENT"]
    return {n: (1 << i) for i, n in enumerate(names)}

MBF21_THING_FLAGS = ["LOGRAV","SHORTMRANGE","DMGIGNORED","NORADIUSDMG",
    "FORCERADIUSDMG","HIGHERMPROB","RANGEHALF","NOTHRESHOLD","LONGMELEE",
    "BOSS","MAP07BOSS1","MAP07BOSS2","E1M8BOSS","E2M8BOSS","E3M8BOSS",
    "E4M6BOSS","E4M8BOSS","RIP","FULLVOLSOUNDS"]

# ---------------------------------------------------------------- weaponinfo
# Field order verified against dsda-doom's d_items.h weaponinfo_t:
#   ammo, upstate, downstate, readystate, atkstate, holdatkstate,
#   flashstate, ammopershot, intflags, flags
_WEAPON_FIELDS = ["ammo", "upstate", "downstate", "readystate", "atkstate",
                  "holdatkstate", "flashstate", "ammopershot", "intflags",
                  "flags"]
_WEAPON_HDR_RE = re.compile(r"\{\s*//\s*([a-z0-9 ]+)\s*\n(.*?)\n\s*\}", re.S)

def parse_weaponinfo():
    text = read("d_items.c")
    start = text.index("doom_weaponinfo[")
    body = text[start:text.index("\n};", start)]
    s_index = build_s_index()
    weapons = []
    for m in _WEAPON_HDR_RE.finditer(body):
        name, chunk = m.group(1).strip(), m.group(2)
        vals = []
        for line in chunk.split("\n"):
            line = re.sub(r"//.*$", "", line).strip().rstrip(",").strip()
            if line:
                vals.append(line)
        entry = {"name": name}
        for field, val in zip(_WEAPON_FIELDS, vals):
            if val.startswith("S_"):
                entry[field] = s_index.get(val, 0)
            elif re.match(r"^-?\d+$", val):
                entry[field] = int(val)
            else:
                entry[field] = val
        weapons.append(entry)
    return weapons

# ---------------------------------------------------------------- aliases
_DEFINE_RE = re.compile(r"^#define\s+([A-Z][A-Z0-9_]*)\s+(\d+)\s*$", re.M)

def _parse_defines(paths, prefix):
    """Parse DECOHack's own constant include files into slot -> mnemonic.
    These are the built-in names that `#include <dsdhacked>` provides, so
    they are the authoritative aliases to print in generated output."""
    out, dupes = {}, []
    for p in paths:
        full = os.path.join(SRC, "dhconst", p)
        if not os.path.isfile(full):
            continue
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        for m in _DEFINE_RE.finditer(text):
            name, slot = m.group(1), int(m.group(2))
            if not name.startswith(prefix):
                continue          # skip include-guard defines
            if name.endswith("_FREE_START"):
                continue
            if slot in out and out[slot] != name:
                dupes.append((slot, out[slot], name))
                continue          # keep the first (lowest tier) name
            out[slot] = name
    return out, dupes

def parse_aliases():
    things, tdupes = _parse_defines(
        ["doom19_things.dh", "boom_things.dh", "mbf_things.dh",
         "extended_things.dh"], "MT_")
    weapons, wdupes = _parse_defines(["doom19_weapons.dh"], "WP_")
    return things, weapons, tdupes + wdupes

# ---------------------------------------------------------------- strings
def parse_default_strings():
    text = read("d_englsh.h", enc="latin-1")
    out = {}
    for m in re.finditer(r'#define\s+([A-Z0-9_]+)\s+"((?:[^"\\]|\\.)*)"', text):
        mnem, raw = m.groups()
        try: s = raw.encode("utf-8").decode("unicode_escape")
        except Exception: s = raw
        out.setdefault(s, mnem)
    return out

# ---------------------------------------------------------------- main
def main():
    os.makedirs(DATA, exist_ok=True)
    pointers, enum_to_name = parse_pointers()
    states  = parse_states(enum_to_name)
    sprites = parse_sprites()
    sounds  = parse_sounds()
    flag_bits = doom_flag_values()
    mobjs   = parse_mobjinfo(flag_bits)
    strings = parse_default_strings()
    alias_things, alias_weapons, alias_dupes = parse_aliases()
    weaponinfo = parse_weaponinfo()

    # ------------- landmark verification (fail loudly on drift) -------------
    errs = []
    if len(states) != 1089: errs.append(f"state table len {len(states)} != 1089")
    s667 = states[667]
    if not (s667["sprite"] == sprites.index("APLS") and s667["bright"]
            and s667["tics"] == 5 and s667["next"] == 668):
        errs.append(f"state 667 landmark failed: {s667}")
    if sprites[138] != "TNT1" or sprites[144] != "BLD2" \
            or sprites[145] != "SP00" or sprites[244] != "SP99":
        errs.append(f"sprite landmarks failed: 138={sprites[138]} 144={sprites[144]} 145={sprites[145]}")
    if sounds[1] != "pistol" or sounds[109] != "dgsit" or sounds[114] != "secret":
        errs.append(f"sound landmarks failed: {sounds[1]},{sounds[109]},{sounds[114]}")
    if mobjs[14]["name"] != "MT_HEAD" or mobjs[0]["name"] != "MT_PLAYER":
        errs.append(f"mobj landmarks failed: [0]={mobjs[0]['name']} [14]={mobjs[14]['name']}")
    if mobjs[14].get("doomednum") != 3005:
        errs.append(f"MT_HEAD doomednum {mobjs[14].get('doomednum')} != 3005")
    F = flag_bits
    MONSTER_BITS = F["MF_SOLID"] | F["MF_SHOOTABLE"] | F["MF_COUNTKILL"]
    caco_want = MONSTER_BITS | F["MF_FLOAT"] | F["MF_NOGRAVITY"]
    if mobjs[14].get("flags") != caco_want:
        errs.append(f"MT_HEAD flags {mobjs[14].get('flags')} != {caco_want}")
    if mobjs[14].get("spawnhealth") != 400 or mobjs[14].get("mass") != 400:
        errs.append(f"MT_HEAD health/mass wrong: {mobjs[14].get('spawnhealth')}/"
                    f"{mobjs[14].get('mass')}")
    # MT_TROOP: regression guard for the commented-out-flag parse bug
    if mobjs[11].get("flags") != MONSTER_BITS:
        errs.append(f"MT_TROOP flags {mobjs[11].get('flags')} != {MONSTER_BITS} "
                    f"(comment-stripping regression?)")
    if mobjs[11].get("radius") != 20 * 65536:
        errs.append(f"MT_TROOP radius {mobjs[11].get('radius')} != {20*65536}")
    if pointers.get("A_RandomJump", {}).get("params") != ["STATE", "UINT"]:
        errs.append(f"A_RandomJump signature: {pointers.get('A_RandomJump')}")
    if not pointers.get("A_WeaponMeleeAttack", {}).get("weapon", False):
        # weapon-flag semantics check -- warn only, don't fail
        print("NOTE: A_WeaponMeleeAttack weapon flag is False; first enum bool "
              "may not mean 'weapon'", file=sys.stderr)
    for slot, want in ((1, "MT_PLAYER"), (15, "MT_HEAD"), (109, "MT_MISC58"),
                       (145, "MT_MUSICSOURCE"), (250, "MT_EXTRA99")):
        if alias_things.get(slot) != want:
            errs.append(f"thing alias {slot} = {alias_things.get(slot)} != {want}")
    if len(weaponinfo) < 9:
        errs.append(f"weaponinfo parsed {len(weaponinfo)} entries, expected >= 9")
    else:
        if weaponinfo[0]["name"] != "fist":
            errs.append(f"weaponinfo[0] = {weaponinfo[0]['name']} != fist")
        if weaponinfo[8]["name"] not in ("super shotgun", "supershotgun"):
            errs.append(f"weaponinfo[8] = {weaponinfo[8]['name']} != super shotgun")
    for slot, want in ((0, "WP_FIST"), (1, "WP_PISTOL"), (8, "WP_SUPERSHOTGUN")):
        if alias_weapons.get(slot) != want:
            errs.append(f"weapon alias {slot} = {alias_weapons.get(slot)} != {want}")

    # Cross-check DECOHack's aliases against dsda-doom's own enum names for
    # the overlapping range. A mismatch means one of the two upstreams moved
    # and the tables need review -- report, don't silently prefer either.
    mismatch = []
    for i, m in enumerate(mobjs):
        slot = i + 1
        dsda_name = m.get("name")
        deco_name = alias_things.get(slot)
        if deco_name and dsda_name and deco_name != dsda_name:
            mismatch.append(f"slot {slot}: DECOHack={deco_name} dsda={dsda_name}")
    if mismatch:
        print(f"NOTE: {len(mismatch)} thing-name mismatch(es) between DECOHack "
              f"and dsda-doom (DECOHack wins, as it defines the emitted names):",
              file=sys.stderr)
        for s in mismatch[:10]:
            print("   ", s, file=sys.stderr)
    if alias_dupes:
        print(f"NOTE: {len(alias_dupes)} duplicate alias slot(s) upstream "
              f"(first/lowest-tier name kept):", file=sys.stderr)
        for slot, kept, skipped in alias_dupes[:10]:
            print(f"    slot {slot}: kept {kept}, skipped {skipped}", file=sys.stderr)

    if errs:
        for e in errs: print("LANDMARK FAIL:", e, file=sys.stderr)
        sys.exit(1)

    json.dump(states,  open(os.path.join(DATA, "states.json"), "w"))
    json.dump(sprites, open(os.path.join(DATA, "sprites.json"), "w"))
    json.dump(sounds,  open(os.path.join(DATA, "sounds.json"), "w"))
    json.dump(mobjs,   open(os.path.join(DATA, "mobjinfo.json"), "w"))
    json.dump(pointers, open(os.path.join(DATA, "pointers.json"), "w"), indent=1)
    json.dump(strings, open(os.path.join(DATA, "strings.json"), "w"))
    json.dump(weaponinfo, open(os.path.join(DATA, "weaponinfo.json"), "w"))
    json.dump({"things": {str(k): v for k, v in sorted(alias_things.items())},
               "weapons": {str(k): v for k, v in sorted(alias_weapons.items())}},
              open(os.path.join(DATA, "aliases.json"), "w"), indent=1)
    json.dump({"doom": {str(v): k[3:] for k, v in flag_bits.items()},
               "mbf21": {str(1 << i): n for i, n in enumerate(MBF21_THING_FLAGS)}},
              open(os.path.join(DATA, "flags.json"), "w"), indent=1)

    print(f"OK: {len(states)} states, {len(sprites)} sprites, {len(sounds)} sounds,")
    print(f"    {len(mobjs)} things, {len(pointers)} pointers, {len(strings)} strings,")
    print(f"    {len(alias_things)} thing aliases, {len(alias_weapons)} weapon aliases,")
    print(f"    {len(weaponinfo)} base weapons")

if __name__ == "__main__":
    main()
