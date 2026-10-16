#!/usr/bin/env python3
# =============================================================================
#  timelapseMap_script.py  -  render a Doom map "being drawn" as an mp4 timelapse
#  Lines are drawn in linedef index order as the IDDT automap, using
#  dsda/nyan automap colour rules. Things: not yet implemented.
#  Self-contained. Pure stdlib Python. Requires ffmpeg on PATH.
# =============================================================================

# =============================================================================
#  EDITABLE SETTINGS
# =============================================================================

# IWADs selectable with -iwad <alias>. Only the IWAD's PLAYPAL is used.
# If the input PWAD has its own PLAYPAL, that one is used instead.
IWAD_ALIASES = {
    "doom"     : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom.wad",
    "doom2"    : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom2.wad",
    "tnt"      : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\tnt.wad",
    "plutonia" : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\plutonia.wad",
    "heretic"  : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\heretic.wad",
    "hexen"    : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\hexen.wad",
    "free1"    : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom1.wad",
    "free2"    : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\freedoom2.wad",
    "doom94"   : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom_1993.wad",
    "doom294"  : r"D:\Projects\DoomProjects\_SourcePorts\_iwads\doom2_1994.wad",
}
IWAD_DEFAULT = "doom2"

# Output video
RESOLUTION  = "1080p"     # 480p 720p 1080p 4k 8k 16k, or a width (always 16:9)   (-rez)
OUTPUT_FORMAT = "mp4"     # mp4, or png = numbered PNG image sequence in a folder  (-format)
FPS         = 30
CRF         = 18          # x264 quality: lower = better / bigger (18 is visually lossless-ish)
PRESET      = "medium"    # x264 speed preset

# Framing
MARGIN_PCT  = 5.0         # empty border around the map in the full-map view, as % of frame size

# Camera
CAM_MODE    = "off"       # off    = whole map, scaled once to fit the frame          (-cam)
                          # steady = zoomed, lines in index order; the camera stays still while
                          #          the pen is in the middle of the frame, glides after it
                          #          when it nears an edge, and when the next line starts
                          #          off-screen the pen pauses while the camera pans there
                          # follow = like steady, but at an off-screen jump the pen keeps
                          #          drawing while the camera quickly catches up
                          # lock   = zoomed, index order, pen tip locked dead centre (cuts)
                          # trace  = like follow, but the pen walks connected lines and glides
                          #          (without drawing) across any gaps: one continuous point
                          # boxed  = the map is cut into a grid of 16:9 boxes (anchored on the
                          #          player 1 start); the camera frames one box, draws what is
                          #          inside it (trace walk), then pans to the next box
ZOOM        = "4096mu"    # follow view size                                          (-zoom)
                          #   4096mu = 4096 map units across the frame width
                          #   15.5   = 15.5% of the full-map view (also "15.5%")
                          #   4x     = 4 times closer than the full-map view (= 25%)
BOX         = ""          # box mode: box width (16:9), same forms as ZOOM; "" = use ZOOM
                          # (set on the command line as  -cam box 6004mu)
BOX_ZOOM_SECONDS = 1.0    # box mode: between boxes the camera zooms out to the full map,
BOX_HOLD_SECONDS = 1.0    # holds, then zooms into the next box. Zoom time each way  (-boxzoom)
                          # and the hold on the full map                             (-boxhold)
                          # BOX_ZOOM_SECONDS = 0: no zoom - pan straight to the next box instead
BOX_PAN_SECONDS  = 0.75   # pan time when the box zoom is 0 (holds are then 0 too)    (-boxpan)
BOX_ORDER        = "sweep"   # order the boxes are visited in                        (-boxorder)
                          #   sweep  = always step to a box touching the last one (diagonals
                          #            too), picking the one with the fewest unfinished
                          #            neighbours - edges and corners are cleared as it goes,
                          #            so nothing is left behind; jumps only when boxed in
                          #   spiral = ring by ring outwards from player 1's box
                          #   dense  = next is the densest box directly beside the last one,
                          #            else the densest box anywhere
BOX_MARGIN       = 5      # boxes only move as far as needed to fit what is left to draw in
                          # them, keeping it this % away from the frame edge
THING_BOX_ZOOM_SECONDS = ""  # the same two for the thing boxes; "" = same as the line  (-thingboxzoom)
THING_BOX_HOLD_SECONDS = ""  # boxes                                                    (-thingboxhold)
THING_BOX   = ""          # box size for placing things, same forms as ZOOM; "" = the line box.
                          # Giving -thingbox places things box by box in ANY camera mode (-thingbox)
MID_HOLD_SECONDS = 2.0    # with -things: hold on the full map between lines and things (-midhold)
JUMP_TRANSITION = 1       # trace/boxed: gap-glide speed as a multiple of the pen speed (-jumptransition)
FOLLOW_DEADZONE = 60      # steady/follow: central % of the frame the pen moves in without
                          # the camera moving
FOLLOW_EASE     = 0.6     # steady/follow: how lazily the camera glides after the pen (seconds)
FOLLOW_CATCHUP  = 0.25    # follow: the quicker chase after a jump to an off-screen line (s)
END_ZOOM_SECONDS = 2.0    # follow/trace: zoom out to the full map once drawing ends  (-endzoom)

# Pacing
DRAW_SPEED         = 3000 # pen speed in map units per second (override with -drawspeed)
VID_LENGTH         = ""   # "" = off. Total video length: everything is time-scaled to fit.
                          #   20 = 20s   1.20 = 1m20s   2.5.0 = 2h5m0s   (":" also works)
                          #   override with -vidlength
HOLD_START_SECONDS = 0.5  # black frames before drawing starts
HOLD_END_SECONDS   = 4.0  # hold on the finished full map                               (-endhold)

# Drawing
LINE_WIDTH        = 2     # pixels (-linewidth). Raise it for 8k/16k renders you will zoom into

# Automap colours (PLAYPAL indices) - names/values from nyan-doom.cfg
# The map is always drawn like IDDT (all lines, including "never show" lines).
# A value of 0 means "off": the line falls through to the next rule.
mapcolor_back     = 247   # background
mapcolor_wall     = 176   # one-sided walls, secret-flagged (ML_SECRET) lines
mapcolor_fchg     = 64    # two-sided, floor height differs
mapcolor_cchg     = 231   # two-sided, ceiling height differs
mapcolor_clsd     = 0     # closed doors (floor == ceiling)
mapcolor_rdor     = 174   # red key doors
mapcolor_bdor     = 197   # blue key doors
mapcolor_ydor     = 229   # yellow key doors
mapcolor_tele     = 112   # teleport lines
mapcolor_secr     = 251   # secret sector boundaries
mapcolor_exit     = 4     # normal exit lines  (pure white; nyan default is 47)
mapcolor_exitsecr = 4     # secret exit lines  (pure white; nyan default is 63)
mapcolor_flat     = 97    # two-sided, no height change

mapcolor_sprt     = 112   # things drawn as triangles

# Things pass - runs after the map is fully drawn (and zoomed out, in follow/trace)
THINGS       = "off"      # off | tri = green triangles | img = real sprites         (-things [img])
THING_TYPES  = "default"  # categories to show, comma separated                       (-thingtypes)
                          #   monsters weapons keys armor powerups health bonuses ammo decor
                          #   deathmatch                (player 1-4 starts: always, placed first)
                          #   default = monsters,weapons,keys,armor,powerups    all = everything
THING_SKILL  = 4          # only things present on this skill (1-5; 4 = Ultra-Violence)  (-skill)
                          # multiplayer-only things (co-op / deathmatch) are never shown
THING_RATE   = 60         # things placed per second                                  (-thingrate)
THING_SCALE  = 1.0        # size multiplier; 1 = true size (1 sprite pixel = 1 map unit) (-thingscale)
THING_MIN_PX = 12         # smallest on-screen size, so things stay visible zoomed out
THING_TRACE  = False      # follow/trace: keep the zoomed camera for the things too - the pen
                          # travels thing to thing and each appears as it is reached  (-tracethings)
                          # (follow = index order, trace = nearest-next order). Default: things
                          # are placed on the full map after the zoom-out
THING_ZOOM   = ""         # -tracethings view size, same forms as ZOOM; "" = use ZOOM.  (-zoomthing)
                          # Giving -zoomthing turns -tracethings on, even with -cam off
THING_SPEED  = 0          # -tracethings pen speed in map units/s; 0 = same as the draw speed (-thingspeed)

# =============================================================================
#  END OF SETTINGS
# =============================================================================

import os
import sys
import math
import struct
import shutil
import subprocess
import re
import bisect

try:                                  # Pillow does the line and sprite drawing (fast, in C)
    from PIL import Image, ImageDraw, ImageOps
except ImportError:
    if not any(a.lower() in ("-h", "--help", "-help", "/?") for a in sys.argv[1:]) and len(sys.argv) > 1:
        print("This script needs Pillow. Install it with:\n    pip install pillow")
        sys.exit(1)

try:
    import msvcrt                 # Windows: non-blocking key check for "S = stop and save"
except ImportError:
    msvcrt = None


class StopRender(Exception):
    pass


# ------------------------------------------------------------------ log ---
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class ConsoleLog:
    """Passes console output through and keeps a plain-text copy (minus the progress counter)."""

    def __init__(self, stream):
        self.stream = stream
        self.lines = []

    def write(self, text):
        self.stream.write(text)
        if "Rendering:" in text:
            return len(text)
        self.lines.append(ANSI.sub("", text))
        return len(text)

    def flush(self):
        self.stream.flush()


def log_path_for(out):
    """Log sits next to the output with the same name: foo.mp4 -> foo.log, foo_frames -> foo_frames.log."""
    root, ext = os.path.splitext(out)
    return (root if ext.lower() in (".mp4", ".png") else out) + ".log"


def write_log(out, result):
    """Write <output>.log: when, where, the exact command line, the result and the console summary."""
    import datetime
    con = sys.stdout if isinstance(sys.stdout, ConsoleLog) else None
    cmdline = subprocess.list2cmdline([SCRIPT_NAME] + sys.argv[1:])
    text = [f"{SCRIPT_NAME} log",
            f"Date     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Folder   : {os.getcwd()}",
            f"Command  : {cmdline}",
            f"Result   : {result}",
            ""]
    if con:
        text.append("".join(con.lines).rstrip("\n"))
    path = log_path_for(out)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(text) + "\n")
    except OSError as e:
        print(f"{C_ERR}WARNING:{C_RST} could not write log '{path}': {e}")
        return
    if con:
        con.stream.write(f"  {C_DIM}log: {path}{C_RST}\n")

# ---------------------------------------------------------------- console ---
if os.name == "nt":
    os.system("")  # enable ANSI escape handling on Windows consoles

C_RST = "\033[0m"
C_HDR = "\033[1;36m"
C_OPT = "\033[1;33m"
C_ARG = "\033[0;32m"
C_DIM = "\033[0;37m"
C_ERR = "\033[1;31m"
C_OK  = "\033[1;32m"

SCRIPT_NAME = "timelapseMap"

# Stock Doom 2 things: doomednum -> (sprite, spawn frame, radius, category).
# Generated from Chocolate Doom's info.c (spawn state of each mobj). Invisible things
# (teleport destinations, Icon of Sin spawn spots / shooter) are not listed.
THING_TABLE = {
    1    : ("PLAY", "A",  16, "p1"),  # PLAYER 1 START (always shown)
    2    : ("PLAY", "A",  16, "p2"),  # PLAYER 2 START (co-op)
    3    : ("PLAY", "A",  16, "p3"),  # PLAYER 3 START (co-op)
    4    : ("PLAY", "A",  16, "p4"),  # PLAYER 4 START (co-op)
    5    : ("BKEY", "A",  20, "keys"),  # MT_MISC4
    6    : ("YKEY", "A",  20, "keys"),  # MT_MISC6
    7    : ("SPID", "A", 128, "monsters"),  # MT_SPIDER
    8    : ("BPAK", "A",  20, "ammo"),  # MT_MISC24
    9    : ("SPOS", "A",  20, "monsters"),  # MT_SHOTGUY
    10   : ("PLAY", "W",  20, "decor"),  # MT_MISC68
    11   : ("PLAY", "A",  16, "deathmatch"),  # DEATHMATCH START
    12   : ("PLAY", "W",  20, "decor"),  # MT_MISC69
    13   : ("RKEY", "A",  20, "keys"),  # MT_MISC5
    15   : ("PLAY", "N",  20, "decor"),  # MT_MISC62
    16   : ("CYBR", "A",  40, "monsters"),  # MT_CYBORG
    17   : ("CELP", "A",  20, "ammo"),  # MT_MISC21
    18   : ("POSS", "L",  20, "decor"),  # MT_MISC63
    19   : ("SPOS", "L",  20, "decor"),  # MT_MISC67
    20   : ("TROO", "M",  20, "decor"),  # MT_MISC66
    21   : ("SARG", "N",  20, "decor"),  # MT_MISC64
    22   : ("HEAD", "L",  20, "decor"),  # MT_MISC61
    23   : ("SKUL", "K",  20, "decor"),  # MT_MISC65
    24   : ("POL5", "A",  20, "decor"),  # MT_MISC71
    25   : ("POL1", "A",  16, "decor"),  # MT_MISC74
    26   : ("POL6", "A",  16, "decor"),  # MT_MISC75
    27   : ("POL4", "A",  16, "decor"),  # MT_MISC72
    28   : ("POL2", "A",  16, "decor"),  # MT_MISC70
    29   : ("POL3", "A",  16, "decor"),  # MT_MISC73
    30   : ("COL1", "A",  16, "decor"),  # MT_MISC32
    31   : ("COL2", "A",  16, "decor"),  # MT_MISC33
    32   : ("COL3", "A",  16, "decor"),  # MT_MISC34
    33   : ("COL4", "A",  16, "decor"),  # MT_MISC35
    34   : ("CAND", "A",  20, "decor"),  # MT_MISC49
    35   : ("CBRA", "A",  16, "decor"),  # MT_MISC50
    36   : ("COL5", "A",  16, "decor"),  # MT_MISC37
    37   : ("COL6", "A",  16, "decor"),  # MT_MISC36
    38   : ("RSKU", "A",  20, "keys"),  # MT_MISC8
    39   : ("YSKU", "A",  20, "keys"),  # MT_MISC7
    40   : ("BSKU", "A",  20, "keys"),  # MT_MISC9
    41   : ("CEYE", "A",  16, "decor"),  # MT_MISC38
    42   : ("FSKU", "A",  16, "decor"),  # MT_MISC39
    43   : ("TRE1", "A",  16, "decor"),  # MT_MISC40
    44   : ("TBLU", "A",  16, "decor"),  # MT_MISC41
    45   : ("TGRN", "A",  16, "decor"),  # MT_MISC42
    46   : ("TRED", "A",  16, "decor"),  # MT_MISC43
    47   : ("SMIT", "A",  16, "decor"),  # MT_MISC47
    48   : ("ELEC", "A",  16, "decor"),  # MT_MISC48
    49   : ("GOR1", "A",  16, "decor"),  # MT_MISC51
    50   : ("GOR2", "A",  16, "decor"),  # MT_MISC52
    51   : ("GOR3", "A",  16, "decor"),  # MT_MISC53
    52   : ("GOR4", "A",  16, "decor"),  # MT_MISC54
    53   : ("GOR5", "A",  16, "decor"),  # MT_MISC55
    54   : ("TRE2", "A",  32, "decor"),  # MT_MISC76
    55   : ("SMBT", "A",  16, "decor"),  # MT_MISC44
    56   : ("SMGT", "A",  16, "decor"),  # MT_MISC45
    57   : ("SMRT", "A",  16, "decor"),  # MT_MISC46
    58   : ("SARG", "A",  30, "monsters"),  # MT_SHADOWS
    59   : ("GOR2", "A",  20, "decor"),  # MT_MISC56
    60   : ("GOR4", "A",  20, "decor"),  # MT_MISC57
    61   : ("GOR3", "A",  20, "decor"),  # MT_MISC58
    62   : ("GOR5", "A",  20, "decor"),  # MT_MISC59
    63   : ("GOR1", "A",  20, "decor"),  # MT_MISC60
    64   : ("VILE", "A",  20, "monsters"),  # MT_VILE
    65   : ("CPOS", "A",  20, "monsters"),  # MT_CHAINGUY
    66   : ("SKEL", "A",  20, "monsters"),  # MT_UNDEAD
    67   : ("FATT", "A",  48, "monsters"),  # MT_FATSO
    68   : ("BSPI", "A",  64, "monsters"),  # MT_BABY
    69   : ("BOS2", "A",  24, "monsters"),  # MT_KNIGHT
    70   : ("FCAN", "A",  16, "decor"),  # MT_MISC77
    71   : ("PAIN", "A",  31, "monsters"),  # MT_PAIN
    72   : ("KEEN", "A",  16, "monsters"),  # MT_KEEN
    73   : ("HDB1", "A",  16, "decor"),  # MT_MISC78
    74   : ("HDB2", "A",  16, "decor"),  # MT_MISC79
    75   : ("HDB3", "A",  16, "decor"),  # MT_MISC80
    76   : ("HDB4", "A",  16, "decor"),  # MT_MISC81
    77   : ("HDB5", "A",  16, "decor"),  # MT_MISC82
    78   : ("HDB6", "A",  16, "decor"),  # MT_MISC83
    79   : ("POB1", "A",  20, "decor"),  # MT_MISC84
    80   : ("POB2", "A",  20, "decor"),  # MT_MISC85
    81   : ("BRS1", "A",  20, "decor"),  # MT_MISC86
    82   : ("SGN2", "A",  20, "weapons"),  # MT_SUPERSHOTGUN
    83   : ("MEGA", "A",  20, "powerups"),  # MT_MEGA
    84   : ("SSWV", "A",  20, "monsters"),  # MT_WOLFSS
    85   : ("TLMP", "A",  16, "decor"),  # MT_MISC29
    86   : ("TLP2", "A",  16, "decor"),  # MT_MISC30
    88   : ("BBRN", "A",  16, "decor"),  # MT_BOSSBRAIN
    2001 : ("SHOT", "A",  20, "weapons"),  # MT_SHOTGUN
    2002 : ("MGUN", "A",  20, "weapons"),  # MT_CHAINGUN
    2003 : ("LAUN", "A",  20, "weapons"),  # MT_MISC27
    2004 : ("PLAS", "A",  20, "weapons"),  # MT_MISC28
    2005 : ("CSAW", "A",  20, "weapons"),  # MT_MISC26
    2006 : ("BFUG", "A",  20, "weapons"),  # MT_MISC25
    2007 : ("CLIP", "A",  20, "ammo"),  # MT_CLIP
    2008 : ("SHEL", "A",  20, "ammo"),  # MT_MISC22
    2010 : ("ROCK", "A",  20, "ammo"),  # MT_MISC18
    2011 : ("STIM", "A",  20, "health"),  # MT_MISC10
    2012 : ("MEDI", "A",  20, "health"),  # MT_MISC11
    2013 : ("SOUL", "A",  20, "powerups"),  # MT_MISC12
    2014 : ("BON1", "A",  20, "bonuses"),  # MT_MISC2
    2015 : ("BON2", "A",  20, "bonuses"),  # MT_MISC3
    2018 : ("ARM1", "A",  20, "armor"),  # MT_MISC0
    2019 : ("ARM2", "A",  20, "armor"),  # MT_MISC1
    2022 : ("PINV", "A",  20, "powerups"),  # MT_INV
    2023 : ("PSTR", "A",  20, "powerups"),  # MT_MISC13
    2024 : ("PINS", "A",  20, "powerups"),  # MT_INS
    2025 : ("SUIT", "A",  20, "powerups"),  # MT_MISC14
    2026 : ("PMAP", "A",  20, "powerups"),  # MT_MISC15
    2028 : ("COLU", "A",  16, "decor"),  # MT_MISC31
    2035 : ("BAR1", "A",  10, "decor"),  # MT_BARREL
    2045 : ("PVIS", "A",  20, "powerups"),  # MT_MISC16
    2046 : ("BROK", "A",  20, "ammo"),  # MT_MISC19
    2047 : ("CELL", "A",  20, "ammo"),  # MT_MISC20
    2048 : ("AMMO", "A",  20, "ammo"),  # MT_MISC17
    2049 : ("SBOX", "A",  20, "ammo"),  # MT_MISC23
    3001 : ("TROO", "A",  20, "monsters"),  # MT_TROOP
    3002 : ("SARG", "A",  30, "monsters"),  # MT_SERGEANT
    3003 : ("BOSS", "A",  24, "monsters"),  # MT_BRUISER
    3004 : ("POSS", "A",  20, "monsters"),  # MT_POSSESSED
    3005 : ("HEAD", "A",  31, "monsters"),  # MT_HEAD
    3006 : ("SKUL", "A",  16, "monsters"),  # MT_SKULL
}
THING_CATEGORIES = ["monsters", "weapons", "keys", "armor", "powerups",
                    "health", "bonuses", "ammo", "decor", "p1", "p2", "p3", "p4", "deathmatch"]
