#!/usr/bin/env python3
"""
conv2pencil_script.py
Builds a Pencil2D project from directories of Doom sprite frames — the reverse
of convertWeaponAnim.

Each directory becomes ONE layer, named after its first sprite, with the frames
laid out one Pencil2D frame apart. Doom offsets are converted back to canvas
positions so the animation lines up exactly as it does in game.

Pure standard library - no third-party dependencies.
"""

import sys
import os
import re
import shutil
import struct
import zipfile
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_NAME = "Pencil2D--WeaponAnimation-Template.pclx"
DEFAULT_OUTPUT = "animationConvert.pclx"

# Doom sprite frame characters. '^' stands in for Doom's '\', which cannot
# appear in a filename.
FRAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ[^]"

CANVAS_W, CANVAS_H = 320, 200
CENTRE_X, CENTRE_Y = CANVAS_W // 2, CANVAS_H // 2      # 160, 100

PNG_SIG = b'\x89PNG\r\n\x1a\n'


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
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
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


HELP = f"""
{bold_cyan("conv2Pencil")} — Doom sprite frames → Pencil2D project

{bold_cyan("USAGE")}
  conv2Pencil [{bold_green("--layers")} "path" ...] [{bold_green("--addlayer")} "path" ...]
              [{bold_green("--layerName")} <name> ...] [{bold_green("--chunk")}] [{bold_green("--noblank")}] [{bold_green("-o")} <name>]

{bold_cyan("WHAT IT DOES")}
  Each directory of sprite frames becomes {bold("one Pencil2D layer")}, with the
  frames one Pencil2D frame apart:

    {dim("pkrla0.png  pkrlb0.png  pkrlc0.png  ...")}
        {dim("↓")}
    {dim("layer 'pkrla0' with keyframes at 1, 2, 3, ...")}

  Doom offsets are converted back to canvas positions, so the animation sits
  exactly where it does in game. New layers are inserted between
  {bold("GuideLayer")} and {bold("statusBar")} in the template project.

{bold_cyan("LAYERS")}
  {dim("(no flag)")}          the current directory is the only layer
  {bold_green("--layers")} P...     use ONLY these paths, ignoring the current directory
  {bold_green("--addlayer")} P...   the current directory, then these paths above it

  The first layer sits {bold("lowest")}; each one after stacks above it.
  {bold_green("--layers")} and {bold_green("--addlayer")} cannot be used together.

{bold_cyan("LAYER NAMES")}
  {bold_green("--layerName")} N...  name the layers positionally
  Any layer without a name given takes the {bold("alphabetically first")} sprite in
  its directory. Supplying more names than there are layers is an error.

{bold_cyan("OFFSETS")}
  For each directory, in order:
    1. a {bold("dimgconv.txt")} in that directory
    2. the PNG's {bold("grAb")} chunk
    3. neither — the sprite is {bold("centred")} on the canvas

  {bold_green("--chunk")}          always use the grAb chunk, even where a dimgconv.txt exists

  Doom offsets convert to canvas position as:
    {dim("topLeftX = −offX − 160        topLeftY = −offY − 100")}

{bold_cyan("END KEYFRAME")}
  Each layer is closed with an {bold("empty terminator keyframe")} just past the last
  sprite. It carries no artwork — it only marks where the final sprite stops,
  which is what convertWeaponAnim needs to read the animation back.

  {bold_green("--noblank")}        leave it off, ending on the last sprite
  {bold_green("--addBlank")}       add it (the default; accepted for clarity)

  Where the {bold("last sprite already repeats the first")} — same pixels and the
  same position — that frame closes the loop by itself and no blank is
  added, since a blank after it would be ignored and the final sprite lost.

{bold_cyan("FRAME ORDER")}
  Sprite names are read as {bold("prefix + frame character + rotation digit")}, and
  ordered by Doom's own frame sequence {bold("A–Z")}, then {bold("[")}, {bold("^")}, {bold("]")}. Files that
  do not parse as sprite names fall back to alphabetical order.

  Several sprite prefixes in one directory are allowed — they all land on the
  same layer, and a warning notes it.

{bold_cyan("OUTPUT")}
  Written into the directory the script was run from, {bold("overwriting")} silently.
  Default name {bold_green(DEFAULT_OUTPUT)}; change it with {bold_green("-o")} / {bold_green("--output")}.

  The template {dim(TEMPLATE_NAME)}
  is read from the script's own folder.

{bold_cyan("EXAMPLES")}
  conv2Pencil
  conv2Pencil -o pistol.pclx
  conv2Pencil --layers ".\\gun" ".\\flash" --layerName pkrla0 pkfla0
  conv2Pencil --addlayer "..\\muzzle" --chunk
"""


