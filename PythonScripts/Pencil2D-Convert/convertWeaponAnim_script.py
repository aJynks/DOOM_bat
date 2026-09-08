#!/usr/bin/env python3
"""
convertWeaponAnim_script.py
Converts a Pencil2D .pclx weapon animation into Doom/DECOHack assets.

Each BITMAP LAYER is one sprite set, laid out on a single row of the timeline:
the layer is named after the FIRST sprite in the series, and every subsequent
keyframe is the next sprite. The gap between keyframes is the duration in tics,
and the final keyframe must be blank to close the last one.

Layer name keywords (after a '--'):
    --Reverse            frame characters count DOWN instead of up

Sound layers are named  LUMPNAME--TARGETLAYER  and bind to that layer by name.

Outputs, written into _<InputFilename>/ next to the .pclx:
    dimgconv.txt      DoomTools graphic offset file, grouped by sprite prefix
    decohack.dh       DECOHack states, one block per sprite set
    <PREFIX>/*.png    exported keyframe artwork, with --export

Pure standard library - no third-party dependencies.
"""

import sys
import os
import zipfile
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Colour / help helpers
# ---------------------------------------------------------------------------

def _supports_colour():
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    return True

USE_COLOUR = _supports_colour()

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if USE_COLOUR else text

def bold_cyan(t):  return _c("1;36", t)
def bold_green(t): return _c("1;32", t)
def yellow(t):     return _c("33",   t)
def dim(t):        return _c("2",    t)
def red(t):        return _c("1;31", t)
def bold(t):       return _c("1",    t)


# ---------------------------------------------------------------------------
# Doom sprite frame characters.
#   A-Z  = frames 0-25
#   [    = frame 26
#   ^    = stands in for Doom's '\' (frame 27); a backslash cannot appear in a
#          filename, so '^' is used in its place throughout.
#   ]    = frame 28
# ---------------------------------------------------------------------------
FRAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ[^]"

SOUND_LAYER_TYPE  = '4'
BITMAP_LAYER_TYPE = '1'

# Reference layers that are never sprite sets, whatever they are named.
# Every layer name is usable as a stem now, so these need naming explicitly
# rather than being skipped for failing to parse.
SKIP_LAYERS = {'guidelayer', 'statusbar', 'camera layer'}

KEYWORD_REVERSE = 'reverse'
KEYWORD_COMBINE = 'combine'

SEP = '--'


def parse_keywords(name):
    """
    Split a layer name into (base, reverse, combine_id, bad_keyword).

    Keywords follow the base name, each after a '--', in any order:
        tst1A0--combine1            -> base tst1A0, combine '1'
        tst1A0--combine1--Reverse   -> base tst1A0, combine '1', reverse
        tst1A0--Reverse--combine1   -> same thing

    bad_keyword is the first unrecognised token, or None.
    """
    parts = name.split(SEP)
    base = parts[0]
    reverse = False
    combine = None
    bad = None

    for token in parts[1:]:
        low = token.strip().lower()
        if low == KEYWORD_REVERSE:
            reverse = True
        elif low.startswith(KEYWORD_COMBINE) and low[len(KEYWORD_COMBINE):].isdigit():
            combine = low[len(KEYWORD_COMBINE):]
        else:
            if bad is None:
                bad = token
    return base, reverse, combine, bad


