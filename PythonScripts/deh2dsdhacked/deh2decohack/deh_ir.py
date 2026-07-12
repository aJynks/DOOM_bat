"""
deh_parser.py
-------------
Stage 1 of the DEH -> DECOHack converter.

Parses an arbitrary DeHackEd (.deh/.bex) file into a plain-data
intermediate representation (IR). This module knows NOTHING about
DECOHack syntax or output formatting -- it just faithfully captures
what's in the DEH file so later stages can reason about it.

Supports:
    - Classic numbered blocks: Thing, Frame, Weapon, Ammo, Sound, Misc, Cheat
    - Old-style "Pointer N (Frame M)" + "Codep Frame = X" blocks
    - Old-style "Text <len1> <len2>" raw sprite/string-rename blocks
    - BEX bracket sections: [CODEPTR], [STRINGS], [SPRITES], [SOUNDS],
      [PARS], [HELPER], [MUSIC], and unknown sections (captured raw so
      nothing is silently dropped)
    - MBF21 "Args1".."Args8" and legacy "Unknown 1"/"Unknown 2" fields,
      normalized into a single 8-slot args list (they're the same
      underlying state_t fields; MBF21 just added slots 3-8)

Field names are normalized to snake_case keys, values are parsed to
int where the DEH format specifies a numeric field, else kept as str.
"""

import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Field name normalization
# ---------------------------------------------------------------------------

def _normalize_key(raw_key: str) -> str:
    """'Initial frame' -> 'initial_frame', 'MBF21 Bits' -> 'mbf21_bits'"""
    key = raw_key.strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return key


# Fields whose values are always integers in vanilla/BEX/MBF21 dehacked.
# Anything not in here (e.g. Deselect frame? no - that IS int) is treated
# as int if it looks like an int, else left as a string.
_ALWAYS_STRING_FIELDS = {
    # thing/weapon sound fields are numeric SOUND indices, not strings,
    # so nothing here for those. Reserved for future known string fields.
}


def _coerce_value(value: str):
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class DehIR:
    doom_version: Optional[int] = None
    patch_format: Optional[int] = None

    # numeric-block tables: index -> {field_name: value}
    things: Dict[int, dict] = field(default_factory=dict)
    things_names: Dict[int, str] = field(default_factory=dict)      # parenthetical name, if any
    frames: Dict[int, dict] = field(default_factory=dict)
    weapons: Dict[int, dict] = field(default_factory=dict)
    weapons_names: Dict[int, str] = field(default_factory=dict)
    ammo: Dict[int, dict] = field(default_factory=dict)
    sounds: Dict[int, dict] = field(default_factory=dict)
    misc: dict = field(default_factory=dict)
    cheat: dict = field(default_factory=dict)

    # old-style Pointer blocks: frame_num -> {"codep_frame": int, ...}
    # (rare in modern output but still legal DEH)
    pointer_blocks: Dict[int, dict] = field(default_factory=dict)

    # old-style "Text <len1> <len2>" raw rename pairs (sprite/string swap hack)
    text_renames: List[Tuple[str, str]] = field(default_factory=list)

    # BEX bracket sections
    codeptr: Dict[int, str] = field(default_factory=dict)          # frame_num -> bare pointer name
    strings: Dict[str, str] = field(default_factory=dict)          # mnemonic -> replacement text
    sprites: Dict[Union[int, str], str] = field(default_factory=dict)  # index-or-oldname -> newname
    sound_names: Dict[Union[int, str], str] = field(default_factory=dict)
    music_names: Dict[Union[int, str], str] = field(default_factory=dict)
    pars: List[str] = field(default_factory=list)                  # raw lines, rarely needed
    helper: List[str] = field(default_factory=list)
    unknown_sections: Dict[str, List[str]] = field(default_factory=dict)

    # Merge legacy Args1/2 (aka Unknown1/2) with MBF21 Args3-8 into
    # frames[n]['args'] = [a1..a8] (None where unset) during parsing.


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_BLOCK_HEADER_RE = re.compile(
    r"^(Thing|Frame|Weapon|Ammo|Sound|Pointer)\s+(\d+)(?:\s*\((.*)\))?\s*$"
)
_SINGLETON_HEADER_RE = re.compile(r"^(Misc|Cheat)\s*$")
_TEXT_HEADER_RE = re.compile(r"^Text\s+(\d+)\s+(\d+)\s*$")
_BRACKET_HEADER_RE = re.compile(r"^\[([A-Za-z0-9_]+)\]\s*$")
_FIELD_RE = re.compile(r"^([^=]+?)\s*=\s*(.*)$")
_HEADER_FIELD_RE = re.compile(r"^(Doom version|Patch format)\s*=\s*(\d+)\s*$", re.IGNORECASE)


