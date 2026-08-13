#!/usr/bin/env python3
"""
voladjust - adjust the global volume of a WAV file.

Two independent modes:
  -vol N          scale amplitude to N% of the original
  -m REF.wav      match the input's loudness (RMS) to a reference WAV

Pure standard library. No external dependencies.
"""

import os
import sys
import math
import wave
import struct

VERSION = "1.0"
SUFFIX = "_volAdjusted"


# ----------------------------------------------------------------------------
# colour / help
# ----------------------------------------------------------------------------

def _supports_colour():
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            return False
    return True


_C = _supports_colour()


def c(code, text):
    return "\033[%sm%s\033[0m" % (code, text) if _C else text


BOLD = lambda s: c("1", s)
TITLE = lambda s: c("1;36", s)
HEAD = lambda s: c("1;36", s)
FLAG = lambda s: c("92", s)
REQ = lambda s: c("93", s)
DIM = lambda s: c("90", s)
ERR = lambda s: c("91", s)
OK = lambda s: c("92", s)


def show_help():
    p = print
    p("")
    p(TITLE("voladjust v%s" % VERSION) + DIM("  -  global volume adjustment for WAV files"))
    p("")
    p(HEAD("USAGE"))
    p("  voladjust input.wav -vol N   [-o out.wav | --same] [--clip]")
    p("  voladjust input.wav -m REF   [-o out.wav | --same]")
    p("")
    p(HEAD("VOLUME MODE") + DIM("   -  scale by a straight percentage"))
    p("  %s %s   %s" % (FLAG("-vol, --volume N"), REQ("(required)"),
                        DIM("target volume as a % of the original")))
    p("      %s" % DIM("75 = 25% quieter   150 = 50% louder   100 = unchanged"))
    p("  %s              %s" % (FLAG("--clip"),
                                DIM("allow clipping; without it the gain is clamped")))
    p("      %s" % DIM("to the loudest value that does not clip"))
    p("")
    p(HEAD("MATCH MODE") + DIM("    -  match the loudness of another WAV"))
    p("  %s %s   %s" % (FLAG("-m, --match REF.wav"), REQ("(required)"),
                        DIM("match input's RMS loudness to REF")))
    p("      %s" % DIM("for seamless playback in sequence; gain is always"))
    p("      %s" % DIM("clamped so the result never clips"))
    p("")
    p(HEAD("OUTPUT") + DIM("        -  shared by both modes"))
    p("  %s       %s" % (FLAG("-o, --output FILE"), DIM("write the result to FILE")))
    p("  %s                  %s" % (FLAG("--same"), DIM("overwrite the input file in place")))
    p("  %s" % DIM("(neither)               write <stem>%s.wav beside the input" % SUFFIX))
    p("")
    p(HEAD("NOTES"))
    p("  %s" % DIM("-vol and -m are mutually exclusive; exactly one is required."))
    p("  %s" % DIM("-o and --same are mutually exclusive."))
    p("  %s" % DIM("Bit depth, sample rate and channel count are preserved exactly."))
    p("  %s" % DIM("Supports 8-bit unsigned and 16/24/32-bit signed PCM WAV."))
    p("  %s" % DIM("Match mode uses RMS, not peak - it levels perceived loudness"))
    p("  %s" % DIM("rather than transients, which is what avoids audible jumps."))
    p("")
    p(HEAD("EXAMPLES"))
    p("  %s" % DIM("voladjust test.wav -vol 75"))
    p("      %s" % DIM("-> test%s.wav at 75%% volume" % SUFFIX))
    p("  %s" % DIM("voladjust test.wav -vol 500"))
    p("      %s" % DIM("-> boosted as far as it can go without clipping"))
    p("  %s" % DIM("voladjust test.wav -vol 500 --clip"))
    p("      %s" % DIM("-> full 500%, samples saturate at the format limits"))
    p("  %s" % DIM("voladjust dsbossit.wav -vol 90 --same"))
    p("      %s" % DIM("-> overwrites dsbossit.wav in place"))
    p("  %s" % DIM("voladjust newsound.wav -m dspistol.wav -o dsnew.wav"))
    p("      %s" % DIM("-> newsound matched to dspistol's loudness"))
    p("")


# ----------------------------------------------------------------------------
# sample codec
# ----------------------------------------------------------------------------