HELP = f"""
{bold_cyan("convertWeaponAnim")} — Pencil2D .pclx → Doom weapon animation files

{bold_cyan("USAGE")}
  convertWeaponAnim {bold("<file.pclx>")} [{bold_green("--export")}]

{bold_cyan("OPTIONS")}
  {bold_green("--export")}         Write each keyframe's artwork out as a PNG, into a
                   subdirectory named after its sprite prefix:
                     {dim("_<InputFilename>/<PREFIX>/<SPRITENAME>.png")}
                   Transparency is preserved — the bytes are copied straight
                   from the archive. {dim("(--extract is accepted as an alias.)")}
                   Each prefix folder is {bold("emptied first")}, contents and all,
                   so nothing lingers from an earlier run. Only the folders
                   this run writes are touched; anything else in the output
                   directory is left alone, and nothing is deleted unless
                   the .pclx parses cleanly.

{bold_cyan("OUTPUTS")}
  Written into {bold("_<InputFilename>/")} next to the .pclx:
  {bold_green("dimgconv.txt")}   DoomTools graphic offset file, {bold("grouped by sprite prefix")}
  {bold_green("decohack.dh")}    DECOHack states, {bold("one block per sprite set")}
  {bold_green("<PREFIX>/*.png")} exported keyframe artwork, with {bold_green("--export")}

{bold_cyan("SPRITE LAYERS")}
  Each bitmap layer is {bold("one sprite set on a single timeline row")}. The layer
  name decides what the sprites are called:

  {bold("Named after its first sprite")} — {dim("prefix + frame character + rotation digit")} —
  and that name is used exactly as written:
    {dim("wap3bA0")}  → {dim("wap3bA0, wap3bB0, wap3bC0 ...")}

  {bold("Named anything else")} — the whole name becomes the stem, with {bold("_")} appended
  and the frames running from {bold("A0")}:
    {dim("Shoot")}    → {dim("Shoot_A0, Shoot_B0, Shoot_C0 ...")}
    {dim("Flash")}    → {dim("Flash_A0, Flash_B0 ...")}

  {yellow("Note")}: a free-form name ending in a letter and a digit reads as the first
  form — {dim("Flash_v4")} is taken as prefix {dim("Flash_")} starting at frame {dim("v")}, not as
  {dim("Flash_v4_A0")}. Avoid a trailing letter+digit unless that is what you want.

  {bold("GuideLayer")}, {bold("statusBar")} and camera layers are always skipped.

    {dim("layer  wap3bA0")}
    {dim("  frame  1 ─┐ wap3bA0   4 tics")}
    {dim("  frame  5 ─┤ wap3bB0   4 tics")}
    {dim("  frame  9 ─┤ wap3bC0   4 tics")}
    {dim("  frame 13 ─┘ (blank)   closes the set")}

  The name splits as {bold("prefix + frame character + rotation digit")}, so {dim("wap3bA0")}
  → prefix {bold("wap3b")}, frame {bold("A")}, rotation {bold("0")}. The frame character advances per
  keyframe; prefix and rotation carry through.

  Tic count is the gap to the next keyframe, so a set beginning late in the
  timeline still starts at its first state — no leading wait is emitted.

  The set is closed by an {bold("end keyframe")}, which supplies the final sprite's
  duration and is not itself a sprite. Either:
    {bold("a blank keyframe")}       — an empty Pencil2D keyframe, or
    {bold("a repeat of frame 1")}    — the same artwork at the same position,
                            closing a loop
  A blank keyframe {bold("takes precedence")}: where one is present it ends the set,
  and any earlier frame repeating the first is just a normal sprite. The
  repeat only closes the set when there is no blank at all. A set with
  neither is an error.

  Several layers may live in one .pclx; each is an independent set, and they
  may overlap on the same frames without interfering.

{bold_cyan("HIDDEN LAYERS")}
  A layer with its {bold("eye closed")} in Pencil2D is ignored completely — sprite
  and sound layers alike. Use it to park alternate takes or work in progress
  without them reaching the output. Anything skipped is listed at the top of
  the run, so it is never a silent loss. A sound whose target layer is
  hidden is dropped with a warning rather than treated as a bad target.

{bold_cyan("LAYER KEYWORDS")}
  A sprite layer may carry keywords after {bold("--")}, in any order:

    {bold_green("--Reverse")}     frame characters count {bold("DOWN")} instead of up
    {bold_green("--combine#")}    merge this layer with others sharing the number

  {dim("wap3I0--Reverse")} with two keyframes gives {dim("wap3I0")} then {dim("wap3H0")}.
  Playback order is unchanged — keyframes still run first to last in time.
  Only the lettering runs backwards. Keywords are case-insensitive; an
  unrecognised one is an error rather than a silently-forward set.

{bold_cyan("COMBINING LAYERS")}
  Layers tagged with the same {bold("--combine#")} are flattened into one sprite
  set, exactly as if their artwork had been pasted onto a single keyframe:

    {dim("panel top     tst2A0--combine1   ─┐ drawn on top")}
    {dim("panel bottom  tst1A0--combine1   ─┘ names the set")}

  The {bold("bottom")} layer of the group supplies the sprite name, and carries
  {bold_green("--Reverse")} if the group is reversed — the keyword on any other member
  is an error. Members stack in panel order, later drawn over earlier.

  Blank keyframes draw nothing, so a member that has blanked simply drops
  out of the composite; the set ends once every member is blank. Members
  need not share keyframe times — at each time, whichever artwork is
  currently showing gets composited, just as the editor displays it.

  The combined offset is the union of the members' rectangles, so the merged
  image may be any shape or size relative to its parts:
    {dim("offX = −min(160 + topLeftX)     offY = −min(100 + topLeftY)")}

  Any number of groups may coexist — {dim("--combine1")}, {dim("--combine2")}, and so on.

{bold_cyan("FRAME CHARACTERS")}
  Frames run {bold("A–Z")}, then {bold("[")}, {bold("^")}, {bold("]")} — Doom's own sequence, except that
  {bold("^")} stands in for Doom's backslash, which cannot appear in a filename.
  Running off either end is an error.

{bold_cyan("SOUND LAYERS")}
  Name a sound layer {bold("LUMPNAME--TARGETLAYER")}:

    {dim("DSDSHTGN--wap3bA0")}   plays DSHTGN on the wap3bA0 row

  The lump's leading {bold("DS")} is stripped for the pointer call, giving
  {dim("A_WeaponSound(DSHTGN, 0)")}. The target is matched case-insensitively
  against the layer's {bold("base name")} — everything before the first {bold("--")} — so
  {dim("DSDBOPN--Shoot")} finds a layer called {dim("Shoot--combine1")}. The full layer
  name works too, e.g. {dim("DSX--wap3I0--Reverse")}. Naming any member of a
  combine group binds the sound to that whole group.

  The sound frame maps onto that row's own timeline. Landing on a state's
  {bold("first tic")} attaches it directly:
    {dim("wap3b B 4 A_WeaponSound(DSHTGN, 0)")}
  Landing {bold("mid-state")} splits it so the sound fires on the right tic:
    {dim("wap3b P 1")}
    {dim("wap3b P 2 A_WeaponSound(DBCLS, 0)")}
  Several sounds on the same tic become stacked 0-tic states.

  A sound layer with no {bold("--")} target, or naming a layer that does not
  exist, is an error.

{bold_cyan("OFFSETS")}
  320×200 canvas, origin at screen centre (160, 100):
    offX = −(160 + topLeftX)
    offY = −(100 + topLeftY)

  dimgconv.txt holds {bold("one entry per unique sprite name")} — the first
  occurrence in panel order wins and later duplicates are skipped, so a
  reversed set replaying sprites the forward set already defined does not
  emit them twice.

{bold_cyan("CASE")}
  Sprite names, prefixes, frame characters and sound names are written
  {bold("UPPER CASE")} in both text files, and exported PNGs are named to match,
  so everything lines up with Doom's uppercase lump names however the
  Pencil2D layers happen to be capitalised.

{bold_cyan("SKIP LAYERS")}
  Camera layers, and any bitmap layer whose name does not end in a frame
  character plus a rotation digit (GuideLayer, statusBar, ...), are skipped.

{bold_cyan("EXAMPLES")}
  convertWeaponAnim SSQ_Animation.pclx
  convertWeaponAnim SSQ_Animation.pclx --export
  convertWeaponAnim "C:\\anim\\Weapon Anims.pclx" --export
"""


def strip_ds(lump_name):
    """DSDSHTGN -> DSHTGN. Leading 'DS' stripped, case-insensitive."""
    if len(lump_name) > 2 and lump_name[:2].upper() == 'DS':
        return lump_name[2:]
    return lump_name


# ---------------------------------------------------------------------------
# PNG pixel comparison (pure standard library)
#
# Pencil2D writes every layer bitmap as 8-bit RGBA, non-interlaced, so a small
# decoder covers it. Used to spot a set whose last artwork keyframe repeats its
# first one, closing a loop.
# ---------------------------------------------------------------------------

_PNG_SIG = b'\x89PNG\r\n\x1a\n'