def _apply_args_field(target: dict, norm_key: str, int_val: int):
    """Route Args1..Args8 / Unknown 1..Unknown 2 into a unified args[0..7] list."""
    args = target.setdefault("args", [None] * 8)
    m = re.fullmatch(r"args(\d)", norm_key)
    if m:
        idx = int(m.group(1)) - 1
        args[idx] = int_val
        return True
    m = re.fullmatch(r"unknown_(\d)", norm_key)
    if m:
        idx = int(m.group(1)) - 1
        if idx < 8:
            args[idx] = int_val
        return True
    return False


def parse_deh(path: str, encoding: str = "latin-1") -> DehIR:
    """
    Parse a DEH/BEX file at `path` into a DehIR.
    Uses latin-1 by default since old DEH files may contain raw bytes
    (e.g. in Text blocks) that aren't valid UTF-8.
    """
    with open(path, "r", encoding=encoding, newline="") as f:
        raw_text = f.read()

    # Normalize line endings but keep it simple; DEH is line-oriented.
    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    ir = DehIR()

    mode = None          # 'thing' | 'weapon' | 'ammo' | 'sound' | 'pointer' | 'misc' | 'cheat' | 'bracket'
    current_index = None
    current_target = None
    current_bracket = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        i += 1

        if stripped == "" or stripped.startswith("#"):
            continue

        # Header lines (only meaningful before any block starts, but harmless if repeated)
        hm = _HEADER_FIELD_RE.match(stripped)
        if hm and mode is None and current_bracket is None:
            key, val = hm.group(1).lower(), int(hm.group(2))
            if key == "doom version":
                ir.doom_version = val
            else:
                ir.patch_format = val
            continue

        # Bracket section header, e.g. [CODEPTR]
        bm = _BRACKET_HEADER_RE.match(stripped)
        if bm:
            current_bracket = bm.group(1).upper()
            mode = "bracket"
            current_target = None
            current_index = None
            continue

        # Old-style "Text <len1> <len2>" block: next len1+len2 raw chars (may span lines)
        tm = _TEXT_HEADER_RE.match(stripped)
        if tm and mode != "bracket":
            len1, len2 = int(tm.group(1)), int(tm.group(2))
            total = len1 + len2
            # Reconstruct raw text: DEH text blocks are byte-exact, but we're
            # working line-oriented. Re-join remaining lines with '\n' the
            # way they'd appear in the file, then slice by character count.
            remainder = "\n".join(lines[i:])
            blob = remainder[:total]
            # Advance i past however many source lines that consumed.
            consumed_newlines = blob.count("\n")
            i += consumed_newlines
            # If the slice ended mid-line, the next iteration still starts
            # cleanly because we only counted full newlines consumed.
            old_str, new_str = blob[:len1], blob[len1:len1 + len2]
            ir.text_renames.append((old_str, new_str))
            mode = None
            current_target = None
            continue

        # Numbered block header: Thing/Frame/Weapon/Ammo/Sound/Pointer N (name)
        nm = _BLOCK_HEADER_RE.match(stripped)
        if nm:
            block_type, idx_str, paren_name = nm.groups()
            current_index = int(idx_str)
            block_type_l = block_type.lower()
            mode = block_type_l
            current_bracket = None

            if block_type_l == "thing":
                current_target = ir.things.setdefault(current_index, {})
                if paren_name:
                    ir.things_names[current_index] = paren_name
            elif block_type_l == "frame":
                current_target = ir.frames.setdefault(current_index, {})
            elif block_type_l == "weapon":
                current_target = ir.weapons.setdefault(current_index, {})
                if paren_name:
                    ir.weapons_names[current_index] = paren_name
            elif block_type_l == "ammo":
                current_target = ir.ammo.setdefault(current_index, {})
            elif block_type_l == "sound":
                current_target = ir.sounds.setdefault(current_index, {})
            elif block_type_l == "pointer":
                # "Pointer N (Frame M)" -- current_index here is the pointer
                # slot number; the real frame number is in paren_name, e.g. "Frame 32"
                frame_num = None
                if paren_name:
                    fm = re.search(r"Frame\s+(\d+)", paren_name, re.IGNORECASE)
                    if fm:
                        frame_num = int(fm.group(1))
                current_target = ir.pointer_blocks.setdefault(frame_num if frame_num is not None else current_index, {})
            continue

        # Singleton block header: Misc / Cheat
        sm = _SINGLETON_HEADER_RE.match(stripped)
        if sm:
            block_type_l = sm.group(1).lower()
            mode = block_type_l
            current_bracket = None
            current_target = ir.misc if block_type_l == "misc" else ir.cheat
            continue

        # Otherwise: a field line, interpreted according to current mode.
        if mode == "bracket":
            _parse_bracket_line(ir, current_bracket, stripped)
            continue

        fmatch = _FIELD_RE.match(stripped)
        if not fmatch:
            # Unparseable stray line; ignore rather than crash. Could log.
            continue

        raw_key, raw_val = fmatch.groups()
        norm_key = _normalize_key(raw_key)
        val = _coerce_value(raw_val)

        if current_target is None:
            # Field appeared outside of any block (shouldn't normally happen)
            continue

        # Route Args*/Unknown* fields into a unified list on Frame targets
        if mode == "frame" and isinstance(val, int) and _apply_args_field(current_target, norm_key, val):
            continue

        # Old-style Pointer block's "Codep Frame = X" field
        if mode == "pointer" and norm_key == "codep_frame":
            current_target["codep_frame"] = val
            continue

        current_target[norm_key] = val

    return ir