# ---------------------------------------------------------------------------
# Command line paths
#
# Windows shells mangle a quoted path that ends in a backslash: the trailing
# '\' escapes the closing quote, the quoting collapses, and the path arrives
# split across several arguments wherever it contained a space. A path like
#     "d:\...\5 - RocketLauncher\v-reload\Flash\"
# comes through as eight fragments, one of which is a bare '-'. These helpers
# put such a path back together.
# ---------------------------------------------------------------------------

KNOWN_OPTS = {
    '-h', '--help', '-help',
    '--layers', '-layers',
    '--addlayer', '-addlayer',
    '--layername', '-layername',
    '--chunk', '-chunk',
    '--noblank', '-noblank',
    '--addblank', '-addblank',
    '-o', '--output', '-output',
}


def is_option(token):
    """True only for a real option word, so a stray '-' is treated as text."""
    return token.lower() in KNOWN_OPTS


def norm_path(p):
    """Strip stray quotes and any trailing separator, keeping drive roots."""
    p = p.replace('"', '').strip()
    while len(p) > 3 and p[-1] in '\\/':
        p = p[:-1]
    return p


def _regroup_words(words, exists):
    """
    Join consecutive words until each run names something real. Recovers a
    path that was split on its spaces with no quote left to mark the end.
    """
    out = []
    i = 0
    n = len(words)
    while i < n:
        hit = None
        for j in range(i, n):
            joined = norm_path(' '.join(words[i:j + 1]))
            if joined and exists(joined):
                hit = (j, joined)
                break
        if hit is not None:
            out.append(hit[1])
            i = hit[0] + 1
        else:
            out.append(norm_path(words[i]))
            i += 1
    return out


def regroup_paths(tokens, exists=os.path.isdir):
    """
    Turn the arguments following a path option back into real paths.

    Windows shells mangle a quoted path ending in a backslash: the '\\'
    escapes the closing quote, so quoting collapses and the path arrives
    broken up. Worse, the tail of one path and the head of the next can land
    in the SAME argument, e.g.

        d:\\...\\Flash" d:\\Projects\\DoomProjects\\map-Citadel

    The surviving '"' is the boundary marker, so the arguments are rejoined
    into one string and cut on the quotes. Where no quote survives, runs of
    words are joined until they resolve instead.
    """
    # Everything already valid as given — the normal, unmangled case.
    direct = [norm_path(t) for t in tokens]
    if direct and all(p and exists(p) for p in direct):
        return direct

    whole = ' '.join(tokens)

    # A surviving quote marks where one path ended and the next began.
    if '"' in whole:
        pieces = [p.strip() for p in whole.split('"')]
        pieces = [p for p in pieces if p]
        resolved = []
        ok = bool(pieces)
        for piece in pieces:
            cand = norm_path(piece)
            if cand and exists(cand):
                resolved.append(cand)
                continue
            # This piece may itself hold several space-split paths.
            sub = _regroup_words(piece.split(' '), exists)
            if sub and all(exists(p) for p in sub):
                resolved.extend(sub)
            else:
                ok = False
                break
        if ok and resolved:
            return resolved

    # No usable quotes: fall back to joining words until they resolve.
    return _regroup_words(whole.split(' '), exists)


def quoting_hint(paths):
    """Explain the trailing-backslash pitfall when a path failed to resolve."""
    return (
        "       If the path has spaces, check for a trailing backslash before the\n"
        "       closing quote — \"...\\Flash\\\" breaks the quoting and splits the\n"
        "       path up. Drop the final backslash: \"...\\Flash\""
    )


# ---------------------------------------------------------------------------
# Sprite names
# ---------------------------------------------------------------------------