THING_DEFAULT_SET = ["monsters", "weapons", "keys", "armor", "powerups", "p1", "p2", "p3", "p4"]
THING_ALIASES = {"coop": ["p2", "p3", "p4"], "co-op": ["p2", "p3", "p4"], "dm": ["deathmatch"],
                 "starts": ["p1"], "player1": ["p1"]}
THING_INVISIBLE = {14, 87, 89}   # teleport destination, Icon of Sin spawn spot / shooter

REZ_PRESETS = {"480p": 854, "720p": 1280, "1080p": 1920, "4k": 3840, "8k": 7680, "16k": 15360}
REZ_LABELS  = {854: "480p", 1280: "720p", 1920: "1080p", 3840: "4K", 7680: "8K", 15360: "16K"}
MP4_MAX_WIDTH = 8192          # H.264 limit; wider needs -format png


def parse_rez(text, source):
    t = str(text).strip().lower()
    if t in REZ_PRESETS:
        w = REZ_PRESETS[t]
    else:
        try:
            w = int(t.rstrip("px"))
        except ValueError:
            die(f"{source}: '{text}' is not a resolution (use {', '.join(REZ_PRESETS)} or a width)")
        if w < 64:
            die(f"{source}: width must be at least 64")
    w -= w % 2
    h = int(round(w * 9 / 16))
    h -= h % 2
    return w, h


def rez_label(w, h):
    """Tag used in default output names: 480p 720p 1080p 4K 8K 16K, else WxH."""
    return REZ_LABELS.get(w, f"{w}x{h}")


WIDTH, HEIGHT = 1920, 1080    # set from RESOLUTION / -rez at startup


def die(msg):
    print(f"{C_ERR}ERROR:{C_RST} {msg}", file=sys.stderr)
    sys.exit(1)


def print_help():
    print(f"""
{C_HDR}timelapseMap{C_RST} - render a Doom map being drawn, as an mp4 timelapse

{C_HDR}USAGE{C_RST}
  {SCRIPT_NAME} {C_ARG}<wad>{C_RST} [{C_OPT}-m{C_RST} {C_ARG}MAP{C_RST}] [{C_OPT}-o{C_RST} {C_ARG}out.mp4{C_RST}] [{C_OPT}-iwad{C_RST} {C_ARG}alias|path{C_RST}] [{C_OPT}-drawspeed{C_RST} {C_ARG}N{C_RST}] [{C_OPT}-vidlength{C_RST} {C_ARG}T{C_RST}]
  {" " * len(SCRIPT_NAME)} [{C_OPT}-rez{C_RST} {C_ARG}R{C_RST}] [{C_OPT}-format{C_RST} {C_ARG}mp4|png{C_RST}] [{C_OPT}-linewidth{C_RST} {C_ARG}N{C_RST}]
  {" " * len(SCRIPT_NAME)} [{C_OPT}-cam{C_RST} {C_ARG}off|follow|trace|box [Z]{C_RST}] [{C_OPT}-zoom{C_RST} {C_ARG}Z{C_RST}] [{C_OPT}-testframe{C_RST} [{C_ARG}pos{C_RST}]]
  {" " * len(SCRIPT_NAME)} [{C_OPT}-endzoom{C_RST} {C_ARG}S{C_RST}] [{C_OPT}-endhold{C_RST} {C_ARG}S{C_RST}]
  {" " * len(SCRIPT_NAME)} [{C_OPT}-things{C_RST} [{C_ARG}img{C_RST}]] [{C_OPT}-thingtypes{C_RST} {C_ARG}LIST{C_RST}] [{C_OPT}-thingrate{C_RST} {C_ARG}N{C_RST}] [{C_OPT}-thingscale{C_RST} {C_ARG}N{C_RST}] [{C_OPT}-onlythings{C_RST}]
  {" " * len(SCRIPT_NAME)} [{C_OPT}-tracethings{C_RST}] [{C_OPT}-zoomthing{C_RST} {C_ARG}Z{C_RST}] [{C_OPT}-thingspeed{C_RST} {C_ARG}N{C_RST}]

{C_HDR}DESCRIPTION{C_RST}
  Draws every linedef in index order with a moving pen, as the IDDT
  automap using dsda/nyan automap colour rules (walls, height changes,
  key doors, teleports, exits, secret sectors). By default the whole map
  is shown, scaled once to fit the frame; -cam follow keeps the pen tip
  centred at a fixed zoom instead. Things are not drawn yet.
  Supports binary Doom / Boom / MBF21 format maps.

{C_HDR}OPTIONS{C_RST}
  {C_OPT}-m, --map{C_RST} {C_ARG}NAME{C_RST}     Map to render (default: first map in the WAD)
  {C_OPT}-o, --out{C_RST} {C_ARG}PATH{C_RST}     Output mp4 file, or folder for -format png
                     {C_DIM}(default, next to the WAD: <wad>_<MAP>_timelapse_<rez>.mp4
                     or <wad>_<MAP>_timelapse_<rez>_frames\\  e.g. ..._timelapse_4K.mp4){C_RST}
  {C_OPT}-rez{C_RST} {C_ARG}R{C_RST}             Resolution, always 16:9 (default: {RESOLUTION})
                     {C_ARG}480p 720p 1080p 4k 8k 16k{C_RST}, or a width e.g. {C_ARG}2560{C_RST}
  {C_OPT}-format{C_RST} {C_ARG}F{C_RST}          {C_ARG}mp4{C_RST} (H.264, up to {MP4_MAX_WIDTH} wide) or {C_ARG}png{C_RST} (numbered image
                     sequence, any size - use for 16k). Default: {OUTPUT_FORMAT}
  {C_OPT}-linewidth{C_RST} {C_ARG}N{C_RST}       Line thickness in pixels (default: {LINE_WIDTH})
  {C_OPT}-iwad, --iwad{C_RST} {C_ARG}X{C_RST}    IWAD to take PLAYPAL from: an alias or a path (default: {IWAD_DEFAULT})
                     {C_DIM}aliases: {", ".join(IWAD_ALIASES)}{C_RST}
                     {C_DIM}A PLAYPAL inside the input WAD always wins.{C_RST}
  {C_OPT}-drawspeed, --drawspeed{C_RST} {C_ARG}N{C_RST}
                     Pen speed in map units per second (default: {DRAW_SPEED:g})
                     {C_DIM}Lines are drawn from their start vertex to their end vertex at
                     this constant speed; leftover travel in a frame carries straight
                     into the next line.{C_RST}
  {C_OPT}-vidlength, --vidlength{C_RST} {C_ARG}T{C_RST}
                     Total video length. The video is planned with your settings, then
                     every speed, hold, pan and zoom is scaled by the same amount to fit -
                     like speeding a finished clip up or down in an editor
                     {C_DIM}20 = 20 seconds, 1.20 = 1 min 20 s, 2.5.0 = 2 h 5 min ("." or ":"){C_RST}
  {C_OPT}-timepreservezoom{C_RST}  with -vidlength: keep every zoom out / hold / zoom in, the mid
                     hold, the final zoom out and the start/end holds at their set
                     lengths; only drawing, thing placement and pans are scaled to fit
                     (error if the kept parts alone are longer than -vidlength)
  {C_OPT}-cam{C_RST} {C_ARG}MODE{C_RST}          {C_ARG}off{C_RST} = whole map (default: {CAM_MODE})
                     {C_ARG}steady{C_RST} = zoomed, lines in index (creation) order. The camera stays
                              still while the pen is mid-frame, glides after it near the
                              edges, and when the next line starts off-screen the pen
                              pauses while the camera pans there (-boxpan time)
                     {C_ARG}follow{C_RST} = like steady, but at an off-screen jump the pen keeps
                              drawing while the camera quickly catches up
                     {C_ARG}lock{C_RST}   = zoomed, index order, pen tip locked dead centre (cuts)
                     {C_ARG}trace{C_RST}  = like follow, but the pen walks connected lines (taking the
                              straightest way at junctions) and glides without drawing
                              across gaps - one continuous moving point
                     {C_ARG}box Z{C_RST}  = the map is cut into a grid of 16:9 boxes, Z wide (same forms
                              as -zoom: 6004mu, 15.5%, 4x; default: the -zoom value),
                              anchored on the
                              player 1 start. The camera frames one box (filling the frame),
                              trace-draws only what is inside it, then zooms out to the full
                              map, holds, and zooms into the next box (see -boxorder;
                              player 1's box first). Things go box by box too
  {C_OPT}-boxzoom{C_RST} {C_ARG}S{C_RST}         box: between boxes the camera zooms out to the full map, holds,
                     then zooms into the next box; seconds for each zoom (default: {BOX_ZOOM_SECONDS:g})
  {C_OPT}-boxhold{C_RST} {C_ARG}S{C_RST}         box: seconds on the full map between boxes (default: {BOX_HOLD_SECONDS:g})
                     {C_DIM}-boxzoom 0 = no zoom or hold: the camera pans straight to the next
                     box and drawing carries on (with -thingboxzoom 0 too, it also pans
                     straight from the lines to the things). Each box move is only as far
                     as needed to bring what is left in that box into view{C_RST}
  {C_OPT}-boxpan{C_RST} {C_ARG}S{C_RST}          seconds for that pan (default: {BOX_PAN_SECONDS:g})
  {C_OPT}-boxorder{C_RST} {C_ARG}O{C_RST}        box visiting order, for lines and things (default: {BOX_ORDER})
                     {C_ARG}sweep{C_RST}   step to a touching box each time, taking the one with the
                             fewest unfinished neighbours, so corners and edges are
                             cleared on the way and nothing is left behind
                     {C_ARG}spiral{C_RST}  ring by ring outwards from player 1's box
                     {C_ARG}dense{C_RST}   the densest box beside the last one, else the densest anywhere
  {C_OPT}-thingboxzoom{C_RST} {C_ARG}S{C_RST}    the same as -boxzoom / -boxhold, for the thing boxes
  {C_OPT}-thingboxhold{C_RST} {C_ARG}S{C_RST}    (default: the -boxzoom / -boxhold values; 0 zoom = pan)
  {C_OPT}-thingbox{C_RST} {C_ARG}Z{C_RST}        place the things box by box with this box size (same forms as
                     -zoom), in any camera mode (default in box mode: the line box size)
  {C_OPT}-midhold{C_RST} {C_ARG}S{C_RST}         with -things: seconds on the full map between the lines and
                     the things (default: {MID_HOLD_SECONDS:g}); the camera zooms out for it, and
                     back in afterwards if the things are placed zoomed
  {C_OPT}-jumptransition{C_RST} {C_ARG}N{C_RST}  trace/boxed: gap-glide speed as a multiple of the pen speed
                     (default: {JUMP_TRANSITION:g}; 4 = glide 4x faster than drawing)
  {C_OPT}-zoom{C_RST} {C_ARG}Z{C_RST}            follow/trace view size (alone, implies -cam follow). Default: {ZOOM}
                     {C_ARG}4096mu{C_RST}  4096 map units across the frame width
                     {C_ARG}15.5{C_RST}    15.5% of the full-map view (also {C_ARG}15.5%{C_RST})
                     {C_ARG}4x{C_RST}      4 times closer than the full-map view (= 25%)
  {C_OPT}-endzoom{C_RST} {C_ARG}S{C_RST}         follow/trace: seconds to zoom out to the full map when drawing
                     ends (default: {END_ZOOM_SECONDS:g}; 0 = cut straight to it)
  {C_OPT}-endhold{C_RST} {C_ARG}S{C_RST}         seconds to hold on the finished full map (default: {HOLD_END_SECONDS:g})
  {C_OPT}-things{C_RST} [{C_ARG}img{C_RST}]      Add a things pass after the map is drawn (in index order)
                     {C_DIM}no value = green triangles; img = the real front-facing sprites
                     (stock Doom 2 definitions; DEHACKED is not read yet){C_RST}
  {C_OPT}-thingtypes{C_RST} {C_ARG}LIST{C_RST}   Which things, comma separated (default: {THING_TYPES})
                     {C_ARG}monsters weapons keys armor powerups health bonuses ammo decor{C_RST}
                     {C_ARG}deathmatch{C_RST} {C_DIM}(deathmatch starts){C_RST}
                     {C_DIM}default = monsters,weapons,keys,armor,powerups   all = every category
                     Player 1-4 starts are always shown and placed first - only the start
                     that spawns the real player (extra copies = voodoo dolls are skipped)
                     e.g. default,health  or  monsters,keys{C_RST}
  {C_OPT}-skill{C_RST} {C_ARG}N{C_RST}           only things that appear on skill N, 1-5 (default: {THING_SKILL} = UV);
                     {C_DIM}multiplayer-only (co-op / deathmatch) things are never shown{C_RST}
  {C_OPT}-thingrate{C_RST} {C_ARG}N{C_RST}       things placed per second (default: {THING_RATE:g})
  {C_OPT}-thingscale{C_RST} {C_ARG}N{C_RST}      thing size multiplier, 1 = true size (default: {THING_SCALE:g});
                     {C_DIM}never smaller than {THING_MIN_PX}px on screen{C_RST}
  {C_OPT}-tracethings{C_RST}       follow/trace: stay zoomed in for the things - the pen travels from
                     thing to thing (follow: index order, trace: nearest next) and each one
                     appears as it is reached; then the zoom-out and hold. Without it,
                     things are placed on the full map after the zoom-out
  {C_OPT}-zoomthing{C_RST} {C_ARG}Z{C_RST}       zoom for the things only (same forms as -zoom); turns on
                     -tracethings, and works with -cam off and -onlythings too
  {C_OPT}-thingspeed{C_RST} {C_ARG}N{C_RST}      -tracethings pen speed, map units/s (default: same as -drawspeed)
  {C_OPT}-onlythings{C_RST}        Skip the line drawing: start on the finished full map and just add
                     the things, then hold (implies -things). -vidlength sets the thing rate.
                     With -tracethings and -cam follow/trace: zoom in from the full map,
                     trace the things at -zoom, then zoom out and hold
  {C_OPT}-testframe{C_RST} [{C_ARG}POS{C_RST}]   Render ONE frame to a PNG and exit - fast, for checking settings
                     {C_DIM}no value = middle of the drawing, 30% = 30% through the drawing,
                     0.45 = that time into the video (s, m.s or h.m.s){C_RST}
  {C_OPT}-h, --help{C_RST}         Show this help

{C_HDR}SETTINGS{C_RST}
  {C_DIM}Resolution, fps, pacing, line width, colours and the IWAD alias table are edited
  at the very top of timelapseMap_script.py.{C_RST}

{C_HDR}LOG{C_RST}
  Every output gets a .log beside it with the same name (e.g. ..._1080p.mp4 -> ..._1080p.log)
  holding the date, folder, exact command line and the console summary.

{C_HDR}WHILE RENDERING{C_RST}
  Press {C_OPT}S{C_RST} to stop and save what has been rendered so far (playable mp4 / PNGs kept).
  {C_DIM}Ctrl+C aborts and deletes the unfinished mp4.{C_RST}

{C_HDR}REQUIRES{C_RST}
  ffmpeg on PATH

{C_HDR}EXAMPLES{C_RST}
  {SCRIPT_NAME} mymap.wad
  {SCRIPT_NAME} mymap.wad {C_OPT}-m{C_RST} MAP03
  {SCRIPT_NAME} megawad.wad {C_OPT}-m{C_RST} MAP12 {C_OPT}-o{C_RST} map12.mp4
  {SCRIPT_NAME} mymap.wad {C_OPT}-iwad{C_RST} tnt
  {SCRIPT_NAME} mymap.wad {C_OPT}-drawspeed{C_RST} 6000
  {SCRIPT_NAME} mymap.wad {C_OPT}-vidlength{C_RST} 1.20
  {SCRIPT_NAME} mymap.wad {C_OPT}-rez{C_RST} 4k
  {SCRIPT_NAME} bigmap.wad {C_OPT}-rez{C_RST} 16k {C_OPT}-format{C_RST} png {C_OPT}-linewidth{C_RST} 5
  {SCRIPT_NAME} mymap.wad {C_OPT}-iwad{C_RST} "D:\\stuff\\other.wad"
  {SCRIPT_NAME} mymap.wad {C_OPT}-zoom{C_RST} 4x
  {SCRIPT_NAME} mymap.wad {C_OPT}-cam{C_RST} follow {C_OPT}-zoom{C_RST} 2048mu {C_OPT}-drawspeed{C_RST} 800
  {SCRIPT_NAME} mymap.wad {C_OPT}-rez{C_RST} 8k {C_OPT}-zoom{C_RST} 4x {C_OPT}-testframe{C_RST}
  {SCRIPT_NAME} mymap.wad {C_OPT}-zoom{C_RST} 15.5 {C_OPT}-testframe{C_RST} 30%
  {SCRIPT_NAME} mymap.wad {C_OPT}-cam{C_RST} trace {C_OPT}-zoom{C_RST} 4x {C_OPT}-drawspeed{C_RST} 800 {C_OPT}-jumptransition{C_RST} 3
  {SCRIPT_NAME} mymap.wad {C_OPT}-cam{C_RST} box 6004mu {C_OPT}-things{C_RST} img {C_OPT}-thingscale{C_RST} 3.2
  {SCRIPT_NAME} mymap.wad {C_OPT}-things{C_RST}
  {SCRIPT_NAME} mymap.wad {C_OPT}-things{C_RST} img {C_OPT}-thingtypes{C_RST} default,health {C_OPT}-thingscale{C_RST} 2
  {SCRIPT_NAME} mymap.wad {C_OPT}-things{C_RST} img {C_OPT}-onlythings{C_RST} {C_OPT}-vidlength{C_RST} 20
  {SCRIPT_NAME} mymap.wad {C_OPT}-cam{C_RST} trace {C_OPT}-zoom{C_RST} 3x {C_OPT}-things{C_RST} img {C_OPT}-tracethings{C_RST} {C_OPT}-thingspeed{C_RST} 1500
""")