def _png_pixels(data):
    """
    Decode 8-bit RGBA non-interlaced PNG bytes to (width, height, raw_rgba).
    Returns None for anything else, so the caller can fall back to comparing
    the bytes as-is.
    """
    import zlib

    if not data.startswith(_PNG_SIG):
        return None

    pos = len(_PNG_SIG)
    width = height = None
    idat = bytearray()

    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], 'big')
        ctype  = data[pos + 4:pos + 8]
        body   = data[pos + 8:pos + 8 + length]
        pos += 12 + length          # length + type + data + crc

        if ctype == b'IHDR':
            if len(body) < 13:
                return None
            width  = int.from_bytes(body[0:4], 'big')
            height = int.from_bytes(body[4:8], 'big')
            bit_depth, colour_type = body[8], body[9]
            interlace = body[12]
            # 8-bit RGBA, no interlacing, only.
            if (bit_depth, colour_type, interlace) != (8, 6, 0):
                return None
        elif ctype == b'IDAT':
            idat += body
        elif ctype == b'IEND':
            break

    if width is None or not idat:
        return None

    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None

    channels = 4
    stride = width * channels
    if len(raw) < height * (stride + 1):
        return None

    out = bytearray(height * stride)
    prev = bytearray(stride)

    for y in range(height):
        base = y * (stride + 1)
        ftype = raw[base]
        line = bytearray(raw[base + 1:base + 1 + stride])

        if ftype == 0:
            pass
        elif ftype == 1:                      # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:                      # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:                      # Average
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:                      # Paeth
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        else:
            return None

        out[y * stride:(y + 1) * stride] = line
        prev = line

    return width, height, bytes(out)


def images_identical(data_a, data_b):
    """
    True when two PNGs hold the same picture. Identical bytes is the fast path;
    otherwise both are decoded and their pixels compared, so artwork that was
    re-saved and no longer matches byte-for-byte is still recognised.
    """
    if data_a == data_b:
        return True
    pa = _png_pixels(data_a)
    pb = _png_pixels(data_b)
    if pa is None or pb is None:
        return False        # undecodable and not byte-identical
    return pa == pb


def _png_encode(width, height, raw_rgba):
    """Encode 8-bit RGBA pixel data as a PNG (filter 0 on every row)."""
    import zlib

    stride = width * 4
    body = bytearray()
    for y in range(height):
        body.append(0)
        body += raw_rgba[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        c = tag + data
        return (len(data).to_bytes(4, 'big') + c
                + zlib.crc32(c).to_bytes(4, 'big'))

    ihdr = (width.to_bytes(4, 'big') + height.to_bytes(4, 'big')
            + bytes((8, 6, 0, 0, 0)))
    return (_PNG_SIG
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(bytes(body), 9))
            + chunk(b'IEND', b''))