def sample_range(sampwidth):
    """Signed min/max for a given sample width in bytes."""
    bits = sampwidth * 8
    return -(1 << (bits - 1)), (1 << (bits - 1)) - 1


def decode(raw, sampwidth):
    """Raw frame bytes -> list of signed ints (8-bit unsigned is centred)."""
    if sampwidth == 1:
        return [b - 128 for b in raw]
    if sampwidth == 2:
        return list(struct.unpack("<%dh" % (len(raw) // 2), raw))
    if sampwidth == 4:
        return list(struct.unpack("<%di" % (len(raw) // 4), raw))
    if sampwidth == 3:
        out = []
        for i in range(0, len(raw), 3):
            v = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if v & 0x800000:
                v -= 0x1000000
            out.append(v)
        return out
    raise ValueError("unsupported sample width: %d byte(s)" % sampwidth)


def encode(samples, sampwidth):
    """Signed ints -> raw frame bytes, saturating at the format limits."""
    lo, hi = sample_range(sampwidth)
    clamped = [lo if s < lo else (hi if s > hi else s) for s in samples]

    if sampwidth == 1:
        return bytes(s + 128 for s in clamped)
    if sampwidth == 2:
        return struct.pack("<%dh" % len(clamped), *clamped)
    if sampwidth == 4:
        return struct.pack("<%di" % len(clamped), *clamped)
    if sampwidth == 3:
        out = bytearray()
        for s in clamped:
            v = s & 0xFFFFFF
            out.append(v & 0xFF)
            out.append((v >> 8) & 0xFF)
            out.append((v >> 16) & 0xFF)
        return bytes(out)
    raise ValueError("unsupported sample width: %d byte(s)" % sampwidth)


def read_wav(path):
    """-> (params, samples)"""
    try:
        with wave.open(path, "rb") as w:
            params = w.getparams()
            if params.comptype != "NONE":
                die("'%s' is compressed (%s); only uncompressed PCM is supported."
                    % (path, params.comptype))
            raw = w.readframes(params.nframes)
    except wave.Error as e:
        die("could not read '%s': %s" % (path, e))
    except OSError as e:
        die("could not open '%s': %s" % (path, e))
    return params, decode(raw, params.sampwidth)


def write_wav(path, params, samples):
    tmp = path + ".voladjust.tmp"
    try:
        with wave.open(tmp, "wb") as w:
            w.setnchannels(params.nchannels)
            w.setsampwidth(params.sampwidth)
            w.setframerate(params.framerate)
            w.writeframes(encode(samples, params.sampwidth))
        os.replace(tmp, path)
    except OSError as e:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        die("could not write '%s': %s" % (path, e))


# ----------------------------------------------------------------------------
# analysis
# ----------------------------------------------------------------------------

def rms(samples):
    if not samples:
        return 0.0
    total = 0
    for s in samples:
        total += s * s
    return math.sqrt(total / len(samples))


def max_clean_gain(samples, sampwidth):
    """Largest gain that keeps every sample inside the format range."""
    lo, hi = sample_range(sampwidth)
    peak_pos = max(samples) if samples else 0
    peak_neg = min(samples) if samples else 0

    limits = []
    if peak_pos > 0:
        limits.append(hi / peak_pos)
    if peak_neg < 0:
        limits.append(lo / peak_neg)
    if not limits:
        return float("inf")
    return min(limits)


def apply_gain(samples, gain):
    """Round-half-away-from-zero, matching typical audio editor behaviour."""
    out = []
    for s in samples:
        v = s * gain
        out.append(int(math.floor(v + 0.5)) if v >= 0 else int(math.ceil(v - 0.5)))
    return out


# ----------------------------------------------------------------------------
# cli
# ----------------------------------------------------------------------------

def die(msg):
    print("%s %s" % (ERR("error:"), msg), file=sys.stderr)
    sys.exit(1)


def parse_args(argv):
    a = {
        "input": None,
        "vol": None,
        "match": None,
        "output": None,
        "same": False,
        "clip": False,
    }

    i = 0
    while i < len(argv):
        tok = argv[i]
        low = tok.lower()
        norm = low.lstrip("-") if tok.startswith("-") else None

        if norm in ("vol", "volume"):
            i += 1
            if i >= len(argv):
                die("%s requires a percentage value." % tok)
            try:
                a["vol"] = float(argv[i])
            except ValueError:
                die("'%s' is not a valid percentage for %s." % (argv[i], tok))
        elif norm in ("m", "match"):
            i += 1
            if i >= len(argv):
                die("%s requires a reference WAV file." % tok)
            a["match"] = argv[i]
        elif norm in ("o", "output"):
            i += 1
            if i >= len(argv):
                die("%s requires a filename." % tok)
            a["output"] = argv[i].strip('"')
        elif norm == "same":
            a["same"] = True
        elif norm == "clip":
            a["clip"] = True
        elif tok.startswith("-"):
            die("unknown option '%s'  (try -help)" % tok)
        else:
            if a["input"] is not None:
                die("unexpected extra argument '%s' - only one input file is accepted." % tok)
            a["input"] = tok.strip('"')
        i += 1

    return a


def resolve_output(inpath, args):
    if args["same"]:
        return inpath
    if args["output"]:
        return args["output"]
    stem, ext = os.path.splitext(inpath)
    return stem + SUFFIX + (ext if ext else ".wav")


def main(argv):
    if any(t.lower().lstrip("-") in ("h", "help", "?") for t in argv if t.startswith("-")):
        show_help()
        return 0
    if not argv:
        show_help()
        return 1

    args = parse_args(argv)

    # --- validation --------------------------------------------------------
    if not args["input"]:
        die("no input WAV file given.  (try -help)")
    if args["vol"] is None and args["match"] is None:
        die("one of -vol or -m is required.  (try -help)")
    if args["vol"] is not None and args["match"] is not None:
        die("-vol and -m are mutually exclusive - use one or the other.")
    if args["output"] and args["same"]:
        die("-o and --same are mutually exclusive.")
    if args["vol"] is not None and args["vol"] < 0:
        die("volume percentage cannot be negative.")
    if args["clip"] and args["match"]:
        print("%s --clip has no effect in match mode; match gain is always clamped."
              % c("93", "note:"))
    if not os.path.isfile(args["input"]):
        die("input file not found: '%s'" % args["input"])

    params, samples = read_wav(args["input"])
    if not samples:
        die("'%s' contains no audio frames." % args["input"])

    outpath = resolve_output(args["input"], args)

    # --- work out the gain -------------------------------------------------
    if args["vol"] is not None:
        mode = "vol"
        requested = args["vol"] / 100.0
    else:
        mode = "match:%s" % os.path.basename(args["match"])
        if not os.path.isfile(args["match"]):
            die("reference file not found: '%s'" % args["match"])
        ref_params, ref_samples = read_wav(args["match"])
        if not ref_samples:
            die("reference '%s' contains no audio frames." % args["match"])

        in_rms = rms(samples)
        ref_rms = rms(ref_samples)
        if in_rms == 0:
            die("'%s' is silent - there is nothing to scale up to the reference."
                % args["input"])
        if ref_rms == 0:
            die("reference '%s' is silent - cannot match to it." % args["match"])

        # RMS is scale-free across bit depths only after normalising each
        # file against its own full-scale range.
        _, in_hi = sample_range(params.sampwidth)
        _, ref_hi = sample_range(ref_params.sampwidth)
        requested = (ref_rms / ref_hi) / (in_rms / in_hi)

    # --- clamp unless clipping was explicitly allowed ----------------------
    clamped = False
    applied = requested
    if not (mode == "vol" and args["clip"]):
        ceiling = max_clean_gain(samples, params.sampwidth)
        if applied > ceiling:
            applied = ceiling
            clamped = True

    out_samples = apply_gain(samples, applied)
    write_wav(outpath, params, out_samples)

    # --- report ------------------------------------------------------------
    tag = c("96", "[voladjust]")
    req_s = "%.1f%%" % (requested * 100)
    app_s = "%.1f%%" % (applied * 100)
    line = "%s %s | %s | requested: %s | applied: %s | -> %s" % (
        tag, os.path.basename(args["input"]), mode,
        req_s, OK(app_s) if not clamped else c("93", app_s),
        outpath)
    print(line)
    if clamped:
        why = "clamped to avoid clipping" if mode == "vol" else "clamped to avoid clipping"
        print("  %s %s" % (c("93", "note:"), DIM(why)))
    if args["same"]:
        print("  %s %s" % (c("93", "note:"), DIM("original file overwritten in place")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\naborted.", file=sys.stderr)
        sys.exit(130)