VALUE_FLAGS = {"m": "map", "map": "map", "o": "out", "out": "out", "iwad": "iwad",
               "drawspeed": "drawspeed", "vidlength": "vidlength",
               "rez": "rez", "format": "format", "linewidth": "linewidth",
               "cam": "cam", "zoom": "zoom", "jumptransition": "jumptransition",
               "endzoom": "endzoom", "endhold": "endhold",
               "thingtypes": "thingtypes", "thingrate": "thingrate", "thingscale": "thingscale",
               "thingspeed": "thingspeed", "skill": "skill", "zoomthing": "zoomthing",
               "box": "box", "boxzoom": "boxzoom", "boxhold": "boxhold", "midhold": "midhold",
               "boxpan": "boxpan", "thingboxzoom": "thingboxzoom", "thingboxhold": "thingboxhold",
               "boxorder": "boxorder",
               "thingbox": "thingbox"}

ZOOM_VALUE = re.compile(r"^\d+(\.\d+)?(mu|x|%)?$", re.I)
TESTFRAME_VALUE = re.compile(r"^(\d+(\.\d+)?%|\d+([.:]\d+){0,2})$")


def parse_args(argv):
    args = {k: None for k in set(VALUE_FLAGS.values())}
    args["wad"] = None
    args["testframe"] = None
    args["things"] = None
    args["onlythings"] = False
    args["tracethings"] = False
    args["timepreservezoom"] = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help", "/?"):
            print_help()
            sys.exit(0)
        elif a.lower() in ("-cam", "--cam"):
            # -cam MODE, and for box mode an optional size straight after: -cam box 6004mu
            if i + 1 >= len(argv):
                die(f"{a} needs a value")
            args["cam"] = argv[i + 1]
            i += 2
            if args["cam"].lower() in ("box", "boxed") and i < len(argv) and ZOOM_VALUE.match(argv[i]):
                args["box"] = argv[i]
                i += 1
            continue
        elif a.lower() in ("-timepreservezoom", "--timepreservezoom"):
            args["timepreservezoom"] = True
            i += 1
            continue
        elif a.lower() in ("-tracethings", "--tracethings"):
            args["tracethings"] = True
            i += 1
            continue
        elif a.lower() in ("-onlythings", "--onlythings"):
            args["onlythings"] = True
            i += 1
            continue
        elif a.lower() in ("-things", "--things"):
            # optional value: img / tri / off
            if i + 1 < len(argv) and argv[i + 1].lower() in ("img", "tri", "triangles", "off"):
                args["things"] = argv[i + 1].lower()
                i += 2
            else:
                args["things"] = "tri"
                i += 1
            continue
        elif a.lower() in ("-testframe", "--testframe"):
            # optional value: only taken if it looks like 30% or a time
            if i + 1 < len(argv) and TESTFRAME_VALUE.match(argv[i + 1]):
                args["testframe"] = argv[i + 1]
                i += 2
            else:
                args["testframe"] = "50%"
                i += 1
            continue
        elif a.lower().lstrip("-") in VALUE_FLAGS and a.startswith("-"):
            if i + 1 >= len(argv):
                die(f"{a} needs a value")
            key = VALUE_FLAGS[a.lower().lstrip("-")]
            args[key] = argv[i + 1]
            i += 2
            continue
        elif a.startswith("-"):
            die(f"unknown option '{a}' (use -h for help)")
        else:
            if args["wad"]:
                die(f"unexpected extra argument '{a}'")
            args["wad"] = a
        i += 1
    if not args["wad"]:
        print_help()
        sys.exit(1)
    raw_given = {k: args[k] is not None for k in ("cam", "zoom", "drawspeed", "endzoom", "jumptransition", "box")}
    raw_tracethings = bool(args["tracethings"])
    raw_zoomthing = args["zoomthing"] is not None
    if args["drawspeed"] is not None:
        try:
            args["drawspeed"] = float(args["drawspeed"])
        except ValueError:
            die(f"-drawspeed needs a number, got '{args['drawspeed']}'")
        if args["drawspeed"] <= 0:
            die("-drawspeed must be greater than 0")
    if args["vidlength"] is not None:
        args["vidlength"] = parse_length(args["vidlength"], "-vidlength")
    # output
    global WIDTH, HEIGHT, LINE_WIDTH
    if args["rez"] is not None:
        WIDTH, HEIGHT = parse_rez(args["rez"], "-rez")
    else:
        WIDTH, HEIGHT = parse_rez(RESOLUTION, "RESOLUTION")
    fmt = (args["format"] or OUTPUT_FORMAT).strip().lower()
    if fmt not in ("mp4", "png"):
        die(f"unknown format '{fmt}' (use mp4 or png)")
    if fmt == "mp4" and WIDTH > MP4_MAX_WIDTH and not args["testframe"]:
        die(f"{WIDTH}x{HEIGHT} is too wide for mp4 (H.264 max {MP4_MAX_WIDTH}); use -format png")
    args["format"] = fmt
    if args["linewidth"] is not None:
        try:
            LINE_WIDTH = int(args["linewidth"])
        except ValueError:
            die(f"-linewidth needs a whole number, got '{args['linewidth']}'")
        if LINE_WIDTH < 1:
            die("-linewidth must be at least 1")

    # camera: -zoom implies follow unless -cam was given
    cam = (args["cam"] or "").strip().lower()
    cam = "boxed" if cam == "box" else cam
    if cam and cam not in ("off", "follow", "steady", "lock", "trace", "boxed"):
        die(f"unknown camera mode '{cam}' (use off, steady, follow, lock, trace or box)")
    if not cam:
        cam = "follow" if args["zoom"] is not None else CAM_MODE.strip().lower()
    elif cam == "off" and args["zoom"] is not None and not args["onlythings"]:
        print(f"{C_ERR}WARNING:{C_RST} -zoom is ignored with -cam off")
    if cam not in ("off", "follow", "steady", "lock", "trace", "boxed"):
        die(f"CAM_MODE must be off, steady, follow, lock, trace or boxed, not '{cam}'")
    args["cam"] = cam
    jt = args["jumptransition"] if args["jumptransition"] is not None else JUMP_TRANSITION
    try:
        jt = float(jt)
    except ValueError:
        die(f"-jumptransition needs a number, got '{jt}'")
    if jt <= 0:
        die("-jumptransition must be greater than 0")
    if args["jumptransition"] is not None and cam not in ("trace", "boxed") and not args["onlythings"]:
        print(f"{C_ERR}WARNING:{C_RST} -jumptransition only applies to -cam trace / boxed")
    args["jumptransition"] = jt

    global END_ZOOM_SECONDS, HOLD_END_SECONDS
    for key in ("endzoom", "endhold"):
        if args[key] is None:
            continue
        try:
            v = float(args[key])
        except ValueError:
            die(f"-{key} needs a number of seconds, got '{args[key]}'")
        if v < 0:
            die(f"-{key} cannot be negative")
        if key == "endzoom":
            END_ZOOM_SECONDS = v
        else:
            HOLD_END_SECONDS = v
    if (args["endzoom"] is not None and cam == "off" and not args["onlythings"]
            and (args["things"] or THINGS) == "off"):
        print(f"{C_ERR}WARNING:{C_RST} -endzoom only applies to -cam follow / trace")

    # things pass
    mode = (args["things"] or THINGS).strip().lower()
    mode = {"triangles": "tri"}.get(mode, mode)
    if mode not in ("off", "tri", "img"):
        die(f"THINGS must be off, tri or img, not '{mode}'")
    args["things"] = mode
    cats = []
    for part in str(args["thingtypes"] or THING_TYPES).lower().replace(" ", "").split(","):
        if not part:
            continue
        if part == "all":
            cats += THING_CATEGORIES + ["unknown"]
        elif part == "default":
            cats += THING_DEFAULT_SET
        elif part in THING_CATEGORIES:
            cats.append(part)
        elif part in THING_ALIASES:
            cats += THING_ALIASES[part]
        else:
            die(f"unknown thing type '{part}' (use {', '.join(c for c in THING_CATEGORIES if c != 'p1')}, "
                f"coop, default or all)")
    cats += ["p1", "p2", "p3", "p4"]                      # player 1-4 starts are always shown
    thing_types_given = args["thingtypes"] is not None
    args["thingtypes"] = list(dict.fromkeys(cats))
    global THING_RATE, THING_SCALE, THING_SKILL
    if args["skill"] is not None:
        try:
            THING_SKILL = int(args["skill"])
        except ValueError:
            die(f"-skill needs a whole number 1-5, got '{args['skill']}'")
    if not 1 <= int(THING_SKILL) <= 5:
        die(f"skill must be 1-5, not {THING_SKILL}")
    for key in ("thingrate", "thingscale"):
        if args[key] is None:
            continue
        try:
            v = float(args[key])
        except ValueError:
            die(f"-{key} needs a number, got '{args[key]}'")
        if v <= 0:
            die(f"-{key} must be greater than 0")
        if key == "thingrate":
            THING_RATE = v
        else:
            THING_SCALE = v
    if args["onlythings"]:
        if mode == "off":
            args["things"] = mode = "tri"                 # -onlythings implies -things
        # with -tracethings and a follow/trace camera, the things are traced at the zoom;
        # otherwise the camera stays on the full map and things appear at -thingrate
        zt_given = (args["zoomthing"] is not None or str(THING_ZOOM).strip() != ""
                    or args["thingbox"] is not None or str(THING_BOX).strip() != "")
        only_traced = ((bool(args["tracethings"] or THING_TRACE)
                        and args["cam"] in ("follow", "steady", "lock", "trace"))
                       or zt_given or args["cam"] == "boxed")
        if only_traced:
            ignored = ["-jumptransition"] if raw_given.get("jumptransition") else []
        else:
            ignored = [f"-{k}" for k in ("cam", "zoom", "drawspeed", "endzoom") if raw_given.get(k)]
            if raw_given.get("jumptransition"):
                ignored.append("-jumptransition")
        if not (args["cam"] in ("follow", "steady", "lock", "trace", "boxed") and only_traced):
            args["cam"] = "off"
        if ignored:
            print(f"{C_DIM}note: -onlythings ignores {', '.join(ignored)}"
                  f"{'' if only_traced else ' (add -tracethings to trace the things at the zoom)'}{C_RST}")
    if mode == "off" and (thing_types_given or any(args[k] is not None for k in ("thingrate", "thingscale"))):
        print(f"{C_ERR}WARNING:{C_RST} thing options are ignored without -things")

    # -tracethings / -zoomthing / -thingspeed
    zt_text = args["zoomthing"] if args["zoomthing"] is not None else str(THING_ZOOM).strip()
    args["zoomthing"] = parse_zoom(zt_text, "-zoomthing") if zt_text else None
    tr = bool(args["tracethings"] or THING_TRACE) or args["zoomthing"] is not None
    if tr and mode == "off" and not args["onlythings"]:
        print(f"{C_ERR}WARNING:{C_RST} -tracethings / -zoomthing are ignored (no -things)")
    if args["tracethings"] and args["zoomthing"] is None and args["cam"] == "off" and not args["onlythings"]:
        print(f"{C_ERR}WARNING:{C_RST} -tracethings is ignored with -cam off (use -zoomthing to set a zoom)")
    args["tracethings"] = tr and mode != "off" and (args["cam"] != "off" or args["zoomthing"] is not None)
    ts = args["thingspeed"] if args["thingspeed"] is not None else THING_SPEED
    try:
        ts = float(ts)
    except ValueError:
        die(f"-thingspeed needs a number, got '{ts}'")
    if ts < 0 or (args["thingspeed"] is not None and ts == 0):
        die("-thingspeed must be greater than 0")
    boxed_thing_pass = (cam == "boxed" or args["thingbox"] is not None
                        or str(THING_BOX).strip() != "")
    if (args["thingspeed"] is not None and not args["tracethings"] and not boxed_thing_pass) \
            or (args["thingspeed"] is not None and mode == "off"):
        print(f"{C_ERR}WARNING:{C_RST} -thingspeed only applies when things are traced or placed "
              f"box by box (-tracethings, -zoomthing, -thingbox or -cam box)")
    args["thingspeed"] = ts if ts > 0 else None
    if args["tracethings"] and args["thingrate"] is not None:
        print(f"{C_ERR}WARNING:{C_RST} -thingrate is ignored with -tracethings (use -thingspeed)")
    args["zoom"] = parse_zoom(args["zoom"] if args["zoom"] is not None else ZOOM,
                              "-zoom" if args["zoom"] is not None else "ZOOM")
    bx_text = args["box"] if args["box"] is not None else str(BOX).strip()
    args["box"] = parse_zoom(bx_text, "-box") if bx_text else args["zoom"]
    if args["box"] is not None and raw_given.get("box") and cam != "boxed":
        print(f"{C_ERR}WARNING:{C_RST} -box only applies to -cam boxed")
    if cam == "boxed" and (raw_tracethings or raw_zoomthing):
        which = " / ".join(k for k, v in (("-tracethings", raw_tracethings), ("-zoomthing", raw_zoomthing)) if v)
        print(f"{C_ERR}WARNING:{C_RST} {which} ignored in box mode - things are placed box by box; "
              f"use -thingbox to set the thing box size")
    global BOX_ZOOM_SECONDS, BOX_HOLD_SECONDS, MID_HOLD_SECONDS, BOX_PAN_SECONDS
    global THING_BOX_ZOOM_SECONDS, THING_BOX_HOLD_SECONDS
    for key in ("boxzoom", "boxhold", "midhold", "boxpan", "thingboxzoom", "thingboxhold"):
        if args[key] is None:
            continue
        try:
            v = float(args[key])
        except ValueError:
            die(f"-{key} needs a number of seconds, got '{args[key]}'")
        if v < 0:
            die(f"-{key} cannot be negative")
        if key == "boxzoom":
            BOX_ZOOM_SECONDS = v
        elif key == "boxhold":
            BOX_HOLD_SECONDS = v
        elif key == "boxpan":
            BOX_PAN_SECONDS = v
        elif key == "thingboxzoom":
            THING_BOX_ZOOM_SECONDS = v
        elif key == "thingboxhold":
            THING_BOX_HOLD_SECONDS = v
        else:
            MID_HOLD_SECONDS = v
    if THING_BOX_ZOOM_SECONDS == "":
        THING_BOX_ZOOM_SECONDS = BOX_ZOOM_SECONDS
    if THING_BOX_HOLD_SECONDS == "":
        THING_BOX_HOLD_SECONDS = BOX_HOLD_SECONDS
    bo = str(args["boxorder"] or BOX_ORDER).strip().lower()
    if bo not in ("sweep", "spiral", "dense"):
        die(f"unknown box order '{bo}' (use sweep, spiral or dense)")
    args["boxorder"] = bo
    tb_text = args["thingbox"] if args["thingbox"] is not None else str(THING_BOX).strip()
    args["thingbox"] = parse_zoom(tb_text, "-thingbox") if tb_text else None
    if args["thingbox"] is not None:
        if (args["things"] or "off") == "off":
            print(f"{C_ERR}WARNING:{C_RST} -thingbox is ignored (no -things)")
        elif args["zoomthing"] is not None:
            print(f"{C_DIM}note: -thingbox is used for the things; -zoomthing is ignored{C_RST}")
    return args