def composite_layers(pieces):
    """
    Flatten several bitmaps into one, exactly as Pencil2D does when artwork is
    pasted together onto a single keyframe.

    `pieces` is an ordered list of (png_bytes, screen_x, screen_y), BOTTOM
    first — later entries are drawn on top. Screen coordinates are the layer's
    top-left on the 320x200 canvas, i.e. 160+topLeftX / 100+topLeftY.

    Returns (png_bytes, screen_x, screen_y, width, height) for the combined
    image, or None if any piece could not be decoded.

    Because Pencil2D stores every bitmap tightly cropped, the union of the
    pieces' rectangles is itself tight — each edge is touched by some piece's
    real content — so no re-cropping is needed and the offset follows directly
    from the union's top-left.
    """
    decoded = []
    for data, sx, sy in pieces:
        px = _png_pixels(data)
        if px is None:
            return None
        w, h, raw = px
        decoded.append((raw, w, h, sx, sy))

    ux0 = min(d[3] for d in decoded)
    uy0 = min(d[4] for d in decoded)
    ux1 = max(d[3] + d[1] for d in decoded)
    uy1 = max(d[4] + d[2] for d in decoded)
    W, H = ux1 - ux0, uy1 - uy0

    buf = bytearray(W * H * 4)

    for raw, w, h, sx, sy in decoded:
        ox, oy = sx - ux0, sy - uy0
        for y in range(h):
            si = y * w * 4
            di = ((y + oy) * W + ox) * 4
            for _x in range(w):
                sa = raw[si + 3]
                if sa:
                    if sa == 255:
                        buf[di:di + 4] = raw[si:si + 4]
                    else:
                        da = buf[di + 3]
                        # source-over
                        oa = sa + da * (255 - sa) // 255
                        if oa:
                            for c in range(3):
                                buf[di + c] = (raw[si + c] * sa
                                               + buf[di + c] * da * (255 - sa) // 255) // oa
                            buf[di + 3] = oa
                si += 4
                di += 4

    return _png_encode(W, H, bytes(buf)), ux0, uy0, W, H


def split_sprite_name(base):
    """
    'wap3bA0' -> ('wap3b', 'A', '0')  |  None if it isn't a sprite name.
    The last character must be a rotation digit and the one before it a valid
    Doom frame character.
    """
    if len(base) < 3:
        return None
    rotation, frame, prefix = base[-1], base[-2], base[:-2]
    if not rotation.isdigit():
        return None
    if frame.upper() not in FRAME_CHARS:
        return None
    return prefix, frame, rotation


def frame_char(start_char, step, reverse=False):
    """
    Advance (or retreat) a frame character. Returns None if it runs off either
    end of the Doom frame sequence.
    """
    idx = FRAME_CHARS.index(start_char.upper()) + (-step if reverse else step)
    if idx < 0 or idx >= len(FRAME_CHARS):
        return None
    ch = FRAME_CHARS[idx]
    if start_char.islower() and ch.isalpha():
        ch = ch.lower()
    return ch


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def build_set(name, base, prefix, first_frame, rotation, reverse, order,
              keyframes, read_bytes, errors, warnings):
    """
    Turn one layer's keyframes into a sprite set.

    `read_bytes(src)` returns the PNG bytes for a keyframe source, so this
    works for real layers (reading from the archive) and for a flattened
    combine group (reading from the composited cache) alike.

    Returns the set dict, or None when the layer could not be used - in which
    case a message has been appended to `errors` or `warnings`.
    """
    blanks   = [i for i, (f, tx, ty, s) in enumerate(keyframes) if tx == 0 and ty == 0]
    art_idx  = [i for i in range(len(keyframes)) if i not in blanks]
    last_i   = len(keyframes) - 1

    if not art_idx:
        warnings.append(
            f"  {yellow('WARN')} {name}: layer holds only blank keyframes — skipped."
        )
        return None

    # --- Work out which keyframe closes the set -----------------------
    # Either the last artwork keyframe repeats the first one (a loop), or
    # a blank keyframe ends the layer. The loop is checked first, so a
    # redundant trailing blank after a repeat does not turn the repeat
    # into an extra sprite.
    term_i = None
    loop_close = False

    # A blank keyframe is an explicit statement of where the set ends, so it
    # wins. Only when there is no blank does a last frame repeating the first
    # close the set instead.
    if last_i in blanks:
        term_i = last_i
    elif blanks:
        frames_txt = ', '.join(str(keyframes[i][0]) for i in blanks)
        errors.append(
            f"  {red('ERROR')} {name}: blank keyframe(s) at frame {frames_txt} are not "
            f"the last keyframe.\n"
            f"         A blank keyframe closes the set, so it can only be the final "
            f"one.\n"
            f"         Every other keyframe must hold the artwork for its sprite."
        )
        return None
    elif len(art_idx) >= 2:
        first_kf = keyframes[art_idx[0]]
        last_kf  = keyframes[art_idx[-1]]
        if (first_kf[1], first_kf[2]) == (last_kf[1], last_kf[2]):
            try:
                a = read_bytes(first_kf[3])
                b = read_bytes(last_kf[3])
            except KeyError:
                a = b = None
            if a is not None and images_identical(a, b):
                term_i = art_idx[-1]
                loop_close = True

    if term_i is None:
        errors.append(
            f"  {red('ERROR')} {name}: the set has no end keyframe.\n"
            f"         The last keyframe ({keyframes[last_i][0]}) holds artwork that "
            f"differs from the\n"
            f"         first, so the final sprite's duration cannot be worked out. "
            f"Either add an\n"
            f"         empty keyframe after it, or repeat the first frame there to "
            f"close a loop —\n"
            f"         the gap to that frame becomes the last sprite's tic count."
        )
        return None

    # Any blank before the terminator is a hole in the middle of the set.
    stray = [i for i in blanks if i < term_i]
    if stray:
        frames_txt = ', '.join(str(keyframes[i][0]) for i in stray)
        errors.append(
            f"  {red('ERROR')} {name}: blank keyframe(s) at frame {frames_txt} sit inside "
            f"the set.\n"
            f"         A blank keyframe closes the set, so it can only come at the end.\n"
            f"         Every other keyframe must hold the artwork for its sprite."
        )
        return None

    sprite_kfs = [keyframes[i] for i in art_idx if i < term_i]
    terminator = keyframes[term_i]

    if not sprite_kfs:
        warnings.append(
            f"  {yellow('WARN')} {name}: layer holds no artwork before its end "
            f"keyframe — skipped."
        )
        return None

    # --- Range check on the frame characters --------------------------
    start_idx = FRAME_CHARS.index(first_frame.upper())
    room = (start_idx + 1) if reverse else (len(FRAME_CHARS) - start_idx)
    if len(sprite_kfs) > room:
        direction = "back past 'A'" if reverse else f"past '{FRAME_CHARS[-1]}'"
        errors.append(
            f"  {red('ERROR')} {name}: {len(sprite_kfs)} sprites starting at frame "
            f"'{first_frame}' runs {direction}.\n"
            f"         A {'reversed ' if reverse else ''}set can hold at most {room} "
            f"sprite(s) from here."
        )
        return None

    # --- Build the sprite list ----------------------------------------
    sprites = []
    failed = False
    for step, (fnum, tx, ty, src) in enumerate(sprite_kfs):
        ch = frame_char(first_frame, step, reverse)
        nxt = sprite_kfs[step + 1][0] if step + 1 < len(sprite_kfs) else terminator[0]
        tics = nxt - fnum
        if tics <= 0:
            errors.append(
                f"  {red('ERROR')} {name}: keyframe at frame {fnum} has a duration of "
                f"{tics} tics.\n"
                f"         Keyframes must be in ascending order with a gap between them."
            )
            failed = True
            break
        sprites.append({
            'sprite_name': f"{prefix}{ch}{rotation}",
            'prefix':   prefix, 'letter': ch, 'rotation': rotation,
            'frame':    fnum,   'next_frame': nxt, 'tics': tics,
            'topLeftX': tx,     'topLeftY': ty,
            'offX': -(160 + tx), 'offY': -(100 + ty),
            'src_png':  src,
            'duplicate_of': None,
        })
    if failed:
        return None

    return {
        'layer_name': name, 'base': base, 'prefix': prefix,
        'rotation': rotation, 'reverse': reverse, 'order': order,
        'sprites': sprites, 'terminator_frame': terminator[0],
        'loop_close': loop_close, 'combine': None, 'members': None,
    }


def merge_group(cid, members, root, read_bytes, cache):
    """
    Flatten a --combine group into one synthetic keyframe list.

    Members are ordered bottom-first. At each keyframe time in the union of
    all members' times, whichever members currently show artwork are
    composited together, bottom to top. Blank keyframes draw nothing, so a
    member that has gone blank simply drops out; when every member is blank
    the group has ended and that time becomes the terminator.

    Returns (keyframes, errors) where keyframes matches the shape build_set
    expects — (frame, topLeftX, topLeftY, src) — with `src` a synthetic key
    into `cache` holding the composited PNG bytes.
    """
    errors = []

    times = sorted({f for m in members for (f, tx, ty, src) in m['keyframes']})

    def state_at(member, t):
        """The member's active keyframe at time t, or None before it starts."""
        cur = None
        for kf in member['keyframes']:
            if kf[0] <= t:
                cur = kf
            else:
                break
        return cur

    merged = []
    for t in times:
        pieces = []
        for m in members:
            kf = state_at(m, t)
            if kf is None:
                continue
            f, tx, ty, src = kf
            if tx == 0 and ty == 0:
                continue                      # blank draws nothing
            pieces.append((src, 160 + tx, 100 + ty))

        if not pieces:
            # Everything is blank here: this closes the set.
            merged.append((t, 0, 0, None))
            continue

        try:
            loaded = [(read_bytes(src), sx, sy) for src, sx, sy in pieces]
        except KeyError as e:
            errors.append(
                f"  {red('ERROR')} --combine{cid}: a keyframe bitmap is missing from the "
                f".pclx ({e})."
            )
            return None, errors

        if len(loaded) == 1:
            data, sx, sy = loaded[0]
            key = f"__combine{cid}__{t}"
            cache[key] = data
            merged.append((t, sx - 160, sy - 100, key))
            continue

        result = composite_layers(loaded)
        if result is None:
            errors.append(
                f"  {red('ERROR')} --combine{cid}: could not decode a keyframe bitmap at "
                f"frame {t}.\n"
                f"         Layers in this group: "
                f"{', '.join(m['layer_name'] for m in members)}"
            )
            return None, errors

        png, ux0, uy0, _w, _h = result
        key = f"__combine{cid}__{t}"
        cache[key] = png
        merged.append((t, ux0 - 160, uy0 - 100, key))

    # A synthetic blank needs a src build_set will never read; reuse the first
    # real one, since blanks are identified by topLeft (0,0) alone.
    merged = [(f, tx, ty, (src if src is not None else '')) for f, tx, ty, src in merged]

    return merged, errors


def parse_pclx(path):
    """
    Returns (sets, sounds, warnings, errors).

      sets    ordered list of dicts, one per bitmap layer forming a sprite set.
      sounds  one dict per <sound> element, carrying its raw target name; the
              binding to a set is resolved after all layers are known.
    """
    if not zipfile.is_zipfile(path):
        sys.exit(red(f"ERROR: '{path}' is not a valid .pclx (ZIP) file."))

    zf = zipfile.ZipFile(path, 'r')
    if 'main.xml' not in zf.namelist():
        zf.close()
        sys.exit(red("ERROR: No main.xml found inside the .pclx archive."))
    xml_data = zf.read('main.xml')

    root = ET.fromstring(xml_data)
    obj = root.find('object')
    if obj is None:
        zf.close()
        sys.exit(red("ERROR: <object> element not found in main.xml."))

    sets, sounds, warnings, errors = [], [], [], []
    hidden = []          # names of layers skipped for being hidden
    combine_groups = {}  # combine id -> [member, ...] in panel order
    combined_png = {}    # synthetic src key -> composited PNG bytes

    for order, layer in enumerate(obj.findall('layer')):
        name  = layer.get('name', '')
        ltype = layer.get('type', '')

        # --- Hidden layers are ignored completely -------------------------
        # Pencil2D writes visibility="0" when the eye is closed.
        if layer.get('visibility', '1') == '0':
            if ltype in (BITMAP_LAYER_TYPE, SOUND_LAYER_TYPE):
                hidden.append(name)
            continue

        # --- Sound layer -------------------------------------------------
        if ltype == SOUND_LAYER_TYPE:
            if SEP not in name:
                errors.append(
                    f"  {red('ERROR')} {name}: sound layer has no '{SEP}' target.\n"
                    f"         Name sound layers  LUMPNAME{SEP}TARGETLAYER  so the sound knows\n"
                    f"         which sprite row it belongs to, e.g. DSDSHTGN{SEP}wap3bA0"
                )
                continue
            lump, target = name.split(SEP, 1)
            if not lump or not target:
                errors.append(
                    f"  {red('ERROR')} {name}: sound layer name must be "
                    f"LUMPNAME{SEP}TARGETLAYER — one side is empty."
                )
                continue

            snd_elems = layer.findall('sound')
            if not snd_elems:
                warnings.append(
                    f"  {yellow('WARN')} {name}: sound layer contains no sound keyframes — "
                    f"nothing to place."
                )
                continue
            for snd in snd_elems:
                try:
                    fnum = int(snd.get('frame', '0'))
                except ValueError:
                    continue
                sounds.append({'layer': name, 'lump': lump, 'name': strip_ds(lump),
                               'target': target, 'frame': fnum, 'owner': None})
            continue

        if ltype != BITMAP_LAYER_TYPE:
            continue

        # Reference layers are never sprite sets.
        if name.strip().lower() in SKIP_LAYERS:
            continue

        # --- Sprite layer: split off any keywords --------------------------
        base, reverse, combine, bad_kw = parse_keywords(name)

        if bad_kw is not None:
            errors.append(
                f"  {red('ERROR')} {name}: unknown layer keyword '{bad_kw}'.\n"
                f"         Known keywords: Reverse, combine<number> "
                f"(case-insensitive, any order).\n"
                f"         A layer name containing '--' is read as name--keyword."
            )
            continue

        parts = split_sprite_name(base)

        # A layer named after its first sprite keeps that name exactly. Any
        # other name becomes the stem itself, with '_' appended and the frames
        # running from A0 — so a layer called 'Shoot' gives Shoot_A0, Shoot_B0,
        # and so on.
        if parts is None:
            parts = (base + '_', 'A', '0')

        # --- Collect keyframes in timeline order --------------------------
        keyframes = []
        for img in layer.findall('image'):
            try:
                fnum = int(img.get('frame', '0'))
                tx   = int(img.get('topLeftX', '0'))
                ty   = int(img.get('topLeftY', '0'))
            except ValueError:
                continue
            keyframes.append((fnum, tx, ty, img.get('src', '')))
        keyframes.sort(key=lambda k: k[0])

        if not keyframes:
            warnings.append(f"  {yellow('WARN')} {name}: layer has no keyframes — skipped.")
            continue

        # --- Members of a combine group are stashed, not built yet --------
        if combine is not None:
            combine_groups.setdefault(combine, []).append({
                'layer_name': name, 'base': base, 'parts': parts,
                'reverse': reverse, 'order': order, 'keyframes': keyframes,
            })
            continue

        prefix, first_frame, rotation = parts

        built = build_set(name, base, prefix, first_frame, rotation, reverse,
                          order, keyframes,
                          lambda src: zf.read(f"data/{src}"),
                          errors, warnings)
        if built is not None:
            sets.append(built)
        continue

    # --- Flatten each combine group into one synthetic set ----------------
    for cid in sorted(combine_groups, key=lambda c: min(m['order'] for m in combine_groups[c])):
        members = sorted(combine_groups[cid], key=lambda m: m['order'])
        root = members[0]                     # bottom layer names the group

        stray = [m for m in members[1:] if m['reverse']]
        if stray:
            errors.append(
                f"  {red('ERROR')} --combine{cid}: '{stray[0]['layer_name']}' carries "
                f"--Reverse, but it is not the bottom layer of the group.\n"
                f"         Put --Reverse on '{root['layer_name']}', the layer everything "
                f"else composites onto."
            )
            continue

        if len(members) < 2:
            warnings.append(
                f"  {yellow('WARN')} --combine{cid}: only one layer "
                f"('{root['layer_name']}') carries this tag — nothing to composite with."
            )

        if root['parts'] is None:
            errors.append(
                f"  {red('ERROR')} --combine{cid}: the bottom layer "
                f"'{root['layer_name']}' must be named after the sprite the group "
                f"produces.\n"
                f"         Its name should end in a frame character and a rotation "
                f"digit, e.g. CHGRA0--combine{cid}.\n"
                f"         The other layers in the group can be named anything."
            )
            continue

        merged, merr = merge_group(cid, members, root,
                                   lambda src: zf.read(f"data/{src}"),
                                   combined_png)
        if merr:
            errors.extend(merr)
            continue

        r_prefix, r_first, r_rot = root['parts']
        built = build_set(root['layer_name'], root['base'], r_prefix,
                          r_first, r_rot, root['reverse'],
                          root['order'],
                          merged,
                          lambda key: combined_png[key],
                          errors, warnings)
        if built is not None:
            built['combine'] = cid
            built['members'] = [m['layer_name'] for m in members]
            sets.append(built)

    sets.sort(key=lambda st: st['order'])

    zf.close()
    return sets, sounds, warnings, errors, hidden, combined_png


def resolve_sound_targets(sets, sounds, hidden):
    """
    Bind each sound to its target set by layer name, case-insensitively.

    The target is matched against the layer's BASE name - everything before
    the first '--' - so a sound written  soundLayer--layer1  finds a layer
    called  layer1--combine1. The full layer name is accepted too, so an
    existing  DSX--wap3I0--Reverse  still resolves.

    Naming any member of a --combine group binds the sound to that group,
    since the group is a single timeline.

    A target that names a HIDDEN layer is not an error - hidden layers are
    ignored, so the sound is dropped with a warning. Only a name matching no
    layer at all is a real mistake.
    """
    errors, warnings = [], []

    by_full = {}
    by_base = {}
    for st in sets:
        by_full.setdefault(st['layer_name'].lower(), st)
        by_base.setdefault(st['base'].lower(), []).append(st)
        # Members of a combine group resolve to the group they belong to.
        for member in (st.get('members') or []):
            m_base = member.split(SEP)[0].lower()
            by_full.setdefault(member.lower(), st)
            if all(x is not st for x in by_base.get(m_base, [])):
                by_base.setdefault(m_base, []).append(st)

    hidden_full = {h.lower() for h in hidden}
    hidden_base = {h.split(SEP)[0].lower() for h in hidden}

    for snd in sounds:
        want = snd['target'].strip().lower()

        st = None
        matches = by_base.get(want, [])
        if len(matches) > 1:
            errors.append(
                f"  {red('ERROR')} {snd['layer']}: target '{snd['target']}' is ambiguous — "
                f"more than one layer has that base name:\n"
                f"         {', '.join(m['layer_name'] for m in matches)}"
            )
            continue
        if matches:
            st = matches[0]
        else:
            st = by_full.get(want)

        if st is None:
            if want in hidden_full or want in hidden_base:
                warnings.append(
                    f"  {yellow('WARN')} {snd['layer']}: target layer '{snd['target']}' is "
                    f"hidden — sound dropped."
                )
            else:
                known = ', '.join(s['layer_name'] for s in sets) or '(none)'
                errors.append(
                    f"  {red('ERROR')} {snd['layer']}: target layer '{snd['target']}' does not "
                    f"exist.\n"
                    f"         Sprite layers in this file: {known}"
                )
            continue
        snd['owner'] = st
    return errors, warnings



# ---------------------------------------------------------------------------
# Duplicate sprite names — dimgconv keeps only the first
# ---------------------------------------------------------------------------

def mark_duplicates(sets):
    """
    Flag any sprite name that has already appeared. The first occurrence in
    panel order is the one written to dimgconv.txt; later ones are skipped.
    A repeat carrying a DIFFERENT offset is warned about, since only one
    offset can be baked into a given graphic.
    """
    warnings = []
    seen = {}
    for st in sets:
        for s in st['sprites']:
            key = s['sprite_name'].lower()
            if key in seen:
                first_set, first = seen[key]
                s['duplicate_of'] = first_set['layer_name']
                if (s['offX'], s['offY']) != (first['offX'], first['offY']):
                    warnings.append(
                        f"  {yellow('WARN')} {s['sprite_name']}: defined by '{first['sprite_name']}' "
                        f"in {first_set['layer_name']} at ({first['offX']},{first['offY']}) but "
                        f"repeated in {st['layer_name']} at ({s['offX']},{s['offY']}) — a sprite "
                        f"can only carry one offset; the first is what gets written."
                    )
            else:
                seen[key] = (st, s)
    return warnings


# ---------------------------------------------------------------------------
# Export keyframe bitmaps (--export)
# ---------------------------------------------------------------------------

_BAD_PATH_CHARS = '<>:"/\\|?*'


def safe_name(name):
    out = ''.join('_' if ch in _BAD_PATH_CHARS or ord(ch) < 32 else ch for ch in name)
    return out, (out != name)


def export_sprites(sets, pclx_path, out_dir, combined_png=None):
    """
    Write each unique sprite's artwork out as a PNG:
        _<InputFilename>/<PREFIX>/<SPRITENAME>.png

    Pencil2D's stored bitmaps are already RGBA PNGs, so the bytes are copied
    straight out of the archive — lossless and transparency preserved. Images
    merged by --combine are written from the composited cache instead.
    Duplicated sprite names are written once, matching dimgconv.txt.
    Names are UPPER CASE so they line up with the dimgconv.txt entries.

    Each prefix folder this run produces is removed first, contents and all,
    so a renamed or deleted sprite cannot linger from an earlier run. Only
    those exact folders are touched — anything else in the output directory
    is left alone.
    """
    import shutil

    warnings = []
    written = 0
    dirs = []

    # Every folder this run is about to write into.
    targets = []
    for st in sets:
        for s in st['sprites']:
            if s['duplicate_of']:
                continue
            d, _ = safe_name(s['prefix'].upper())
            if d not in targets:
                targets.append(d)

    cleared = []
    for d in targets:
        path = os.path.join(out_dir, d)
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
                cleared.append(d)
            except OSError as e:
                sys.exit(red(
                    f"ERROR: could not clear the existing export folder '{path}' ({e}).\n"
                    f"       Close anything using it and run again."
                ))

    if cleared:
        print(f"  {dim('cleared ' + str(len(cleared)) + ' existing export folder(s): ' + ', '.join(cleared))}")
        print()

    zf = zipfile.ZipFile(pclx_path, 'r')
    try:
        for st in sets:
            for s in st['sprites']:
                if s['duplicate_of']:
                    continue

                dir_name,  dir_changed  = safe_name(s['prefix'].upper())
                file_name, name_changed = safe_name(s['sprite_name'].upper())
                if dir_changed or name_changed:
                    warnings.append(
                        f"  {yellow('WARN')} {s['sprite_name']}: name contains characters that "
                        f"are not valid in a path — written as '{dir_name}/{file_name}.png'."
                    )

                try:
                    src = s['src_png']
                    if combined_png and src in combined_png:
                        data = combined_png[src]
                    else:
                        data = zf.read(f"data/{src}")
                except KeyError:
                    warnings.append(
                        f"  {yellow('WARN')} {s['sprite_name']}: bitmap '{s['src_png']}' not "
                        f"found inside the .pclx — not exported."
                    )
                    continue

                target_dir = os.path.join(out_dir, dir_name)
                dest = os.path.join(target_dir, file_name + '.png')
                try:
                    os.makedirs(target_dir, exist_ok=True)
                    with open(dest, 'wb') as fh:
                        fh.write(data)
                    written += 1
                    if target_dir not in dirs:
                        dirs.append(target_dir)
                except OSError as e:
                    warnings.append(
                        f"  {yellow('WARN')} {s['sprite_name']}: could not write '{dest}' ({e})."
                    )
    finally:
        zf.close()

    return written, dirs, warnings


# ---------------------------------------------------------------------------
# Build states, splitting where sounds land mid-way
# ---------------------------------------------------------------------------

def build_states(sets, sounds):
    """
    Build a state list per set. Returns (blocks, warnings, dropped).
    A sound frame maps onto its target row's own timeline.
    """
    warnings = []
    dropped = set()
    blocks = []

    for st in sets:
        sprites = st['sprites']
        my_sounds = [s for s in sounds if s['owner'] is st]

        per_state = {}
        for snd in my_sounds:
            placed = False
            for i, s in enumerate(sprites):
                if s['frame'] <= snd['frame'] < s['next_frame']:
                    per_state.setdefault(i, []).append((snd['frame'] - s['frame'], snd))
                    placed = True
                    break
            if not placed:
                dropped.add((snd['layer'], snd['frame']))
                span = (f"{sprites[0]['frame']}–{st['terminator_frame']}"
                        if sprites else 'empty')
                warnings.append(
                    f"  {yellow('WARN')} {snd['layer']}: sound at frame {snd['frame']} falls "
                    f"outside {st['layer_name']} (frames {span}) — dropped."
                )

        states = []
        for i, s in enumerate(sprites):
            entries = sorted(per_state.get(i, []), key=lambda e: e[0])

            if not entries:
                states.append({'prefix': s['prefix'], 'letter': s['letter'],
                               'tics': s['tics'], 'action': None})
                continue

            groups = []
            for offset, snd in entries:
                if groups and groups[-1][0] == offset:
                    groups[-1][1].append(snd)
                else:
                    groups.append((offset, [snd]))

            cursor = 0
            for gi, (offset, group) in enumerate(groups):
                if offset > cursor:
                    states.append({'prefix': s['prefix'], 'letter': s['letter'],
                                   'tics': offset - cursor, 'action': None})
                    cursor = offset

                next_offset = groups[gi + 1][0] if gi + 1 < len(groups) else s['tics']
                span = next_offset - cursor

                for si, snd in enumerate(group):
                    is_last = (si == len(group) - 1)
                    states.append({'prefix': s['prefix'], 'letter': s['letter'],
                                   'tics': span if is_last else 0,
                                   'action': f"A_WeaponSound({snd['name'].upper()}, 0)"})
                cursor = next_offset

        blocks.append((st, states))

    return blocks, warnings, dropped


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_dimgconv(sets, out_path):
    """
    One entry per unique sprite name, grouped by set under a comment header.
    Repeats of a name already written are skipped.

    Names are written UPPER CASE, matching Doom lump naming.
    """
    lines = []
    first_group = True
    for st in sets:
        fresh = [s for s in st['sprites'] if not s['duplicate_of']]
        if not fresh:
            continue
        if not first_group:
            lines.append("\n")
        first_group = False
        lines.append(f"# ---- {st['prefix'].upper()} ----\n")
        for s in fresh:
            lines.append(f"{s['sprite_name'].upper()} graphic {s['offX']} {s['offY']}\n")
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.writelines(lines)


def write_decohack(blocks, out_path):
    """
    One block of states per set, each under a comment header.

    Sprite names and frame characters are written UPPER CASE.
    """
    lines = []
    for gi, (st, states) in enumerate(blocks):
        if gi > 0:
            lines.append("\n")
        header = st['prefix'].upper() + ("  (reverse)" if st['reverse'] else "")
        lines.append(f"# ---- {header} ----\n")
        for s in states:
            line = f"{s['prefix'].upper()} {s['letter'].upper()} {s['tics']}"
            if s['action']:
                line += f" {s['action']}"
            lines.append(line + "\n")
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.writelines(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

KNOWN_OPTS = {
    '-h', '--help', '-help',
    '-export', '--export', '-extract', '--extract',
}


def norm_path(p):
    """Strip stray quotes and any trailing separator, keeping drive roots."""
    p = p.replace('"', '').strip()
    while len(p) > 3 and p[-1] in '\\/':
        p = p[:-1]
    return p


def parse_args(argv):
    """
    Windows shells mangle a quoted path that ends in a backslash: the trailing
    '\\' escapes the closing quote, quoting collapses, and the path arrives
    split wherever it contained a space - often including a lone '-' from a
    folder like "5 - RocketLauncher". The arguments are rejoined into one
    string and cut on any surviving quote, then on word boundaries.
    """
    export = False
    rest = []

    for a in argv:
        if a.lower() in KNOWN_OPTS:
            if a.lower() in ('-export', '--export', '-extract', '--extract'):
                export = True
            continue
        rest.append(a)

    if not rest:
        return None, export

    # Single, unmangled argument - the normal case.
    if len(rest) == 1:
        single = norm_path(rest[0])
        if not os.path.exists(single) and rest[0].startswith('-'):
            sys.exit(red(f"ERROR: unknown option '{rest[0]}'.  Use -h for help."))
        return single, export

    whole = ' '.join(rest)

    # A surviving quote marks where the path ended.
    if '"' in whole:
        for piece in (x.strip() for x in whole.split('"')):
            cand = norm_path(piece)
            if cand and os.path.isfile(cand):
                return cand, export

    # The whole thing as one path.
    joined = norm_path(whole)
    if os.path.isfile(joined):
        return joined, export

    # Longest leading run that resolves, so stray trailing words are caught.
    for j in range(len(rest), 0, -1):
        cand = norm_path(' '.join(rest[:j]))
        if os.path.isfile(cand):
            leftover = rest[j:]
            if leftover:
                sys.exit(red(
                    f"ERROR: unexpected extra argument '{leftover[0]}'.  Use -h for help."
                ))
            return cand, export

    stray = next((a for a in rest if a.startswith('-')), None)
    if stray:
        sys.exit(red(
            f"ERROR: unknown option '{stray}'.  Use -h for help.\n"
            f"       If this came from a path, check for a trailing backslash before\n"
            f"       the closing quote - \"...\\anim\\\" breaks the quoting and splits\n"
            f"       the path up. Drop the final backslash: \"...\\anim\""
        ))

    sys.exit(red(
        f"ERROR: could not make sense of the arguments: {whole}\n"
        f"       If the path has spaces, check for a trailing backslash before the\n"
        f"       closing quote - \"...\\anim\\\" breaks the quoting and splits the\n"
        f"       path up. Drop the final backslash: \"...\\anim\""
    ))


def main():
    argv = sys.argv[1:]
    if not argv or any(a.lower() in ('-h', '--help', '-help') for a in argv):
        print(HELP)
        sys.exit(0 if argv else 1)

    pclx_path, do_export = parse_args(argv)

    if pclx_path is None:
        sys.exit(red("ERROR: no .pclx file given.  Use -h for help."))
    if not os.path.isfile(pclx_path):
        sys.exit(red(f"ERROR: File not found: '{pclx_path}'"))
    if not pclx_path.lower().endswith('.pclx'):
        print(yellow(f"WARNING: '{pclx_path}' does not have a .pclx extension — attempting anyway."))

    pclx_abs  = os.path.abspath(pclx_path)
    base_stem = os.path.splitext(os.path.basename(pclx_abs))[0]
    out_dir   = os.path.join(os.path.dirname(pclx_abs), f"_{base_stem}")

    dimgconv_path = os.path.join(out_dir, "dimgconv.txt")
    decohack_path = os.path.join(out_dir, "decohack.dh")

    print(bold_cyan("convertWeaponAnim") + f"  {dim(pclx_path)}")
    if do_export:
        print(f"  {dim('export: on')}")
    print()

    sets, sounds, warnings, errors, hidden, combined_png = parse_pclx(pclx_path)
    snd_errors, snd_warnings = resolve_sound_targets(sets, sounds, hidden)
    errors.extend(snd_errors)
    warnings.extend(snd_warnings)
    sounds = [s for s in sounds if s['owner'] is not None]

    if hidden:
        print(f"  {dim('ignored ' + str(len(hidden)) + ' hidden layer(s): ' + ', '.join(hidden))}")
        print()

    if errors:
        for w in warnings:
            print(w)
        for e in errors:
            print(e)
        print()
        sys.exit(red("Nothing written — fix the error(s) above and run again."))

    if not sets:
        for w in warnings:
            print(w)
        sys.exit(red("ERROR: No sprite layers found. Nothing written."))

    warnings.extend(mark_duplicates(sets))

    os.makedirs(out_dir, exist_ok=True)

    exported_count, exported_dirs = 0, []
    if do_export:
        exported_count, exported_dirs, ex_warnings = export_sprites(
            sets, pclx_abs, out_dir, combined_png)
        warnings.extend(ex_warnings)

    blocks, snd_warnings, dropped = build_states(sets, sounds)
    warnings.extend(snd_warnings)

    if warnings:
        for w in warnings:
            print(w)
        print()

    # ---- Per-set report ----
    for st in sets:
        my_sounds = [s for s in sounds if s['owner'] is st]
        closed = "loop repeat" if st['loop_close'] else "blank"
        meta = (f"prefix {st['prefix']}, rotation {st['rotation']}, "
                f"closed by {closed} at frame {st['terminator_frame']}")
        tag = bold_green("  REVERSE") if st['reverse'] else ""
        if st.get('combine'):
            tag += bold_green(f"  COMBINE{st['combine']}")
        print(f"  {bold('━━ ' + st['layer_name'] + ' ━━')}{tag}  {dim(meta)}")
        if st.get('members'):
            print(f"  {dim('composited: ' + ' + '.join(st['members']))}")
        print(f"  {'Sprite':<16} {'Frame':>6} {'Tics':>5}   {'offX':>6} {'offY':>6}")
        print(f"  {'-'*16} {'-'*6} {'-'*5}   {'-'*6} {'-'*6}")
        for s in st['sprites']:
            note = dim(f"  dup of {s['duplicate_of']}") if s['duplicate_of'] else ""
            print(f"  {s['sprite_name']:<16} {s['frame']:>6} {s['tics']:>5}   "
                  f"{s['offX']:>6} {s['offY']:>6}{note}")

        if my_sounds:
            print()
            for s in my_sounds:
                if (s['layer'], s['frame']) in dropped:
                    tail = yellow("dropped — outside this row")
                else:
                    tail = dim(f"A_WeaponSound({s['name']}, 0)")
                print(f"  {s['lump']:<16} frame {s['frame']:>3}  →  {tail}")
        print()

    write_dimgconv(sets, dimgconv_path)
    write_decohack(blocks, decohack_path)

    total_sprites = sum(len(st['sprites']) for st in sets)
    unique = sum(1 for st in sets for s in st['sprites'] if not s['duplicate_of'])
    dups   = total_sprites - unique
    total_states = sum(len(states) for _, states in blocks)

    summary = f"  {len(sets)} set(s), {unique} sprite(s)"
    if dups:
        summary += f" ({dups} duplicate(s) skipped)"
    summary += f", {total_states} state(s)"
    if sounds:
        summary += f", {len(sounds) - len(dropped)} sound(s)"
        if dropped:
            summary += f" ({len(dropped)} dropped)"
    if do_export:
        summary += f", {exported_count} png(s) exported"
    print(summary)
    print()
    print(f"  {bold_green('Written:')} {dimgconv_path}")
    print(f"  {bold_green('Written:')} {decohack_path}")
    for d in exported_dirs:
        print(f"  {bold_green('Written:')} {os.path.join(d, '')}{dim('*.png')}")
    print()


if __name__ == '__main__':
    try:
        main()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        os._exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