def split_sprite_name(stem):
    """'pkrla0' -> ('pkrl', 'a', '0'), or None if it isn't a sprite name."""
    if len(stem) < 3:
        return None
    rotation, frame, prefix = stem[-1], stem[-2], stem[:-2]
    if not rotation.isdigit():
        return None
    if frame.upper() not in FRAME_CHARS:
        return None
    return prefix, frame, rotation


def frame_sort_key(stem):
    """
    Order by Doom's frame sequence when the name parses as a sprite, so that
    '[', '^' and ']' follow Z in the right order rather than by ASCII.
    Anything else sorts alphabetically after the sprites.
    """
    parts = split_sprite_name(stem)
    if parts is None:
        return (1, stem.lower(), 0, '')
    prefix, frame, rotation = parts
    return (0, prefix.lower(), FRAME_CHARS.index(frame.upper()), rotation)


# ---------------------------------------------------------------------------
# PNG reading
# ---------------------------------------------------------------------------

def png_info(path):
    """
    Return (width, height, grab) for a PNG, where grab is (x, y) from the grAb
    chunk or None. Raises ValueError if the file is not a PNG.
    """
    with open(path, 'rb') as fh:
        data = fh.read()

    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG")

    pos = len(PNG_SIG)
    width = height = None
    grab = None

    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], 'big')
        ctype  = data[pos + 4:pos + 8]
        body   = data[pos + 8:pos + 8 + length]
        pos += 12 + length

        if ctype == b'IHDR' and len(body) >= 8:
            width, height = struct.unpack('>II', body[:8])
        elif ctype == b'grAb' and len(body) >= 8:
            grab = struct.unpack('>ii', body[:8])
        elif ctype == b'IEND':
            break

    if width is None:
        raise ValueError("no IHDR")
    return width, height, grab


def _png_pixels(data):
    """
    Decode 8-bit RGBA non-interlaced PNG bytes to (width, height, raw_rgba),
    or None for anything else. Matches convertWeaponAnim's decoder, so the two
    tools agree on whether two frames hold the same picture.
    """
    import zlib

    if not data.startswith(PNG_SIG):
        return None

    pos = len(PNG_SIG)
    width = height = None
    idat = bytearray()

    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], 'big')
        ctype  = data[pos + 4:pos + 8]
        body   = data[pos + 8:pos + 8 + length]
        pos += 12 + length

        if ctype == b'IHDR':
            if len(body) < 13:
                return None
            width  = int.from_bytes(body[0:4], 'big')
            height = int.from_bytes(body[4:8], 'big')
            if (body[8], body[9], body[12]) != (8, 6, 0):
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
        elif ftype == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
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


def files_identical(path_a, path_b):
    """
    True when two PNG files hold the same picture. Identical bytes is the fast
    path; otherwise both are decoded and compared pixel for pixel.
    """
    try:
        with open(path_a, 'rb') as fh:
            a = fh.read()
        with open(path_b, 'rb') as fh:
            b = fh.read()
    except OSError:
        return False

    if a == b:
        return True
    pa = _png_pixels(a)
    pb = _png_pixels(b)
    if pa is None or pb is None:
        return False
    return pa == pb


# ---------------------------------------------------------------------------
# dimgconv.txt
# ---------------------------------------------------------------------------

DIMGCONV_LINE = re.compile(r'^\s*(\S+)\s+\S+\s+(-?\d+)\s+(-?\d+)\s*$')


def read_dimgconv(path):
    """
    Parse a dimgconv.txt into {lowercase sprite name: (offX, offY)}.
    Comment lines and anything that doesn't match are ignored.
    """
    table = {}
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            m = DIMGCONV_LINE.match(line)
            if m:
                table[m.group(1).lower()] = (int(m.group(2)), int(m.group(3)))
    return table


# ---------------------------------------------------------------------------
# Gather one layer's frames
# ---------------------------------------------------------------------------