def parse_zoom(text, source):
    """Returns ("mu", units) | ("pct", percent) . 'x' is converted to a percent."""
    t = str(text).strip().lower()
    try:
        if t.endswith("mu"):
            v = float(t[:-2])
            if v <= 0:
                die(f"{source}: map units must be greater than 0")
            return ("mu", v)
        if t.endswith("x"):
            v = float(t[:-1])
            if v < 1:
                die(f"{source}: '{text}' would zoom out past the full map (use 1x or more)")
            return ("pct", 100.0 / v)
        v = float(t.rstrip("%"))
    except ValueError:
        die(f"{source}: '{text}' is not a zoom (use e.g. 4096mu, 15.5, 15.5% or 4x)")
    if not 0 < v <= 100:
        die(f"{source}: '{text}' must be above 0% and at most 100%")
    return ("pct", v)


def parse_length(text, source):
    """20 = 20s, 1.20 = 1m20s, 2.5.0 = 2h5m0s. '.' or ':' separators. Returns seconds."""
    t = str(text).strip().replace(":", ".")
    parts = t.split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        die(f"{source}: '{text}' is not a valid length (use s, m.s or h.m.s, e.g. 20, 1.20, 2.5.0)")
    nums = [int(p) for p in parts]
    for n in nums[1:]:
        if n >= 60:
            die(f"{source}: '{text}' has a minutes/seconds part of 60 or more")
    secs = 0
    for n in nums:
        secs = secs * 60 + n
    if secs <= 0:
        die(f"{source}: length must be greater than 0")
    return secs


# -------------------------------------------------------------------- wad ---
class Wad:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        if len(self.data) < 12:
            die(f"'{path}' is too small to be a WAD")
        ident, count, offset = struct.unpack_from("<4sii", self.data, 0)
        if ident not in (b"IWAD", b"PWAD"):
            die(f"'{path}' is not a WAD file")
        self.lumps = []
        for i in range(count):
            pos, size, name = struct.unpack_from("<ii8s", self.data, offset + i * 16)
            name = name.split(b"\0", 1)[0].decode("ascii", "replace").upper()
            self.lumps.append((name, pos, size))

    def lump_bytes(self, index):
        _, pos, size = self.lumps[index]
        return self.data[pos:pos + size]

    def find(self, name):
        name = name.upper()
        for i in range(len(self.lumps) - 1, -1, -1):
            if self.lumps[i][0] == name:
                return i
        return -1

    def map_names(self):
        out = []
        for i in range(len(self.lumps) - 1):
            nxt = self.lumps[i + 1][0]
            if nxt in ("THINGS", "TEXTMAP"):
                out.append(self.lumps[i][0])
        return out

    def map_lumps(self, mapname):
        mapname = mapname.upper()
        idx = -1
        for i in range(len(self.lumps) - 1):
            if self.lumps[i][0] == mapname and self.lumps[i + 1][0] in ("THINGS", "TEXTMAP"):
                idx = i
                break
        if idx < 0:
            return None
        known = {"THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS", "SSECTORS",
                 "NODES", "SECTORS", "REJECT", "BLOCKMAP", "BEHAVIOR", "SCRIPTS",
                 "TEXTMAP", "ZNODES", "DIALOGUE", "ENDMAP", "LEAFS", "LIGHTS", "MACROS",
                 "GL_VERT", "GL_SEGS", "GL_SSECT", "GL_NODES", "GL_PVS"}
        res = {}
        for j in range(idx + 1, len(self.lumps)):
            nm = self.lumps[j][0]
            if nm not in known and not nm.startswith("GL_"):
                break
            res[nm] = self.lump_bytes(j)
            if nm == "ENDMAP":
                break
        return res


# ---------------------------------------------------------------- palette ---
def resolve_iwad(iwad_override):
    choice = iwad_override or IWAD_DEFAULT
    alias = choice.lower()
    if alias in IWAD_ALIASES:
        path = IWAD_ALIASES[alias]
        if not os.path.isfile(path):
            die(f"IWAD alias '{alias}' points to a missing file: '{path}' "
                f"(edit IWAD_ALIASES at the top of the script)")
        return path
    if os.path.isfile(choice):
        return choice
    die(f"'{choice}' is not an IWAD alias or an existing file. "
        f"Aliases: {', '.join(IWAD_ALIASES)}")


def load_palette(pwad, iwad_override):
    i = pwad.find("PLAYPAL")
    if i >= 0:
        src = "PWAD"
        raw = pwad.lump_bytes(i)
    else:
        path = resolve_iwad(iwad_override)
        iw = Wad(path)
        j = iw.find("PLAYPAL")
        if j < 0:
            die(f"no PLAYPAL lump in '{path}'")
        src = path
        raw = iw.lump_bytes(j)
    if len(raw) < 768:
        die("PLAYPAL lump is too short")
    pal = [bytes(raw[k * 3:k * 3 + 3]) for k in range(256)]
    return pal, src


# -------------------------------------------------------------------- map ---
def read_map(lumps, mapname):
    if "TEXTMAP" in lumps:
        die(f"{mapname} is UDMF; only binary Doom/Boom/MBF21 maps are supported for now")
    if "BEHAVIOR" in lumps:
        die(f"{mapname} is Hexen format; only binary Doom/Boom/MBF21 maps are supported for now")
    for need in ("THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SECTORS"):
        if need not in lumps:
            die(f"{mapname} is missing its {need} lump")

    vx = lumps["VERTEXES"]
    verts = [struct.unpack_from("<hh", vx, k) for k in range(0, len(vx) - 3, 4)]

    sc = lumps["SECTORS"]
    sectors = []
    for k in range(0, len(sc) - 25, 26):
        fl, ce = struct.unpack_from("<hh", sc, k)
        sp = struct.unpack_from("<H", sc, k + 22)[0]
        sectors.append((fl, ce, sp))                      # floor, ceiling, special

    sd = lumps["SIDEDEFS"]
    side_sector = [struct.unpack_from("<h", sd, k + 28)[0] for k in range(0, len(sd) - 29, 30)]

    ld = lumps["LINEDEFS"]
    lines = []
    for k in range(0, len(ld) - 13, 14):
        v1, v2, flags, special, tag, s1, s2 = struct.unpack_from("<HHHHHHH", ld, k)
        lines.append((v1, v2, flags, special, s1, s2))

    th = lumps["THINGS"]
    things = []
    for k in range(0, len(th) - 9, 10):
        x, y, ang, typ, fl = struct.unpack_from("<hhhhh", th, k)
        things.append((x, y, ang, typ, fl))

    return verts, sectors, side_sector, lines, things


EXIT_NORMAL  = {11, 52, 197}
EXIT_SECRET  = {51, 124, 198}
TELEPORTS    = {39, 97, 125, 126, 174, 195, 207, 208, 209, 210, 243, 244,
                262, 263, 264, 265, 266, 267, 268, 269}
DOOR_RED     = {28, 33, 134, 135}
DOOR_BLUE    = {26, 32, 99, 133}
DOOR_YELLOW  = {27, 34, 136, 137}


def key_door_colour(special):
    """Key door colour for vanilla and Boom generalized locked doors, or 0."""
    if special in DOOR_RED:
        return mapcolor_rdor
    if special in DOOR_BLUE:
        return mapcolor_bdor
    if special in DOOR_YELLOW:
        return mapcolor_ydor
    if 0x3800 <= special < 0x3C00:          # Boom generalized locked door
        key = (special & 0x01C0) >> 6
        if key in (1, 4):
            return mapcolor_rdor
        if key in (2, 5):
            return mapcolor_bdor
        if key in (3, 6):
            return mapcolor_ydor
    return 0


def is_secret_sector(sec):
    special = sec[2]
    return special == 9 or bool(special & 0x80)   # vanilla 9, or Boom secret bit


def line_colour(line, sectors, side_sector):
    """dsda/nyan automap rules, IDDT on. Returns a palette index, or None = not drawn."""
    v1, v2, flags, special, s1, s2 = line
    ML_SECRET = 0x20

    def sec_of(s):
        if s == 0xFFFF or s >= len(side_sector):
            return None
        si = side_sector[s]
        return sectors[si] if 0 <= si < len(sectors) else None

    front = sec_of(s1)
    back = sec_of(s2)
    if front is None and back is None:
        return None
    if front is None:
        front, back = back, None

    # exits
    if special in EXIT_SECRET and mapcolor_exitsecr:
        return mapcolor_exitsecr
    if special in EXIT_NORMAL and mapcolor_exit:
        return mapcolor_exit

    # key doors
    kc = key_door_colour(special)
    if kc:
        return kc

    # one-sided
    if back is None:
        if mapcolor_secr and is_secret_sector(front):
            return mapcolor_secr
        return mapcolor_wall or None

    # two-sided
    if mapcolor_tele and not (flags & ML_SECRET) and special in TELEPORTS:
        return mapcolor_tele
    if flags & ML_SECRET:
        return mapcolor_wall or None
    if mapcolor_clsd and (front[0] >= front[1] or back[0] >= back[1]):
        return mapcolor_clsd
    if mapcolor_secr and (is_secret_sector(front) or is_secret_sector(back)):
        return mapcolor_secr
    if front[0] != back[0] and mapcolor_fchg:
        return mapcolor_fchg
    if front[1] != back[1] and mapcolor_cchg:
        return mapcolor_cchg
    if mapcolor_flat:
        return mapcolor_flat
    return None


# ----------------------------------------------------------------- raster ---
class Canvas:
    """One RGB frame (a Pillow image). Lines and sprites are drawn onto it, then it is
    streamed to ffmpeg each frame. Lines use the same square brush as before: a w x w block
    stamped along a 1-pixel Bresenham line, drawn here as w*w offset 1-pixel lines in C."""

    def __init__(self, w, h, bg, keep_blank=False):
        self.w, self.h = w, h
        self.bg = tuple(bg)
        self.im = Image.new("RGB", (w, h), self.bg)
        self.dr = ImageDraw.Draw(self.im)
        self.lw = max(1, int(LINE_WIDTH))
        self.half = (self.lw - 1) // 2
        self.offsets = [(ox, oy) for oy in range(-self.half, self.lw - self.half)
                        for ox in range(-self.half, self.lw - self.half)]

    @property
    def buf(self):
        return self.im.tobytes()

    def clear(self):
        self.im.paste(self.bg, (0, 0, self.w, self.h))

    def polyline(self, pts, rgb):
        """Connected on-screen points (already rounded) in one call per brush offset."""
        line = self.dr.line
        col = rgb if isinstance(rgb, tuple) else tuple(rgb)
        if len(self.offsets) == 1:
            line(pts, fill=col)
            return
        for ox, oy in self.offsets:
            line([(x + ox, y + oy) for x, y in pts], fill=col)

    def paste(self, sprite, x0, y0):
        """Draw a pre-scaled RGBA sprite with its top-left at (x0, y0); clipped by Pillow."""
        self.im.paste(sprite, (x0, y0), sprite)

    def _clip(self, x0, y0, x1, y1):
        """Liang-Barsky clip to the frame (plus line width). None if fully outside."""
        m = self.lw + 1
        xmin, ymin, xmax, ymax = -m, -m, self.w + m, self.h + m
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
            if p == 0:
                if q < 0:
                    return None
            else:
                r = q / p
                if p < 0:
                    if r > t1:
                        return None
                    if r > t0:
                        t0 = r
                else:
                    if r < t0:
                        return None
                    if r < t1:
                        t1 = r
        return x0 + dx * t0, y0 + dy * t0, x0 + dx * t1, y0 + dy * t1

    def plot_line(self, x0, y0, x1, y1, rgb):
        w, h = self.w, self.h
        if not (0 <= x0 < w and 0 <= x1 < w and 0 <= y0 < h and 0 <= y1 < h):
            c = self._clip(x0, y0, x1, y1)                # only lines reaching off-frame
            if c is None:
                return
            x0, y0, x1, y1 = c
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        line = self.dr.line
        col = rgb if isinstance(rgb, tuple) else tuple(rgb)
        for ox, oy in self.offsets:
            line((x0 + ox, y0 + oy, x1 + ox, y1 + oy), fill=col)