def _parse_bracket_line(ir: DehIR, bracket: str, line: str):
    if bracket == "CODEPTR":
        m = re.match(r"^FRAME\s+(\d+)\s*=\s*(\S+)\s*$", line, re.IGNORECASE)
        if m:
            ir.codeptr[int(m.group(1))] = m.group(2)
        return

    if bracket == "STRINGS":
        m = re.match(r"^([A-Za-z0-9_]+)\s*=\s*(.*)$", line)
        if m:
            ir.strings[m.group(1)] = m.group(2)
        return

    if bracket in ("SPRITES", "SOUNDS", "MUSIC"):
        m = re.match(r"^(\S+)\s*=\s*(\S+)\s*$", line)
        if m:
            left, right = m.groups()
            key = int(left) if re.fullmatch(r"\d+", left) else left
            target = {"SPRITES": ir.sprites, "SOUNDS": ir.sound_names, "MUSIC": ir.music_names}[bracket]
            target[key] = right
        return

    if bracket == "PARS":
        ir.pars.append(line)
        return

    if bracket == "HELPER":
        ir.helper.append(line)
        return

    # Unknown bracket section: capture raw so nothing is silently lost.
    ir.unknown_sections.setdefault(bracket, []).append(line)


# ---------------------------------------------------------------------------
# Quick self-test / smoke test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("usage: python deh_parser.py <file.deh>")
        sys.exit(1)

    ir = parse_deh(path)
    print(f"Doom version = {ir.doom_version}, Patch format = {ir.patch_format}")
    print(f"Things:  {len(ir.things)}")
    print(f"Frames:  {len(ir.frames)}")
    print(f"Weapons: {len(ir.weapons)}")
    print(f"Ammo:    {len(ir.ammo)}")
    print(f"Sounds:  {len(ir.sounds)}")
    print(f"Pointer blocks (old-style): {len(ir.pointer_blocks)}")
    print(f"Text renames (old-style):   {len(ir.text_renames)}")
    print(f"[CODEPTR] entries: {len(ir.codeptr)}")
    print(f"[STRINGS] entries: {len(ir.strings)}")
    print(f"[SPRITES] entries: {len(ir.sprites)}")
    print(f"[SOUNDS]  entries: {len(ir.sound_names)}")
    print(f"[MUSIC]   entries: {len(ir.music_names)}")
    print(f"[PARS] raw lines:  {len(ir.pars)}")
    print(f"[HELPER] raw lines:{len(ir.helper)}")
    if ir.unknown_sections:
        print("Unknown bracket sections encountered:")
        for k, v in ir.unknown_sections.items():
            print(f"  [{k}]: {len(v)} lines (captured raw, not lost)")

    # Show a couple of samples for sanity checking
    sample_thing = next(iter(ir.things.items()))
    print("\nSample thing:", sample_thing)
    sample_frame_with_args = next(
        (kv for kv in ir.frames.items() if "args" in kv[1]), None
    )
    print("Sample frame with args:", sample_frame_with_args)