def gather_layer(path, force_chunk, warnings):
    """
    Read a directory of sprite PNGs into an ordered frame list.

    Each frame: {'stem', 'file', 'width', 'height', 'topLeftX', 'topLeftY',
                 'source'} where source is how the offset was found.
    Returns (frames, default_name) or (None, None) on a fatal problem.
    """
    if not os.path.isdir(path):
        return None, f"'{path}' is not a directory"

    files = []
    for fn in sorted(os.listdir(path)):
        full = os.path.join(path, fn)
        if not os.path.isfile(full):
            continue
        stem, ext = os.path.splitext(fn)
        if ext.lower() == '.png':
            files.append((stem, fn, full))
        elif ext.lower() in ('.bmp', '.gif', '.tga', '.jpg', '.jpeg'):
            warnings.append(
                f"  {yellow('WARN')} {os.path.basename(path)}: '{fn}' is not a PNG — "
                f"skipped. Pencil2D stores PNGs, and grAb offsets are a PNG chunk."
            )

    if not files:
        return None, f"no PNG files found in '{path}'"

    # Offset source for this directory
    table = {}
    dimg = os.path.join(path, 'dimgconv.txt')
    used_dimg = False
    if os.path.isfile(dimg) and not force_chunk:
        table = read_dimgconv(dimg)
        used_dimg = True

    files.sort(key=lambda t: frame_sort_key(t[0]))

    # Note when a directory mixes sprite prefixes
    prefixes = []
    for stem, _fn, _full in files:
        parts = split_sprite_name(stem)
        p = parts[0].lower() if parts else '?'
        if p not in prefixes:
            prefixes.append(p)
    if len(prefixes) > 1:
        warnings.append(
            f"  {yellow('WARN')} {os.path.basename(path)}: several sprite prefixes here "
            f"({', '.join(prefixes)}) — they all go onto one layer."
        )

    frames = []
    for stem, fn, full in files:
        try:
            w, h, grab = png_info(full)
        except (OSError, ValueError) as e:
            warnings.append(
                f"  {yellow('WARN')} {os.path.basename(path)}: could not read '{fn}' ({e}) — "
                f"skipped."
            )
            continue

        off = table.get(stem.lower())
        if off is not None:
            source = 'dimgconv'
        elif grab is not None:
            off = grab
            source = 'grAb'
        else:
            off = None
            source = 'centred'

        if off is None:
            tx, ty = -(w // 2), -(h // 2)
        else:
            tx, ty = -off[0] - CENTRE_X, -off[1] - CENTRE_Y

        frames.append({
            'stem': stem, 'file': full, 'width': w, 'height': h,
            'topLeftX': tx, 'topLeftY': ty, 'source': source,
        })

    if not frames:
        return None, f"no readable PNG files in '{path}'"

    if used_dimg and not any(f['source'] == 'dimgconv' for f in frames):
        warnings.append(
            f"  {yellow('WARN')} {os.path.basename(path)}: dimgconv.txt matched none of the "
            f"sprites here — fell back to the grAb chunk."
        )

    return frames, frames[0]['stem']


# ---------------------------------------------------------------------------
# Build the project
# ---------------------------------------------------------------------------

def build_project(template, out_path, layers):
    """
    Write a new .pclx from the template with `layers` inserted between
    GuideLayer and statusBar. Each layer is {'name', 'frames'}.
    """
    with zipfile.ZipFile(template, 'r') as zf:
        names = zf.namelist()
        if 'main.xml' not in names:
            sys.exit(red(f"ERROR: template has no main.xml: '{template}'"))
        xml_bytes = zf.read('main.xml')
        carried = {n: zf.read(n) for n in names if n != 'main.xml'}

    root = ET.fromstring(xml_bytes)
    obj = root.find('object')
    if obj is None:
        sys.exit(red(f"ERROR: template has no <object> element: '{template}'"))

    existing = list(obj.findall('layer'))
    next_id = max((int(l.get('id', '0')) for l in existing), default=0) + 1

    # Insert directly above GuideLayer, i.e. below statusBar.
    insert_at = None
    for i, l in enumerate(existing):
        if l.get('name', '') == 'GuideLayer':
            insert_at = list(obj).index(l) + 1
            break
    if insert_at is None:
        # No GuideLayer: fall back to just below statusBar, else at the end.
        for l in existing:
            if l.get('name', '') == 'statusBar':
                insert_at = list(obj).index(l)
                break
    if insert_at is None:
        insert_at = len(list(obj))

    new_files = {}

    for layer in layers:
        lid = next_id
        next_id += 1

        el = ET.Element('layer')
        el.set('id', str(lid))
        el.set('name', layer['name'])
        el.set('visibility', '1')
        el.set('type', '1')

        for n, fr in enumerate(layer['frames'], start=1):
            src = f"{lid:03d}.{n:03d}.png"
            img = ET.SubElement(el, 'image')
            img.set('src', src)
            img.set('frame', str(n))
            img.set('topLeftX', str(fr['topLeftX']))
            img.set('topLeftY', str(fr['topLeftY']))
            img.set('opacity', '1')
            with open(fr['file'], 'rb') as fh:
                new_files[f"data/{src}"] = fh.read()

        # An empty keyframe closing the set. Pencil2D writes no file for a
        # blank keyframe — the <image> entry exists but its src is absent from
        # the archive — so nothing is added to new_files here.
        if layer.get('blank'):
            n = len(layer['frames']) + 1
            img = ET.SubElement(el, 'image')
            img.set('src', f"{lid:03d}.{n:03d}.png")
            img.set('frame', str(n))
            img.set('topLeftX', '0')
            img.set('topLeftY', '0')
            img.set('opacity', '1')

        obj.insert(insert_at, el)
        insert_at += 1
        layer['id'] = lid

    body = ET.tostring(root, encoding='unicode')
    out_xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<!DOCTYPE PencilDocument>\n' + body + '\n')

    tmp = out_path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
        # mimetype first and uncompressed, as in Pencil2D's own archives
        if 'mimetype' in carried:
            zi = zipfile.ZipInfo('mimetype')
            zi.compress_type = zipfile.ZIP_STORED
            zf.writestr(zi, carried.pop('mimetype'))
        zf.writestr('main.xml', out_xml)
        for n, data in carried.items():
            zf.writestr(n, data)
        for n, data in new_files.items():
            zf.writestr(n, data)

    shutil.move(tmp, out_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv):
    layers_raw = None
    add_raw = None
    layer_names = []
    force_chunk = False
    no_blank = False
    output = None

    i = 0
    while i < len(argv):
        a = argv[i]
        al = a.lower()

        if al in ('--layers', '-layers'):
            layers_raw = []
            i += 1
            while i < len(argv) and not is_option(argv[i]):
                layers_raw.append(argv[i])
                i += 1
            if not layers_raw:
                sys.exit(red("ERROR: --layers needs at least one path."))
            continue

        if al in ('--addlayer', '-addlayer'):
            add_raw = []
            i += 1
            while i < len(argv) and not is_option(argv[i]):
                add_raw.append(argv[i])
                i += 1
            if not add_raw:
                sys.exit(red("ERROR: --addlayer needs at least one path."))
            continue

        if al in ('--layername', '-layername'):
            i += 1
            while i < len(argv) and not is_option(argv[i]):
                layer_names.append(argv[i].replace('"', '').strip())
                i += 1
            if not layer_names:
                sys.exit(red("ERROR: --layerName needs at least one name."))
            continue

        if al in ('--chunk', '-chunk'):
            force_chunk = True
            i += 1
            continue

        if al in ('--noblank', '-noblank'):
            no_blank = True
            i += 1
            continue

        if al in ('--addblank', '-addblank'):
            # The default; accepted so it can be stated explicitly.
            no_blank = False
            i += 1
            continue

        if al in ('-o', '--output', '-output'):
            if i + 1 >= len(argv):
                sys.exit(red("ERROR: --output needs a filename."))
            output = argv[i + 1].replace('"', '').strip()
            i += 2
            continue

        if a.startswith('-'):
            sys.exit(red(f"ERROR: unknown option '{a}'.  Use -h for help."))

        sys.exit(red(f"ERROR: unexpected argument '{a}'.  Use -h for help."))

    if layers_raw is not None and add_raw is not None:
        sys.exit(red(
            "ERROR: --layers and --addlayer cannot be used together.\n"
            "       --layers replaces the current directory; --addlayer adds to it."
        ))

    layers_paths = regroup_paths(layers_raw) if layers_raw is not None else None
    add_paths    = regroup_paths(add_raw)    if add_raw    is not None else None

    return layers_paths, add_paths, layer_names, force_chunk, no_blank, output


def main():
    argv = sys.argv[1:]
    if any(a.lower() in ('-h', '--help', '-help') for a in argv):
        print(HELP)
        sys.exit(0)

    layers_paths, add_paths, layer_names, force_chunk, no_blank, output = parse_args(argv)

    run_dir = os.getcwd()
    template = os.path.join(SCRIPT_DIR, TEMPLATE_NAME)
    if not os.path.isfile(template):
        sys.exit(red(
            f"ERROR: template not found:\n"
            f"       {template}\n"
            f"       It must sit in the same folder as the script."
        ))

    if layers_paths is not None:
        paths = layers_paths
    elif add_paths is not None:
        paths = [run_dir] + add_paths
    else:
        paths = [run_dir]

    if len(layer_names) > len(paths):
        sys.exit(red(
            f"ERROR: {len(layer_names)} name(s) given to --layerName but there "
            f"are only {len(paths)} layer(s)."
        ))

    out_name = output or DEFAULT_OUTPUT
    if not out_name.lower().endswith('.pclx'):
        out_name += '.pclx'
    out_path = os.path.join(run_dir, os.path.basename(out_name))

    print(bold_cyan("conv2Pencil"))
    print(f"  {dim('template: ' + template)}")
    if force_chunk:
        print(f"  {dim('offsets:  grAb chunk forced')}")
    print()

    warnings = []
    layers = []

    for n, p in enumerate(paths):
        frames, info = gather_layer(os.path.abspath(p), force_chunk, warnings)
        if frames is None:
            msg = f"ERROR: {info}"
            if 'not a directory' in info:
                msg += "\n" + quoting_hint(paths)
            sys.exit(red(msg))
        name = layer_names[n] if n < len(layer_names) else info

        # A last frame identical to the first - same pixels AND same position -
        # already closes the loop, and convertWeaponAnim reads it as the
        # terminator. Adding a blank there would leave the blank ignored and
        # the final sprite dropped, so it is left off.
        loop_close = False
        if len(frames) >= 2:
            a, z = frames[0], frames[-1]
            if ((a['topLeftX'], a['topLeftY']) == (z['topLeftX'], z['topLeftY'])
                    and files_identical(a['file'], z['file'])):
                loop_close = True

        layers.append({'name': name, 'frames': frames,
                       'path': os.path.abspath(p),
                       'blank': (not no_blank) and (not loop_close),
                       'loop_close': loop_close})

    if warnings:
        for w in warnings:
            print(w)
        print()

    for n, layer in enumerate(layers, start=1):
        where = 'bottom' if n == 1 else f'#{n}'
        if layer['loop_close']:
            closer = f"last frame repeats the first — it closes the set"
        elif layer['blank']:
            closer = f"blank terminator at frame {len(layer['frames']) + 1}"
        else:
            closer = "no terminator"
        print(f"  {bold('━━ ' + layer['name'] + ' ━━')}  "
              f"{dim(where + '  ' + layer['path'])}")
        print(f"  {dim(closer)}")
        print(f"  {'Sprite':<14} {'Frame':>5} {'Size':>10}   {'topLeft':>12}   offsets")
        print(f"  {'-'*14} {'-'*5} {'-'*10}   {'-'*12}   -------")
        for i, fr in enumerate(layer['frames'], start=1):
            tag = {'dimgconv': dim('dimgconv.txt'),
                   'grAb':     dim('grAb'),
                   'centred':  yellow('centred')}[fr['source']]
            size = f"{fr['width']}x{fr['height']}"
            pos  = f"{fr['topLeftX']},{fr['topLeftY']}"
            print(f"  {fr['stem']:<14} {i:>5} {size:>10}   {pos:>12}   {tag}")
        print()

    build_project(template, out_path, layers)

    total = sum(len(l['frames']) for l in layers)
    centred = sum(1 for l in layers for f in l['frames'] if f['source'] == 'centred')
    blanks = sum(1 for l in layers if l['blank'])
    loops  = sum(1 for l in layers if l['loop_close'])
    summary = f"  {len(layers)} layer(s), {total} frame(s)"
    if blanks:
        summary += f", {blanks} blank terminator(s)"
    if loops:
        summary += f", {loops} closed by a repeated first frame"
    if centred:
        summary += f", {centred} centred (no offsets found)"
    print(summary)
    print()
    print(f"  {bold_green('Written:')} {out_path}")
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