class Grid:
    """Spatial hash of line indices, so a follow-mode redraw only visits nearby lines."""
    CELL = 512

    def __init__(self, lines):
        self.cells = {}
        c = self.CELL
        for i, (ax, ay, bx, by, *_r) in enumerate(lines):
            for gx in range(int(min(ax, bx) // c), int(max(ax, bx) // c) + 1):
                for gy in range(int(min(ay, by) // c), int(max(ay, by) // c) + 1):
                    self.cells.setdefault((gx, gy), []).append(i)

    def query(self, view):
        cx, cy, vw = view
        vh = vw * HEIGHT / WIDTH
        c = self.CELL
        gx0, gx1 = int((cx - vw / 2) // c), int((cx + vw / 2) // c)
        gy0, gy1 = int((cy - vh / 2) // c), int((cy + vh / 2) // c)
        out = set()
        if (gx1 - gx0 + 1) * (gy1 - gy0 + 1) > len(self.cells):
            for lst in self.cells.values():
                out.update(lst)
        else:
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    lst = self.cells.get((gx, gy))
                    if lst:
                        out.update(lst)
        return out


def lerp_view(a, b, t):
    """Eased move between two views: centre slides, zoom changes evenly (log scale)."""
    e = t * t * (3 - 2 * t)                               # smoothstep
    w = math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * e)
    return (a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e, w)


# ---------------------------------------------------------------- sprites ---
def sprite_lumps(wad):
    """name -> lump index for lumps inside S_START/S_END (or SS_START/SS_END)."""
    out = {}
    inside = False
    for i, (nm, _pos, size) in enumerate(wad.lumps):
        if nm in ("S_START", "SS_START"):
            inside = True
        elif nm in ("S_END", "SS_END"):
            inside = False
        elif inside and size > 0:
            out[nm] = i
    return out


def decode_patch(data):
    """Doom patch -> (w, h, rows) with rows[y][x] = palette index or -1 (transparent)."""
    if len(data) < 8:
        return None
    w, h = struct.unpack_from("<hh", data, 0)
    if w <= 0 or h <= 0 or w > 4096 or h > 4096 or len(data) < 8 + 4 * w:
        return None
    img = [[-1] * w for _ in range(h)]
    for x in range(w):
        off = struct.unpack_from("<I", data, 8 + 4 * x)[0]
        top = -1
        while 0 <= off < len(data):
            delta = data[off]
            if delta == 0xFF:
                break
            top = top + delta if delta <= top else delta       # tall-patch aware
            length = data[off + 1] if off + 1 < len(data) else 0
            for k in range(length):
                y = top + k
                if 0 <= y < h and off + 3 + k < len(data):
                    img[y][x] = data[off + 3 + k]
            off += length + 4
    return w, h, img


class Sprites:
    """Finds front-facing spawn sprites (PWAD first, then IWAD) and scales them, cached."""

    def __init__(self, pwad, iwad, pal):
        self.srcs = [(pwad, sprite_lumps(pwad))]
        if iwad is not None:
            self.srcs.append((iwad, sprite_lumps(iwad)))
        self.pal = pal
        self.found = {}
        self.scaled = {}

    def get(self, spr, frame):
        """(w, h, img, flip) for sprite+frame rotation 1 (or 0), or None."""
        key = (spr, frame)
        if key in self.found:
            return self.found[key]
        res = None
        for wad, names in self.srcs:
            hit = None
            for cand in (spr + frame + "1", spr + frame + "0"):
                if cand in names:
                    hit = (names[cand], False)
                    break
            if hit is None:
                for nm, idx in names.items():
                    if len(nm) == 8 and nm[:4] == spr:
                        if nm[4] == frame and nm[5] == "1":
                            hit = (idx, False)
                            break
                        if nm[6] == frame and nm[7] == "1":
                            hit = (idx, True)            # mirrored half of a paired lump
                            break
            if hit is not None:
                dec = decode_patch(wad.lump_bytes(hit[0]))
                if dec is not None:
                    res = (dec[0], dec[1], dec[2], hit[1])
                    break
        self.found[key] = res
        return res

    def scaled_image(self, spr, frame, ow, oh):
        """The sprite as an RGBA Pillow image at ow x oh, cached. Uses the same nearest-
        neighbour sampling as before (scaled_rows), so sprites look exactly the same."""
        key = ("img", spr, frame, ow, oh)
        if key in self.scaled:
            return self.scaled[key]
        px = bytearray(ow * oh * 4)
        for y, runs in enumerate(self.scaled_rows(spr, frame, ow, oh)):
            for x, data in runs:
                o = (y * ow + x) * 4
                for k in range(len(data) // 3):
                    px[o + k * 4:o + k * 4 + 3] = data[k * 3:k * 3 + 3]
                    px[o + k * 4 + 3] = 255
        im = Image.frombytes("RGBA", (ow, oh), bytes(px))
        self.scaled[key] = im
        return im

    def scaled_rows(self, spr, frame, ow, oh):
        key = (spr, frame, ow, oh)
        if key in self.scaled:
            return self.scaled[key]
        w, h, img, flip = self.found[(spr, frame)]
        pal = self.pal
        rows = []
        for oy in range(oh):
            src = img[min(h - 1, int((oy + 0.5) * h / oh))]
            runs = []
            run_x, run = None, bytearray()
            for ox in range(ow):
                sx = min(w - 1, int((ox + 0.5) * w / ow))
                if flip:
                    sx = w - 1 - sx
                c = src[sx]
                if c < 0:
                    if run_x is not None:
                        runs.append((run_x, bytes(run)))
                        run_x, run = None, bytearray()
                else:
                    if run_x is None:
                        run_x = ox
                    run += pal[c]
            if run_x is not None:
                runs.append((run_x, bytes(run)))
            rows.append(runs)
        self.scaled[key] = rows
        return rows


# ------------------------------------------------------------------ trace ---
def build_trace(draw_lines, jump_mult, start=None):
    """Reorder lines into one continuous pen path.

    From the end of each line, carry on along an undrawn line touching that point (flipped if
    needed), choosing the straightest continuation; at a dead end, glide (no drawing) to the
    nearest undrawn line end. Returns moves: (ax, ay, bx, by, rgb or None, cost), where cost is
    the length for drawn moves and length / jump_mult for glides, so pacing stays uniform.
    """
    n = len(draw_lines)
    at = {}                                   # point -> line indices with an end there
    for i, (ax, ay, bx, by, *_r) in enumerate(draw_lines):
        at.setdefault((ax, ay), []).append(i)
        at.setdefault((bx, by), []).append(i)
    C = 1024                                  # grid of line ends, for nearest-undrawn search
    cells = {}
    for i, (ax, ay, bx, by, *_r) in enumerate(draw_lines):
        for x, y in ((ax, ay), (bx, by)):
            cells.setdefault((x // C, y // C), set()).add(i)
    done = [False] * n

    def mark(i):
        done[i] = True
        ax, ay, bx, by = draw_lines[i][:4]
        for x, y in ((ax, ay), (bx, by)):
            cells[(x // C, y // C)].discard(i)

    def nearest(px, py):
        gx, gy = int(px // C), int(py // C)
        best = None
        r = 0
        while True:
            for cx in range(gx - r, gx + r + 1):
                for cy in range(gy - r, gy + r + 1):
                    if max(abs(cx - gx), abs(cy - gy)) != r:
                        continue
                    for i in cells.get((cx, cy), ()):
                        ax, ay, bx, by = draw_lines[i][:4]
                        for sx, sy, flip in ((ax, ay, False), (bx, by, True)):
                            d = math.hypot(sx - px, sy - py)
                            if best is None or (d, i) < (best[0], best[1]):
                                best = (d, i, flip)
            if best is not None and best[0] <= r * C:
                return best
            r += 1

    moves = []
    px, py = start if start is not None else (draw_lines[0][0], draw_lines[0][1])
    dx, dy = 0.0, 0.0                         # direction of travel so far
    for _ in range(n):
        cand = [i for i in at.get((px, py), ()) if not done[i]]
        if cand:
            best = None
            for i in cand:
                ax, ay, bx, by = draw_lines[i][:4]
                flip = (ax, ay) != (px, py)
                ex, ey = (ax, ay) if flip else (bx, by)
                ln = math.hypot(ex - px, ey - py)
                straight = ((ex - px) * dx + (ey - py) * dy) / ln if ln > 0 else -2.0
                key = (-straight, i)
                if best is None or key < best[0]:
                    best = (key, i, flip)
            _, i, flip = best
        else:
            d, i, flip = nearest(px, py)
            ax, ay, bx, by = draw_lines[i][:4]
            sx, sy = (bx, by) if flip else (ax, ay)
            if d > 0:
                moves.append((px, py, sx, sy, None, d / jump_mult))
        ax, ay, bx, by, rgb, ln = draw_lines[i]
        if flip:
            ax, ay, bx, by = bx, by, ax, ay
        moves.append((ax, ay, bx, by, rgb, ln))
        mark(i)
        if ln > 0:
            dx, dy = (bx - ax) / ln, (by - ay) / ln
        px, py = bx, by
    return moves


def nearest_order(points, start):
    """Greedy nearest-next visiting order for points, starting from 'start'. Grid-accelerated."""
    C = 1024
    cells = {}
    for i, (x, y) in enumerate(points):
        cells.setdefault((int(x // C), int(y // C)), set()).add(i)
    order = []
    px, py = start
    for _ in range(len(points)):
        gx, gy = int(px // C), int(py // C)
        best = None
        r = 0
        while True:
            for cx in range(gx - r, gx + r + 1):
                for cy in range(gy - r, gy + r + 1):
                    if max(abs(cx - gx), abs(cy - gy)) != r:
                        continue
                    for i in cells.get((cx, cy), ()):
                        d = math.hypot(points[i][0] - px, points[i][1] - py)
                        if best is None or (d, i) < best:
                            best = (d, i)
            if best is not None and best[0] <= r * C:
                break
            r += 1
        i = best[1]
        order.append(i)
        cells[(int(points[i][0] // C), int(points[i][1] // C))].discard(i)
        px, py = points[i]
    return order


# ------------------------------------------------------------------- main ---
def main():
    global THING_RATE
    sys.stdout = ConsoleLog(sys.stdout)
    args = parse_args(sys.argv[1:])
    only = args["onlythings"]

    if not shutil.which("ffmpeg"):
        die("ffmpeg could not be found on PATH. Install it and make sure 'ffmpeg' runs from a console.")

    wad_path = args["wad"]
    if not os.path.isfile(wad_path):
        die(f"WAD not found: '{wad_path}'")
    wad = Wad(wad_path)

    maps = wad.map_names()
    if not maps:
        die("no maps found in the WAD")
    mapname = (args["map"] or maps[0]).upper()
    lumps = wad.map_lumps(mapname)
    if lumps is None:
        die(f"map {mapname} not found. Maps in this WAD: {', '.join(maps)}")

    pal, pal_src = load_palette(wad, args["iwad"])
    verts, sectors, side_sector, lines, things = read_map(lumps, mapname)

    # drawn lines, in index order: (ax, ay, bx, by, rgb, length)
    draw_lines = []
    for ln in lines:
        c = line_colour(ln, sectors, side_sector)
        if c is None:
            continue
        if ln[0] >= len(verts) or ln[1] >= len(verts):
            continue
        a, b = verts[ln[0]], verts[ln[1]]
        draw_lines.append((a[0], a[1], b[0], b[1], pal[c], math.hypot(b[0] - a[0], b[1] - a[1])))
    if not draw_lines:
        die(f"{mapname} has no visible lines to draw")
    n_lines = len(draw_lines)
    line_len = sum(d[5] for d in draw_lines)

    # the pen's path: index order, or (trace) one continuous walk with glides across gaps.
    # Each move is (ax, ay, bx, by, rgb or None for a glide, cost in pen units)
    cam = args["cam"]
    if cam == "trace":
        draw_lines = build_trace(draw_lines, args["jumptransition"])
    glides = [m for m in draw_lines if m[4] is None]
    glide_len = sum(m[5] for m in glides) * args["jumptransition"]
    n = len(draw_lines)

    # full-map view (bounds from every line's vertices). A view is (centre x, centre y,
    # map units across the frame width).
    xs = [v[0] for ln in lines if ln[0] < len(verts) and ln[1] < len(verts) for v in (verts[ln[0]], verts[ln[1]])]
    ys = [v[1] for ln in lines if ln[0] < len(verts) and ln[1] < len(verts) for v in (verts[ln[0]], verts[ln[1]])]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    mw, mh = max(maxx - minx, 1), max(maxy - miny, 1)
    full_w = max(mw, mh * WIDTH / HEIGHT) / (1 - 2 * MARGIN_PCT / 100.0)
    full_view = ((minx + maxx) / 2.0, (miny + maxy) / 2.0, full_w)

    ztype, zval = args["zoom"]
    zoom_w = zval if ztype == "mu" else full_w * zval / 100.0
    zoom_desc = (f"{zoom_w:.0f} mu across  =  {zoom_w / full_w * 100:.1f}% of full view  =  "
                 f"{full_w / zoom_w:.2f}x  ({WIDTH / zoom_w:.3f} px/unit)")

    def to_screen(view, x, y):
        cx, cy, vw = view
        sc = WIDTH / vw
        return WIDTH / 2.0 + (x - cx) * sc, HEIGHT / 2.0 - (y - cy) * sc   # north up

    if args["zoomthing"] is not None:
        tzt, tzv = args["zoomthing"]
        tzoom_w = tzv if tzt == "mu" else full_w * tzv / 100.0
    else:
        tzoom_w = zoom_w
    tzoom_desc = (f"{tzoom_w:.0f} mu across  =  {tzoom_w / full_w * 100:.1f}% of full view  =  "
                  f"{full_w / tzoom_w:.2f}x  ({WIDTH / tzoom_w:.3f} px/unit)")

    def thing_view(tip):
        sc = WIDTH / tzoom_w
        return (round(tip[0] * sc) / sc, round(tip[1] * sc) / sc, tzoom_w)

    def follow_view(tip):
        sc = WIDTH / zoom_w                               # snap to whole pixels: no shimmer
        return (round(tip[0] * sc) / sc, round(tip[1] * sc) / sc, zoom_w)

    def pen_tip(i, d):
        """Map position of the pen: line i, d units along it."""
        if i < n and d > 0:
            ax, ay, bx, by, _rgb, ln = draw_lines[i]
            t = d / ln if ln > 0 else 1.0
            return ax + (bx - ax) * t, ay + (by - ay) * t
        if i == 0:
            return draw_lines[0][0], draw_lines[0][1]
        return draw_lines[i - 1][2], draw_lines[i - 1][3]

    # pacing
    hold_start = int(round(HOLD_START_SECONDS * FPS))
    hold_end = int(round(HOLD_END_SECONDS * FPS))
    end_zoom = int(round(END_ZOOM_SECONDS * FPS)) if (cam != "off" or args["tracethings"]) else 0

    # things pass: filter by category, in thing index order. Drawn on the full-map view.
    tmode = args["things"]
    thing_list = []                                   # (x, y, angle, sprite, frame, radius, cat)
    cat_shown, cat_skipped, missing = {}, {}, {}
    sprites = None
    if tmode != "off":
        if tmode == "img":
            sprites = Sprites(wad, Wad(resolve_iwad(args["iwad"])), pal)
        wanted = set(args["thingtypes"])
        skill_bit = {1: 1, 2: 1, 3: 2, 4: 4, 5: 4}[int(THING_SKILL)]

        def add(x, y, ang, typ, cat, ent):
            cat_shown[cat] = cat_shown.get(cat, 0) + 1
            spr, frame, rad = (ent[0], ent[1], ent[2]) if ent else (None, None, 16)
            if tmode == "img" and spr and sprites.get(spr, frame) is None:
                missing[f"{spr}{frame}"] = missing.get(f"{spr}{frame}", 0) + 1
                spr = None
            if tmode == "img" and not spr and ent is None:
                missing[f"type {typ}"] = missing.get(f"type {typ}", 0) + 1
            thing_list.append((x, y, ang, spr if tmode == "img" else None, frame, rad, cat))

        # Player 1-4 starts always come first. Like the engine, only the LAST start of each
        # number spawns the real player; earlier copies are voodoo dolls and are left out.
        # (Player starts ignore skill and multiplayer flags, as in the game.)
        real_start = {}
        for i, t in enumerate(things):
            if t[3] in (1, 2, 3, 4):
                real_start[t[3]] = i
        for pn in (1, 2, 3, 4):
            if pn in real_start:
                x, y, ang, typ, _f = things[real_start[pn]]
                add(x, y, ang, typ, f"p{pn}", THING_TABLE[typ])
        voodoo = sum(1 for t in things if t[3] in (1, 2, 3, 4)) - len(real_start)
        if voodoo:
            cat_skipped["voodoo dolls (extra player starts)"] = voodoo
        n_starts = len(thing_list)

        for (x, y, ang, typ, tfl) in things:
            if typ in (1, 2, 3, 4):
                continue                                  # handled above
            if tfl & 0x10:                                # multiplayer only (co-op / deathmatch)
                cat_skipped["multiplayer-only"] = cat_skipped.get("multiplayer-only", 0) + 1
                continue
            if not tfl & skill_bit:                       # not on the chosen skill
                cat_skipped[f"not on skill {int(THING_SKILL)}"] = cat_skipped.get(f"not on skill {int(THING_SKILL)}", 0) + 1
                continue
            if typ in THING_INVISIBLE:
                cat_skipped["invisible"] = cat_skipped.get("invisible", 0) + 1
                continue
            ent = THING_TABLE.get(typ)
            cat = ent[3] if ent else "unknown"
            if cat not in wanted:
                cat_skipped[cat] = cat_skipped.get(cat, 0) + 1
                continue
            add(x, y, ang, typ, cat, ent)
    else:
        n_starts = 0
    tcount = len(thing_list)
    things_frames = int(math.ceil(tcount * FPS / THING_RATE)) if tcount else 0

    def things_placed(k):
        """How many things are on screen after things-phase frame k (0-based)."""
        return min(tcount, int(round((k + 1) * tcount / things_frames))) if things_frames else 0

    thing_px = WIDTH / full_w                          # things live on the full-map view
    tri = [((-0.5, -0.7), (1.0, 0.0)), ((1.0, 0.0), (-0.5, 0.7)), ((-0.5, 0.7), (-0.5, -0.7))]
    tri_rgb = pal[mapcolor_sprt]

    def draw_thing(cv, t, view=None):
        view = view or full_view
        x, y, ang, spr, frame, rad, _cat = t
        sx, sy = to_screen(view, x, y)
        tpx = WIDTH / view[2]
        if spr:
            w, h = sprites.found[(spr, frame)][:2]
            sc = tpx * THING_SCALE
            if max(w, h) * sc < THING_MIN_PX:
                sc = THING_MIN_PX / max(w, h)
            ow, oh = max(1, int(round(w * sc))), max(1, int(round(h * sc)))
            cv.paste(sprites.scaled_image(spr, frame, ow, oh),
                     int(round(sx - ow / 2.0)), int(round(sy - oh / 2.0)))
        else:
            r = max(16 * tpx * THING_SCALE, THING_MIN_PX / 2.0)
            a = math.radians(ang)
            ca, sa = math.cos(a), math.sin(a)
            for (ax, ay), (bx, by) in tri:
                cv.plot_line(sx + (ax * ca - ay * sa) * r, sy - (ax * sa + ay * ca) * r,
                             sx + (bx * ca - by * sa) * r, sy - (bx * sa + by * ca) * r, tri_rgb)

    # ======================================================================= ENGINE ===
    # Everything below builds a timeline of phases, then renders it. A phase is one of:
    #   hold  - still frames                move - eased camera move between two views
    #   pen   - the pen travels a list of moves (lines, or things) with a camera rule
    #   rate  - things appear on the full map at THING_RATE
    # A frame's look is fully described by (view, lines done, line partial, things shown),
    # which lets the video draw incrementally and -testframe render any frame directly.
    zoomf = int(round(END_ZOOM_SECONDS * FPS))
    bzf = int(round(BOX_ZOOM_SECONDS * FPS))
    bhf = int(round(BOX_HOLD_SECONDS * FPS))
    tbzf = int(round(float(THING_BOX_ZOOM_SECONDS) * FPS))
    tbhf = int(round(float(THING_BOX_HOLD_SECONDS) * FPS))
    bpf = int(round(BOX_PAN_SECONDS * FPS))
    line_pan = float(BOX_ZOOM_SECONDS) == 0               # 0 box zoom = pan between boxes
    thing_pan = float(THING_BOX_ZOOM_SECONDS) == 0
    midf = int(round(MID_HOLD_SECONDS * FPS))
    hold_start = int(round(HOLD_START_SECONDS * FPS))
    hold_end = int(round(HOLD_END_SECONDS * FPS))
    jm = args["jumptransition"]

    # ----- box grids: 16:9 boxes anchored so one is centred on the real player 1 start
    p1s = [t for t in things if t[3] == 1]
    anchor = (p1s[-1][0], p1s[-1][1]) if p1s else (full_view[0], full_view[1])

    def zoom_width(z):
        zt_, zv_ = z
        return zv_ if zt_ == "mu" else full_w * zv_ / 100.0

    box_w = zoom_width(args["box"])
    box_h = box_w * HEIGHT / WIDTH
    tbox_w = zoom_width(args["thingbox"]) if args["thingbox"] is not None else box_w
    tbox_h = tbox_w * HEIGHT / WIDTH

    def cell_of(x, y, bw, bh):
        return (int(math.floor((x - anchor[0]) / bw + 0.5)),
                int(math.floor((y - anchor[1]) / bh + 0.5)))

    def cell_view(c, bw, bh):
        return (anchor[0] + c[0] * bw, anchor[1] + c[1] * bh, bw)

    def box_sequence(weights, bw, bh):
        """Visiting order for the boxes that have something in them.
        spiral: player 1's box, then ring by ring outwards (ring = boxes at the same
                Chebyshev distance); each ring is walked round clockwise starting from the
                box nearest the last one, so every ring is finished before the next.
        dense:  the densest unfinished box directly left/right/above/below the last one,
                else the densest unfinished box anywhere.
        Returns (order, info) where info is a short description for the console."""
        if not weights:
            return [], ""
        home = cell_of(anchor[0], anchor[1], bw, bh)

        def key(c):
            return (-weights[c][0], -weights[c][1], math.hypot(c[0] * bw, c[1] * bh), c)

        if args["boxorder"] == "sweep":
            # walk box to touching box; prefer the one with the fewest unfinished neighbours
            # (Warnsdorff's rule), so corners and dead-ends are cleared rather than stranded
            nbr = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]
            remaining = set(weights)
            cur = home if home in remaining else min(
                remaining, key=lambda c: (math.hypot(c[0] - home[0], c[1] - home[1]), c))
            order = [cur]
            remaining.discard(cur)
            jumps = 0

            def free(c):
                return sum(1 for d in nbr if (c[0] + d[0], c[1] + d[1]) in remaining)

            while remaining:
                near = [(cur[0] + d[0], cur[1] + d[1]) for d in nbr
                        if (cur[0] + d[0], cur[1] + d[1]) in remaining]
                if near:
                    cur = min(near, key=lambda c: (free(c), 0 if (c[0] == cur[0] or c[1] == cur[1]) else 1,
                                                   math.hypot(c[0] - home[0], c[1] - home[1]), c))
                else:
                    cur = min(remaining, key=lambda c: (math.hypot(c[0] - cur[0], c[1] - cur[1]), c))
                    jumps += 1
                order.append(cur)
                remaining.discard(cur)
            return order, (f"sweep from player 1's box, {jumps} jump{'s' if jumps != 1 else ''} "
                           f"to a non-touching box")

        if args["boxorder"] == "spiral":
            rings = {}
            for c in weights:
                rings.setdefault(max(abs(c[0] - home[0]), abs(c[1] - home[1])), []).append(c)
            order = []
            cur = home
            for r in sorted(rings):
                ring = rings[r]
                if r == 0:
                    order += ring
                    cur = ring[0]
                    continue
                # clockwise around the home box (map y points up)
                ring.sort(key=lambda c: -math.atan2(c[1] - home[1], c[0] - home[0]))
                start = min(range(len(ring)), key=lambda i: (math.hypot(ring[i][0] - cur[0],
                                                                          ring[i][1] - cur[1]), i))
                ring = ring[start:] + ring[:start]
                order += ring
                cur = ring[-1]
            return order, f"spiral, {len(rings)} rings around player 1"

        remaining = set(weights)
        cur = home if home in remaining else min(remaining, key=key)
        order = [cur]
        remaining.discard(cur)
        by_neighbour = by_densest = 0
        while remaining:
            near = [c for c in ((cur[0] - 1, cur[1]), (cur[0] + 1, cur[1]),
                                (cur[0], cur[1] - 1), (cur[0], cur[1] + 1)) if c in remaining]
            if near:
                cur = min(near, key=key)
                by_neighbour += 1
            else:
                cur = min(remaining, key=key)
                by_densest += 1
            order.append(cur)
            remaining.discard(cur)
        return order, (f"dense - player 1's first, then {by_neighbour} by densest neighbour, "
                       f"{by_densest} by densest anywhere")

    # ----- line moves, split into pen segments: [(moves, camera)]
    #   camera: "full" | "follow" | ("box", view)
    line_segs = []
    line_box_range = None
    line_order_info = thing_order_info = ""
    if cam == "boxed" and not only:
        pieces = {}
        for (ax, ay, bx, by, rgb, ln) in draw_lines:     # index order lines, cut at box edges
            ts = {0.0, 1.0}
            dxl, dyl = bx - ax, by - ay
            if dxl:
                lo, hi = sorted((ax, bx))
                for i in range(int(math.ceil((lo - anchor[0]) / box_w - 0.5)),
                               int(math.floor((hi - anchor[0]) / box_w - 0.5)) + 1):
                    t = (anchor[0] + (i + 0.5) * box_w - ax) / dxl
                    if 0 < t < 1:
                        ts.add(t)
            if dyl:
                lo, hi = sorted((ay, by))
                for j in range(int(math.ceil((lo - anchor[1]) / box_h - 0.5)),
                               int(math.floor((hi - anchor[1]) / box_h - 0.5)) + 1):
                    t = (anchor[1] + (j + 0.5) * box_h - ay) / dyl
                    if 0 < t < 1:
                        ts.add(t)
            ts = sorted(ts)
            for t0, t1 in zip(ts, ts[1:]):
                if t1 - t0 < 1e-12 and ln > 0:
                    continue
                x0, y0 = ax + dxl * t0, ay + dyl * t0
                x1, y1 = ax + dxl * t1, ay + dyl * t1
                c = cell_of((x0 + x1) / 2, (y0 + y1) / 2, box_w, box_h)
                pieces.setdefault(c, []).append((x0, y0, x1, y1, rgb, ln * (t1 - t0)))
        weights = {c: (len(v), sum(m[5] for m in v)) for c, v in pieces.items()}
        order, line_order_info = box_sequence(weights, box_w, box_h)
        line_box_range = (max(w[0] for w in weights.values()), min(w[0] for w in weights.values()))
        pen = anchor
        for c in order:
            mv = build_trace(pieces[c], jm, start=pen)
            if mv and mv[0][4] is None:
                # the pan already brings the pen into this box: its glide in costs no time
                mv[0] = mv[0][:5] + (0.0,)
            line_segs.append((mv, ("box", cell_view(c, box_w, box_h))))
            pen = (mv[-1][2], mv[-1][3])
    elif not only:
        line_segs.append((draw_lines, "full" if cam == "off" else
                          "dz" if cam in ("follow", "steady") else "follow"))
    M = [m for seg in line_segs for m in seg[0]]          # every line move, in pen order
    nM = len(M)
    glides = [m for m in M if m[4] is None]
    glide_len = sum(m[5] for m in glides) * jm

    # ----- things: placement order T and pen segments [(tmoves, camera)]
    #   tmove = (ax, ay, bx, by, length, thing); camera "tfollow" | ("box", view)
    boxed_things = tcount > 0 and (cam == "boxed" or args["thingbox"] is not None)
    zoomed_things = tcount > 0 and (boxed_things or args["tracethings"])
    T = list(thing_list)
    thing_segs = []
    thing_box_range = None
    if boxed_things:
        tcells = {}
        for k, t in enumerate(thing_list):
            tcells.setdefault(cell_of(t[0], t[1], tbox_w, tbox_h), []).append(k)
        weights = {c: (len(v), 0) for c, v in tcells.items()}
        order, thing_order_info = box_sequence(weights, tbox_w, tbox_h)
        thing_box_range = (max(w[0] for w in weights.values()), min(w[0] for w in weights.values()))
        T = []
        pen = anchor
        for c in order:
            ks = tcells[c]
            first = [k for k in ks if k < n_starts]           # player starts first
            rest = [k for k in ks if k >= n_starts]
            seq = first[:]
            if rest:
                startp = (thing_list[first[-1]][0], thing_list[first[-1]][1]) if first else pen
                ro = nearest_order([(thing_list[k][0], thing_list[k][1]) for k in rest], startp)
                seq += [rest[i] for i in ro]
            tm = []
            for k in seq:
                t = thing_list[k]
                # the first move into a box is covered by the camera move: no travel time
                d = 0.0 if not tm else math.hypot(t[0] - pen[0], t[1] - pen[1])
                tm.append((pen[0], pen[1], t[0], t[1], d, t))
                pen = (t[0], t[1])
                T.append(t)
            thing_segs.append((tm, ("box", cell_view(c, tbox_w, tbox_h))))
    elif zoomed_things:
        if cam in ("follow", "steady", "lock") or n_starts >= tcount:
            order = list(range(tcount))
        else:                                             # starts first, then nearest-next
            startp = ((thing_list[n_starts - 1][0], thing_list[n_starts - 1][1]) if n_starts
                      else (thing_list[0][0], thing_list[0][1]))
            rest = nearest_order([(t[0], t[1]) for t in thing_list[n_starts:]], startp)
            order = list(range(n_starts)) + [n_starts + i for i in rest]
        T = [thing_list[i] for i in order]
        pen = (T[0][0], T[0][1])                          # the pen starts on the first thing
        tm = []
        for t in T:
            tm.append((pen[0], pen[1], t[0], t[1], math.hypot(t[0] - pen[0], t[1] - pen[1]), t))
            pen = (t[0], t[1])
        thing_segs.append((tm, "tdz" if cam in ("follow", "steady") else "tfollow"))
    # ----- conform the box views: each box only moves as far as needed from the previous view
    # to bring what it still has to draw into the frame (BOX_MARGIN % clear of the edges)
    def conform(segs, prev, pts_of):
        out = []
        for si, (mv, camr) in enumerate(segs):
            if not isinstance(camr, tuple):
                out.append((mv, camr))
                continue
            cxn, cyn, bw = camr[1]
            if si == 0 or prev is None:
                out.append((mv, camr))                    # the first box stays where it is
                prev = camr[1]
                continue
            bh = bw * HEIGHT / WIDTH
            pts = pts_of(mv)
            if not pts:
                out.append((mv, camr))
                prev = camr[1]
                continue
            minx = min(p[0] for p in pts); maxx = max(p[0] for p in pts)
            miny = min(p[1] for p in pts); maxy = max(p[1] for p in pts)
            mx, my = bw * BOX_MARGIN / 100.0, bh * BOX_MARGIN / 100.0

            def fit(c, lo, hi, half, m):
                a, b = hi - half + m, lo + half - m          # allowed centre range
                return (lo + hi) / 2.0 if a > b else min(max(c, a), b)

            v = (fit(prev[0], minx, maxx, bw / 2.0, mx), fit(prev[1], miny, maxy, bh / 2.0, my), bw)
            out.append((mv, ("box", v)))
            prev = v
        return out

    line_segs = conform(line_segs, None,
                        lambda mv: [p for m in mv if m[4] is not None for p in ((m[0], m[1]), (m[2], m[3]))])
    thing_segs = conform(thing_segs, None, lambda mv: [(m[2], m[3]) for m in mv])
    TM = [m for seg in thing_segs for m in seg[0]]
    t_path = sum(m[4] for m in TM)

    def seg_first_view(seg, kind):
        mv, camr = seg
        if isinstance(camr, tuple):
            return camr[1]
        if camr == "full":
            return full_view
        if camr in ("follow", "dz"):
            return follow_view((mv[0][0], mv[0][1]))
        return thing_view((mv[0][0], mv[0][1]))           # tfollow

    def seg_last_view(seg):
        mv, camr = seg
        if isinstance(camr, tuple):
            return camr[1]
        if camr == "full":
            return full_view
        if camr in ("dz", "tdz"):
            return dz_last.get(id(mv), follow_view((mv[-1][2], mv[-1][3])))
        if camr == "follow":
            return follow_view((mv[-1][2], mv[-1][3]))
        return thing_view((mv[-1][2], mv[-1][3]))

    # ----- steady / follow camera: simulated frame by frame
    dz_last = {}                                          # id(moves) -> last view of that path
    dz_jumps = {}                                         # id(moves) -> off-screen jumps

    def simulate(mv, li, stp, vw, start, pause_on_jump, pan_frames):
        """Run the pen over mv at stp units/frame with a dead-zone camera. Returns a list of
        frame records (idx, done, view): idx moves fully done, done = units into move idx.
        Off-screen jumps: pause + pan (steady) or keep drawing + fast catch-up (follow)."""
        vh = vw * HEIGHT / WIDTH
        dzx = vw * FOLLOW_DEADZONE / 200.0
        dzy = vh * FOLLOW_DEADZONE / 200.0
        dt = 1.0 / FPS
        a_slow = 1.0 - math.exp(-dt / max(FOLLOW_EASE, 1e-3))
        a_fast = 1.0 - math.exp(-dt / max(FOLLOW_CATCHUP, 1e-3))
        sc = WIDTH / vw
        cx, cy = start[0], start[1]
        n_ = len(mv)
        recs = []
        idx, done = 0, 0.0
        chasing = fast = False
        jumps = 0

        def snap():
            return (round(cx * sc) / sc, round(cy * sc) / sc, vw)

        def on_screen(x, y):
            return abs(x - cx) <= vw * 0.45 and abs(y - cy) <= vh * 0.45

        def tip():
            if idx < n_:
                m = mv[idx]
                ln = m[li]
                f = done / ln if ln > 0 else 0.0
                return m[0] + (m[2] - m[0]) * f, m[1] + (m[3] - m[1]) * f
            m = mv[-1]
            return m[2], m[3]

        while idx < n_:
            budget = stp
            jump_to = None
            while idx < n_ and budget > 1e-9:
                # lines: is the next line's start off-screen?  things: the next thing itself?
                px_, py_ = (mv[idx][2], mv[idx][3]) if li == 4 else (mv[idx][0], mv[idx][1])
                if done == 0.0 and idx > 0 and not on_screen(px_, py_):
                    jumps += 1
                    if pause_on_jump:
                        jump_to = (px_, py_)
                        break
                    if not fast:
                        chasing = fast = True
                ln = mv[idx][li]
                left = ln - done
                if left <= budget + 1e-6:
                    budget -= left
                    idx += 1
                    done = 0.0
                else:
                    done += budget
                    budget = 0.0
            tx, ty = tip()
            dx, dy = tx - cx, ty - cy
            if abs(dx) > dzx or abs(dy) > dzy:
                chasing = True
            if chasing:
                a = a_fast if fast else a_slow
                cx += dx * a
                cy += dy * a
                if math.hypot(tx - cx, ty - cy) < vw * 0.08:
                    chasing = fast = False
            # never let the pen leave the frame
            cx = min(max(cx, tx - vw * 0.45), tx + vw * 0.45)
            cy = min(max(cy, ty - vh * 0.45), ty + vh * 0.45)
            recs.append((idx, done, snap()))
            if jump_to is not None:
                a_v = snap()
                b_v = (jump_to[0], jump_to[1], vw)
                for f in range(1, pan_frames + 1):
                    recs.append((idx, 0.0, lerp_view(a_v, b_v, f / pan_frames)))
                cx, cy = jump_to
                chasing = fast = False
                if li == 4:
                    idx += 1                              # the pan carried the pen to that thing
        if not recs:
            recs.append((n_, 0.0, snap()))
        dz_jumps[id(mv)] = jumps
        return recs

    # ----- timeline
    def pen_frames(length, stp):
        return max(1, int(math.ceil(length / stp - 1e-9)))

    def build_timeline(step, tstep, rate_frames):
        ph = []

        def add(kind, frames, label, **kw):
            if frames > 0:
                kw.update(kind=kind, frames=frames, label=label,
                          keep=(kind == "hold" or (kind == "move" and "pan" not in label)))
                ph.append(kw)

        if only:
            add("hold", hold_start, "start hold (finished map)", view=full_view, lu=nM, tu=0)
            last = full_view
        else:
            sv = seg_first_view(line_segs[0], "lines") if line_segs else full_view
            add("hold", hold_start, "start hold", view=sv, lu=0, tu=0)
            m0 = 0
            last = sv
            for si, seg in enumerate(line_segs):
                v0 = seg_first_view(seg, "lines")
                if si and v0 != last and line_pan:
                    add("move", bpf, "box pan", a=last, b=v0, lu=m0, tu=0)
                elif si and v0 != last:
                    add("move", bzf, "box zoom out/in", a=last, b=full_view, lu=m0, tu=0)
                    add("hold", bhf, "box hold (full map)", view=full_view, lu=m0, tu=0)
                    add("move", bzf, "box zoom out/in", a=full_view, b=v0, lu=m0, tu=0)
                ln = sum(m[5] for m in seg[0])
                if seg[1] == "dz":
                    recs = simulate(seg[0], 5, step, zoom_w, v0, cam == "steady", bpf)
                    dz_last[id(seg[0])] = recs[-1][2]
                    add("path", len(recs), "drawing lines", what="lines", m0=m0,
                        m1=m0 + len(seg[0]), recs=recs, length=ln, tu=0)
                else:
                    add("pen", pen_frames(ln, step), "drawing lines", what="lines", m0=m0,
                        m1=m0 + len(seg[0]), cam=seg[1], step=step, length=ln, tu=0)
                m0 += len(seg[0])
                last = seg_last_view(seg)
        straight_pan = (not only and line_pan and thing_pan and cam == "boxed"
                        and bool(thing_segs) and isinstance(thing_segs[0][1], tuple))
        if tcount:
            if not only and not straight_pan:
                if last != full_view:
                    add("move", zoomf, "zoom out to the full map", a=last, b=full_view, lu=nM, tu=0)
                add("hold", midf, "mid hold (map finished)", view=full_view, lu=nM, tu=0)
                last = full_view
            if thing_segs:
                t0 = 0
                for si, seg in enumerate(thing_segs):
                    v0 = seg_first_view(seg, "things")
                    if v0 != last and si == 0 and straight_pan:
                        add("move", bpf, "pan to the things", a=last, b=v0, lu=nM, tu=t0)
                    elif v0 != last and si == 0:
                        add("move", zoomf, "zoom in for the things", a=last, b=v0, lu=nM, tu=t0)
                    elif v0 != last and thing_pan:
                        add("move", bpf, "thing box pan", a=last, b=v0, lu=nM, tu=t0)
                    elif v0 != last:
                        add("move", tbzf, "thing box zoom out/in", a=last, b=full_view, lu=nM, tu=t0)
                        add("hold", tbhf, "thing box hold (full map)", view=full_view, lu=nM, tu=t0)
                        add("move", tbzf, "thing box zoom out/in", a=full_view, b=v0, lu=nM, tu=t0)
                    ln = sum(m[4] for m in seg[0])
                    if seg[1] == "tdz":
                        recs = simulate(seg[0], 4, tstep, tzoom_w, v0, cam == "steady", bpf)
                        dz_last[id(seg[0])] = recs[-1][2]
                        add("path", len(recs), "placing things", what="things", m0=t0,
                            m1=t0 + len(seg[0]), recs=recs, length=ln, tu=t0)
                    else:
                        add("pen", pen_frames(ln, tstep), "placing things", what="things", m0=t0,
                            m1=t0 + len(seg[0]), cam=seg[1], step=tstep, length=ln, tu=t0)
                    t0 += len(seg[0])
                    last = seg_last_view(seg)
            else:
                add("rate", rate_frames, "placing things", lu=nM)
                last = full_view
        if last != full_view:
            add("move", zoomf, "zoom out to the full map", a=last, b=full_view, lu=nM, tu=len(T))
        add("hold", hold_end, "end hold", view=full_view, lu=nM, tu=len(T))
        return ph

    # ----- speeds and -vidlength
    # -vidlength works like speeding up / slowing down a finished clip in an editor: the video
    # is planned with the given settings (speeds, rate, holds, pans, zooms), then every one of
    # them is scaled by the same factor so the whole thing lasts exactly the requested time.
    speed = args["drawspeed"] or float(DRAW_SPEED)
    t_speed = args["thingspeed"] or speed
    speed_note = ""
    scale_note = ""
    vid_len = args["vidlength"]
    if vid_len is None and str(VID_LENGTH).strip():
        vid_len = parse_length(VID_LENGTH, "VID_LENGTH")

    def rate_frames_for(rate):
        return int(math.ceil(tcount * FPS / rate)) if tcount else 0

    def total(ph):
        return sum(p["frames"] for p in ph)

    rate_frames = rate_frames_for(THING_RATE)
    if args["timepreservezoom"] and vid_len is None:
        print(f"{C_DIM}note: -timepreservezoom only does something together with -vidlength{C_RST}")
    if vid_len is not None and args["timepreservezoom"]:
        # zooms and holds keep their set lengths; drawing, placing and pans share the rest
        target = int(round(vid_len * FPS))
        nat_ph = build_timeline(speed / FPS, t_speed / FPS, rate_frames)
        kept = sum(p["frames"] for p in nat_ph if p["keep"])
        flex = sum(p["frames"] for p in nat_ph if not p["keep"])
        if kept >= target:
            def mmss(fr):
                m_, s_ = divmod(int(round(fr / FPS)), 60)
                return f"{m_}:{s_:02d}"
            die(f"the zooms and holds kept by -timepreservezoom take {mmss(kept)}, which is not "
                f"shorter than -vidlength {mmss(target)} - nothing is left for drawing")
        f = (target - kept) / flex if flex else 1.0
        bpf = max(1, int(round(bpf * f))) if bpf else 0
        speed /= f
        t_speed /= f
        THING_RATE /= f
        rate_frames = rate_frames_for(THING_RATE)
        tries = 0
        while total(build_timeline(speed / FPS, t_speed / FPS, rate_frames)) > target:
            speed *= 1.001
            t_speed *= 1.001
            THING_RATE *= 1.001
            rate_frames = rate_frames_for(THING_RATE)
            tries += 1
            if tries > 20000:
                die(f"video length {vid_len}s is too short for this map and these settings")
        km, ks = divmod(int(round(kept / FPS)), 60)
        how = (f"{1 / f:.3g}x faster" if f < 1 else f"{f:.3g}x slower" if f > 1 else "unchanged")
        scale_note = (f"zooms & holds kept ({km}:{ks:02d}); drawing, placing and pans {how} "
                      f"to fit the rest")
        speed_note = "  (time-scaled)"
    elif vid_len is not None:
        target = int(round(vid_len * FPS))
        natural = total(build_timeline(speed / FPS, t_speed / FPS, rate_frames))
        f = target / natural                              # > 1 = slower, < 1 = faster

        def scaled(frames, keep_one):
            v = int(round(frames * f))
            return max(1, v) if (keep_one and frames > 0) else max(0, v)

        hold_start = scaled(hold_start, False)
        hold_end = scaled(hold_end, False)
        midf = scaled(midf, False)
        zoomf = scaled(zoomf, True)
        bzf = scaled(bzf, True)
        bhf = scaled(bhf, False)
        tbzf = scaled(tbzf, True)
        tbhf = scaled(tbhf, False)
        bpf = scaled(bpf, True)
        speed /= f
        t_speed /= f
        THING_RATE /= f
        rate_frames = rate_frames_for(THING_RATE)
        tries = 0
        while total(build_timeline(speed / FPS, t_speed / FPS, rate_frames)) > target:
            speed *= 1.001                                # rounding overshoot: nudge the pace
            t_speed *= 1.001
            THING_RATE *= 1.001
            rate_frames = rate_frames_for(THING_RATE)
            tries += 1
            if tries > 20000:
                die(f"video length {vid_len}s is too short for this map and these settings")
        nm, ns = divmod(int(round(natural / FPS)), 60)
        h, rem = divmod(int(vid_len), 3600)
        mnt, sec = divmod(rem, 60)
        nice = (f"{h}h{mnt:02d}m{sec:02d}s" if h else f"{mnt}m{sec:02d}s" if mnt else f"{sec}s")
        how = (f"{1 / f:.3g}x faster" if f < 1 else f"{f:.3g}x slower" if f > 1 else "unchanged")
        scale_note = (f"{how} (natural {nm}:{ns:02d} -> {nice}); every speed, hold, pan and zoom "
                      f"scaled by the same amount")
        speed_note = "  (time-scaled)"
    phases = build_timeline(speed / FPS, t_speed / FPS, rate_frames)
    total_frames = total(phases)
    if vid_len is not None and total_frames < int(round(vid_len * FPS)):
        phases[-1]["frames"] += int(round(vid_len * FPS)) - total_frames   # spare frames -> end hold
        total_frames = total(phases)

    # cumulative lengths per pen phase, for finding the pen at any distance
    for p in phases:
        if p["kind"] == "pen":
            src = M if p["what"] == "lines" else TM
            li = 5 if p["what"] == "lines" else 4
            acc, cum = 0.0, []
            for k in range(p["m0"], p["m1"]):
                acc += src[k][li]
                cum.append(acc)
            p["cum"] = cum

    # ----- frame state: (view, lines fully done, line partial (idx, done), things shown)
    def state_at(p, k):
        kind = p["kind"]
        if kind == "hold":
            return p["view"], p["lu"], None, p["tu"]
        if kind == "move":
            return lerp_view(p["a"], p["b"], (k + 1) / p["frames"]), p["lu"], None, p["tu"]
        if kind == "rate":
            shown = min(tcount, int(round((k + 1) * tcount / p["frames"])))
            return full_view, nM, None, shown
        if kind == "path":
            j, done, view = p["recs"][k]
            idx = p["m0"] + j
            if p["what"] == "lines":
                return view, idx, ((idx, done) if done > 0 and idx < p["m1"] else None), p["tu"]
            return view, nM, None, idx
        d = min(p["length"], (k + 1) * p["step"])
        j = bisect.bisect_right(p["cum"], d + 1e-6)       # moves fully travelled in this phase
        idx = p["m0"] + j
        done = d - (p["cum"][j - 1] if j else 0.0) if idx < p["m1"] else 0.0
        src = M if p["what"] == "lines" else TM
        if idx < p["m1"]:
            mv = src[idx]
            ln = mv[5] if p["what"] == "lines" else mv[4]
            f = done / ln if ln > 0 else 0.0
            tip = (mv[0] + (mv[2] - mv[0]) * f, mv[1] + (mv[3] - mv[1]) * f)
        else:
            mv = src[p["m1"] - 1]
            tip = (mv[2], mv[3])
        camr = p["cam"]
        view = (camr[1] if isinstance(camr, tuple) else full_view if camr == "full"
                else follow_view(tip) if camr == "follow" else thing_view(tip))
        if p["what"] == "lines":
            return view, idx, ((idx, done) if done > 0 else None), p["tu"]
        return view, nM, None, idx

    # ----- drawing
    def seg_draw(cv, view, i, t0, t1):
        ax, ay, bx, by, rgb = M[i][:5]
        if rgb is None:
            return
        x0, y0 = to_screen(view, ax + (bx - ax) * t0, ay + (by - ay) * t0)
        x1, y1 = to_screen(view, ax + (bx - ax) * t1, ay + (by - ay) * t1)
        cv.plot_line(x0, y0, x1, y1, rgb)

    def things_in_view(cv, view, seq):
        cx, cy, vw = view
        hw = vw / 2.0 + 200
        hh = vw * HEIGHT / WIDTH / 2.0 + 200
        for t in seq:
            if abs(t[0] - cx) <= hw and abs(t[1] - cy) <= hh:
                draw_thing(cv, t, view)

    grid = Grid(M) if M else None

    def render_full(cv, st, clear=True):
        view, lu, part, tu = st
        if clear:
            cv.clear()
        if grid is not None:
            cx, cy, vw = view
            sc = WIDTH / vw
            hx, hy = WIDTH / 2.0, HEIGHT / 2.0
            lo_x, hi_x, lo_y, hi_y = -8, WIDTH + 8, -8, HEIGHT + 8
            pl = cv.plot_line
            poly = cv.polyline
            run, run_rgb = None, None                     # connected on-screen lines, one call
            for j in sorted(grid.query(view)):
                if j >= lu:
                    continue
                ax, ay, bx, by, rgb = M[j][:5]
                if rgb is None:
                    continue
                x0 = hx + (ax - cx) * sc
                x1 = hx + (bx - cx) * sc
                if (x0 < lo_x and x1 < lo_x) or (x0 > hi_x and x1 > hi_x):
                    continue
                y0 = hy - (ay - cy) * sc
                y1 = hy - (by - cy) * sc
                if (y0 < lo_y and y1 < lo_y) or (y0 > hi_y and y1 > hi_y):
                    continue
                if 0 <= x0 < WIDTH and 0 <= x1 < WIDTH and 0 <= y0 < HEIGHT and 0 <= y1 < HEIGHT:
                    p0 = (int(round(x0)), int(round(y0)))
                    p1 = (int(round(x1)), int(round(y1)))
                    if run is not None and rgb == run_rgb and run[-1] == p0:
                        run.append(p1)
                        continue
                    if run is not None:
                        poly(run, run_rgb)
                    run, run_rgb = [p0, p1], rgb
                else:
                    if run is not None:
                        poly(run, run_rgb)
                        run = None
                    pl(x0, y0, x1, y1, rgb)
            if run is not None:
                poly(run, run_rgb)
        if part:
            i, d = part
            ln = M[i][5]
            seg_draw(cv, view, i, 0.0, d / ln if ln > 0 else 1.0)
        things_in_view(cv, view, T[:tu])

    def render_step(cv, prev, st):
        """Same view as the last frame: draw only what was added since."""
        view, lu, part, tu = st
        _v, plu, ppart, ptu = prev
        i, d0 = (ppart if ppart else (plu, 0.0))
        ni, nd = (part if part else (lu, 0.0))
        while i < nM and (i < ni or (i == ni and nd > d0)):
            ln = M[i][5]
            a = d0 / ln if ln > 0 else 0.0
            b = 1.0 if i < ni else (nd / ln if ln > 0 else 1.0)
            seg_draw(cv, view, i, a, b)
            i += 1
            d0 = 0.0
        for t in T[ptu:tu]:
            draw_thing(cv, t, view)

    # ----- console summary
    def things_report():
        if tmode == "off":
            return
        shown = ", ".join(f"{c} {cat_shown[c]}" for c in THING_CATEGORIES + ["unknown"] if c in cat_shown)
        if boxed_things:
            print(f"  ThingBox : {tbox_w:.0f} x {tbox_h:.0f} mu  =  {tbox_w / full_w * 100:.1f}% of full "
                  f"view  =  {full_w / tbox_w:.2f}x  ({WIDTH / tbox_w:.3f} px/unit), "
                  f"{len(thing_segs)} boxes ({thing_box_range[0]} -> {thing_box_range[1]} things) - "
                  f"{thing_order_info}; {'pan' if thing_pan else 'zoom out/hold/zoom in'} between boxes")
            timing = (f"box by box, {t_path:.0f} units of travel at {t_speed:.0f} units/s")
        elif thing_segs:
            print(f"  ThingZoom: {tzoom_desc}")
            timing = (f"traced at the zoom, {t_path:.0f} units of travel at {t_speed:.0f} units/s "
                      f"({'index' if cam == 'follow' else 'nearest-next'} order)")
        else:
            timing = f"{rate_frames / FPS:.1f}s at {THING_RATE:.4g}/s"
        print(f"  Things   : {'sprites' if tmode == 'img' else 'triangles'}, skill {int(THING_SKILL)}, "
              f"{tcount} shown{' (' + shown + ')' if shown else ''}, {timing}")
        if cat_skipped:
            sk = ", ".join(f"{c} {k}" for c, k in sorted(cat_skipped.items()))
            print(f"  {C_DIM}           skipped: {sk}{C_RST}")
        if missing:
            ms = ", ".join(f"{k} x{v}" for k, v in sorted(missing.items()))
            print(f"  {C_DIM}           no sprite found, drawn as triangles: {ms}{C_RST}")
        if tmode == "img" and wad.find("DEHACKED") >= 0:
            print(f"  {C_DIM}           note: DEHACKED lump present but not read - stock Doom 2 "
                  f"sprites are used{C_RST}")

    def summary(header):
        print(f"{C_HDR}timelapseMap{C_RST}{header}")
        print(f"  WAD      : {wad_path}")
        print(f"  Map      : {mapname}  ({n_lines} drawn lines of {len(lines)}, {len(things)} things)")
        print(f"  Palette  : {pal_src}")
        print(f"  Map size : {mw}x{mh} units")
        if only:
            print(f"  Mode     : things only - starts on the finished full map")
        if cam == "off" and not only:
            print(f"  Camera   : off, whole map  ({WIDTH / full_w:.4f} px/unit)")
        elif cam in ("follow", "steady") and not only:
            nj = sum(dz_jumps.get(id(sg[0]), 0) for sg in line_segs)
            print(f"  Camera   : {cam}, lines in index order; still while the pen is in the middle "
                  f"{FOLLOW_DEADZONE:g}%, glides after it near the edges; {nj} off-screen jumps - "
                  + ("pen pauses while the camera pans" if cam == "steady" else
                     "pen keeps drawing while the camera catches up"))
            print(f"  Zoom     : {zoom_desc}")
        elif cam == "lock" and not only:
            print(f"  Camera   : lock, pen tip locked dead centre, lines in index order")
            print(f"  Zoom     : {zoom_desc}")
        elif cam == "trace" and not only:
            print(f"  Camera   : trace, pen tip centred, continuous path; {len(glides)} gaps glided "
                  f"({glide_len:.0f} units at {jm:g}x pen speed)")
            print(f"  Zoom     : {zoom_desc}")
        elif cam == "boxed":
            counts = []
            if line_segs:
                counts.append(f"{len(line_segs)} boxes with lines")
            if thing_segs:
                counts.append(f"{len(thing_segs)} with things")
            print(f"  Camera   : boxed, {box_w:.0f} x {box_h:.0f} mu boxes  =  "
                  f"{box_w / full_w * 100:.1f}% of full view  =  {full_w / box_w:.2f}x  "
                  f"({WIDTH / box_w:.3f} px/unit)")
            if line_box_range:
                print(f"  Boxes    : {len(line_segs)} with lines ({line_box_range[0]} -> "
                      f"{line_box_range[1]} lines) - {line_order_info}; "
                      f"{'pan' if line_pan else 'zoom out/hold/zoom in'} between boxes")
        if not only:
            print(f"  Pen      : {speed:.0f} units/s, {line_len:.0f} units of line{speed_note}")
        things_report()
        groups = {}
        for p in phases:
            g = groups.setdefault(p["label"], [0, 0])
            g[0] += p["frames"]
            g[1] += 1
        parts = []
        for lbl, (fr, cnt) in groups.items():
            parts.append(f"{lbl} {fr / FPS:.1f}s" + (f" (x{cnt})" if cnt > 1 else ""))
        if scale_note:
            print(f"  TimeScale: {scale_note}")
        print(f"  Timeline : " + ", ".join(parts))
        print(f"  Video    : {WIDTH}x{HEIGHT} @ {FPS}fps, {total_frames} frames, "
              f"{total_frames / FPS:.1f}s, line width {LINE_WIDTH}px")

    def locate(frame):
        """(phase, frame within phase) for a whole-video frame number."""
        acc = 0
        for p in phases:
            if frame < acc + p["frames"]:
                return p, frame - acc
            acc += p["frames"]
        return phases[-1], phases[-1]["frames"] - 1

    # ----- -testframe
    if args["testframe"]:
        spec = args["testframe"]
        if spec.endswith("%"):
            pc = float(spec[:-1])
            if not 0 <= pc <= 100:
                die(f"-testframe {spec}: percent must be 0-100")
            what = "things" if only else "lines"
            pens = [p for p in phases if p["kind"] in ("pen", "path") and p["what"] == what]
            if not pens and only:
                pens = [p for p in phases if p["kind"] == "rate"]
            tot = sum(p.get("length", p["frames"]) for p in pens) or 1
            dist = tot * pc / 100.0
            frame, acc = 0, 0
            for p in phases:
                if p in pens:
                    L = p.get("length", p["frames"])
                    if dist <= L or p is pens[-1]:
                        if p["kind"] == "path":
                            src = M if p["what"] == "lines" else TM
                            li = 5 if p["what"] == "lines" else 4
                            cum = [0.0]
                            for kk in range(p["m0"], p["m1"]):
                                cum.append(cum[-1] + src[kk][li])
                            kf = len(p["recs"]) - 1
                            for kk, (j, dn, _v) in enumerate(p["recs"]):
                                if cum[min(j, len(cum) - 1)] + dn >= dist - 1e-6:
                                    kf = kk
                                    break
                            frame = acc + kf
                            break
                        unit = p["step"] if p["kind"] == "pen" else 1
                        frame = acc + min(p["frames"] - 1, max(0, int(math.ceil(dist / unit - 1e-9)) - 1))
                        break
                    dist -= L
                acc += p["frames"]
            label = f"{pc:g}pct"
        else:
            t = parse_length(spec, "-testframe") if spec != "0" else 0
            frame = min(int(round(t * FPS)), total_frames - 1)
            label = f"{t}s"
        p, k = locate(frame)
        st = state_at(p, k)
        canvas = Canvas(WIDTH, HEIGHT, pal[mapcolor_back])
        render_full(canvas, st, clear=False)
        out = args["out"]
        if not out:
            base = os.path.splitext(os.path.abspath(wad_path))[0]
            out = (f"{base}_{mapname}_test{'_things' if only else ''}_{rez_label(WIDTH, HEIGHT)}"
                   f"_{label}.png")
        summary("  test frame")
        extra = ""
        if p["kind"] in ("pen", "path") and p["what"] == "things" or p["kind"] == "rate":
            extra = f" ({st[3]} of {len(T)} things placed)"
        print(f"  Frame    : {frame + 1} of {total_frames}  ({(frame + 1) / FPS:.1f}s into the video)"
              f"  - {p['label']}{extra}")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{WIDTH}x{HEIGHT}", "-i", "-", "-frames:v", "1", "-update", "1", out]
        try:
            proc = subprocess.run(cmd, input=bytes(canvas.buf))
        except OSError as e:
            die(f"could not start ffmpeg: {e}")
        if proc.returncode != 0:
            die(f"ffmpeg exited with code {proc.returncode}")
        print(f"{C_OK}Done:{C_RST} {out}")
        write_log(out, "test frame")
        return

    # ----- output
    fmt = args["format"]
    out = args["out"]
    if not out:
        base = os.path.splitext(os.path.abspath(wad_path))[0]
        tag = rez_label(WIDTH, HEIGHT)
        out = (f"{base}_{mapname}_timelapse{'_things' if only else ''}_{tag}"
               + (".mp4" if fmt == "mp4" else "_frames"))
    if fmt == "png":
        out_dir = out
        if os.path.exists(out_dir) and not os.path.isdir(out_dir):
            die(f"-format png needs a folder, but '{out_dir}' is a file")
        os.makedirs(out_dir, exist_ok=True)
        for f in [f for f in os.listdir(out_dir) if re.fullmatch(r"frame_\d{6}\.png", f)]:
            os.remove(os.path.join(out_dir, f))           # old frames from an earlier run
        target_png = os.path.join(out_dir, "frame_%06d.png")

    summary("")
    if fmt == "png":
        print(f"  Output   : {out}{os.sep}frame_000001.png ... (PNG sequence)")
    else:
        print(f"  Output   : {out}")
    if msvcrt:
        print(f"  {C_DIM}Press S to stop and save early.{C_RST}")

    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-"]
    if fmt == "png":
        cmd += ["-c:v", "png", "-start_number", "1", target_png]
    else:
        cmd += ["-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF), "-pix_fmt", "yuv420p"]
        if WIDTH > 3840:
            cmd += ["-rc-lookahead", "10"]              # keeps x264's RAM use sane at 8k
        cmd += ["-movflags", "+faststart", out]
    popen_kw = {}
    if os.name == "nt":
        popen_kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kw["start_new_session"] = True
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, **popen_kw)
    except OSError as e:
        die(f"could not start ffmpeg: {e}")

    moving = (any(p["kind"] in ("move", "path") for p in phases)
              or cam in ("follow", "steady", "lock", "trace") or bool(thing_segs))
    canvas = Canvas(WIDTH, HEIGHT, pal[mapcolor_back], keep_blank=moving)
    written = 0

    def emit():
        nonlocal written
        proc.stdin.write(canvas.buf)
        written += 1
        if written % 15 == 0 or written == total_frames or WIDTH > 4000:
            pct = min(100, written * 100 // total_frames)
            hint = "   [S] stop + save" if msvcrt else ""
            sys.stdout.write(f"\r  Rendering: {pct:3d}%  ({written}/{total_frames}){hint}")
            sys.stdout.flush()
        if msvcrt:
            while msvcrt.kbhit():
                if msvcrt.getwch() in ("s", "S"):
                    raise StopRender()

    try:
        prev = None
        for p in phases:
            for k in range(p["frames"]):
                st = state_at(p, k)
                if prev is not None and st[0] == prev[0]:
                    if st[1:] != prev[1:]:
                        render_step(canvas, prev, st)
                elif prev is None and st[1] == 0 and st[2] is None and st[3] == 0:
                    pass                                  # blank canvas is already right
                else:
                    render_full(canvas, st, clear=(prev is not None) and moving)
                prev = st
                emit()
        proc.stdin.close()
    except StopRender:
        print(f"\n  Stopping... finishing the file")
        try:
            proc.stdin.close()
        except OSError:
            pass
        rc = proc.wait()
        if rc != 0:
            die(f"ffmpeg exited with code {rc}")
        print(f"{C_OK}Stopped early (S):{C_RST} saved {written} frames ({written / FPS:.1f}s) -> {out}")
        write_log(out, f"stopped early with S - {written} of {total_frames} frames ({written / FPS:.1f}s)")
        return
    except BrokenPipeError:
        proc.wait()
        die("ffmpeg stopped unexpectedly (see its message above)")
    except KeyboardInterrupt:
        proc.kill()
        proc.wait()
        print()
        if fmt == "mp4" and os.path.isfile(out):
            try:
                os.remove(out)
            except OSError:
                die(f"aborted (Ctrl+C) - could not delete unfinished '{out}'")
            die(f"aborted (Ctrl+C) - unfinished '{out}' deleted. Press S instead to stop and keep it.")
        die(f"aborted (Ctrl+C) - PNG frames written so far are kept in '{out}'")

    rc = proc.wait()
    print()
    if rc != 0:
        die(f"ffmpeg exited with code {rc}")
    print(f"{C_OK}Done:{C_RST} {out}")
    write_log(out, f"complete - {written} frames ({written / FPS:.1f}s)")


if __name__ == "__main__":
    main()
