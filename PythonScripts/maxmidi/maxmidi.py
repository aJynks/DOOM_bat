"""
midi_volume.py - Scale volume of a MIDI file while preserving relative balance.

Usage:
    python midi_volume.py input.mid <percent>   # scale by percentage
    python midi_volume.py input.mid --max       # hard-set everything to 127
    python midi_volume.py input.mid --full      # hard-set everything to 100 (GM default)

Examples:
    python midi_volume.py song.mid 200    # twice as loud
    python midi_volume.py song.mid 50     # half as loud
    python midi_volume.py song.mid --max  # absolute maximum (127)
    python midi_volume.py song.mid --full # GM default ceiling (100)

Output: input_<label>.mid  (e.g. song_200pct.mid, song_max.mid, song_full.mid)

Scales:
    - CC7  (Channel Volume)
    - CC11 (Expression)
    - Note velocity

If velocities are already maxed (all at 127) and scaling UP, falls back to
CC7 injection to gain headroom within the MIDI spec.
All values clamped to 1-127 (0 = silence/note-off, so floor is 1).
"""

import sys
import os
import subprocess

# ── dependency check ──────────────────────────────────────────────────────────
try:
    import mido
except ImportError:
    print("mido not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mido", "--break-system-packages", "-q"])
    import mido
# ─────────────────────────────────────────────────────────────────────────────

VOLUME_CCS = {7, 11}


def clamp(value: int) -> int:
    return max(1, min(127, value))


def analyze_midi(mid: mido.MidiFile):
    velocities = []
    channel_cc7  = {}
    channel_cc11 = {}
    for track in mid.tracks:
        for msg in track:
            if hasattr(msg, 'channel'):
                ch = msg.channel
                if msg.type == 'control_change':
                    if msg.control == 7:
                        channel_cc7[ch] = msg.value
                    elif msg.control == 11:
                        channel_cc11[ch] = msg.value
                elif msg.type == 'note_on' and msg.velocity > 0:
                    velocities.append(msg.velocity)
    return velocities, channel_cc7, channel_cc11


def get_active_channels(mid: mido.MidiFile):
    channels = set()
    for track in mid.tracks:
        for msg in track:
            if msg.type in ('note_on', 'note_off') and hasattr(msg, 'channel'):
                channels.add(msg.channel)
    return channels


def scale_midi_volume(input_path: str, percent: float, label: str) -> str:
    """
    percent : the scale factor as a percentage (e.g. 150 = 1.5x)
    label   : suffix for output filename (e.g. "150pct", "max", "full")

    When percent is None, hard_value must be set via the mode flags handled in main().
    """
    factor = percent / 100.0

    mid = mido.MidiFile(input_path)
    velocities, existing_cc7, existing_cc11 = analyze_midi(mid)

    all_maxed  = velocities and all(v == 127 for v in velocities)
    has_cc7    = bool(existing_cc7)
    has_cc11   = bool(existing_cc11)
    inject_cc7 = all_maxed and factor > 1.0

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"Input : {input_path}")
    print(f"Scale : {percent}%  (factor: {factor:.4f})")
    print()
    print("── Analysis ──────────────────────────────────────────────────")
    if velocities:
        print(f"  Velocity range : {min(velocities)}–{max(velocities)}  (avg {sum(velocities)/len(velocities):.1f}, {len(velocities)} notes)")
    print(f"  CC7  present   : {'yes, channels ' + str(sorted(existing_cc7.keys())) if has_cc7 else 'no  (GM default = 100 on all channels)'}")
    print(f"  CC11 present   : {'yes, channels ' + str(sorted(existing_cc11.keys())) if has_cc11 else 'no  (GM default = 127 on all channels)'}")
    print()

    if inject_cc7:
        print("── Strategy: CC7 INJECTION ───────────────────────────────────")
        print("  All note velocities are already at 127 (maxed).")
        print("  Velocity scaling would have no effect upward.")
        print("  Injecting CC7 (channel volume) messages instead.")
        print()
    else:
        print("── Strategy: VELOCITY + CC SCALING ───────────────────────────")
        if all_maxed and factor < 1.0:
            print("  All velocities maxed, but scaling DOWN — velocity scaling applied.")
        print()

    # ── Build output ──────────────────────────────────────────────────────────
    out = mido.MidiFile(type=mid.type, ticks_per_beat=mid.ticks_per_beat)
    active_channels   = get_active_channels(mid)
    injected_channels = set()

    cc7_scaled   = 0
    cc7_injected = 0
    cc11_scaled  = 0
    vel_scaled   = 0
    vel_clamped  = 0

    for track in mid.tracks:
        new_track = mido.MidiTrack()
        out.tracks.append(new_track)

        for msg in track:
            # ── CC7 injection before first note on each channel ───────────────
            if inject_cc7 and msg.type in ('note_on', 'note_off') and hasattr(msg, 'channel'):
                ch = msg.channel
                if ch in active_channels and ch not in injected_channels:
                    base_cc7 = existing_cc7.get(ch, 100)
                    new_cc7  = clamp(round(base_cc7 * factor))
                    new_track.append(mido.Message('control_change', channel=ch,
                                                  control=7, value=new_cc7, time=0))
                    injected_channels.add(ch)
                    cc7_injected += 1

            # ── Scale existing CC7 / CC11 ─────────────────────────────────────
            if msg.type == 'control_change' and msg.control in VOLUME_CCS:
                new_val = clamp(round(msg.value * factor))
                if msg.control == 7:
                    cc7_scaled += 1
                else:
                    cc11_scaled += 1
                new_track.append(msg.copy(value=new_val))

            # ── Scale velocity ────────────────────────────────────────────────
            elif msg.type == 'note_on' and msg.velocity > 0:
                if inject_cc7:
                    new_track.append(msg)  # velocity untouched when using CC7 injection
                else:
                    new_vel = clamp(round(msg.velocity * factor))
                    if new_vel != msg.velocity:
                        vel_scaled += 1
                    if round(msg.velocity * factor) > 127:
                        vel_clamped += 1
                    new_track.append(msg.copy(velocity=new_vel))

            else:
                new_track.append(msg)

    # ── Save ──────────────────────────────────────────────────────────────────
    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_{label}{ext}"
    out.save(output_path)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("── Results ───────────────────────────────────────────────────")
    if inject_cc7:
        print(f"  CC7 injected on {cc7_injected} channel(s) : {sorted(injected_channels)}")
        for ch in sorted(injected_channels):
            base_val = existing_cc7.get(ch, 100)
            new_val  = clamp(round(base_val * factor))
            clamped  = " (clamped — at maximum)" if round(base_val * factor) > 127 else ""
            print(f"    ch {ch:2d}: {base_val} → {new_val}{clamped}")
        if cc7_scaled:
            print(f"  Existing CC7 events also scaled : {cc7_scaled}")
    else:
        print(f"  CC7  events scaled     : {cc7_scaled}")
        print(f"  CC11 events scaled     : {cc11_scaled}")
        print(f"  Velocity events scaled : {vel_scaled}")
        if vel_clamped:
            print(f"  ⚠  Velocities clamped to 127   : {vel_clamped} notes (headroom lost)")

    print(f"\nOutput: {output_path}")
    return output_path


def hard_set_volume(input_path: str, target: int, label: str) -> str:
    """
    Hard-set ALL CC7, CC11, and velocity events to a fixed value.
    Also injects CC7 on any channel that doesn't have one.
    Preserves relative balance is intentionally NOT a goal here —
    this is a blunt force override, used for --max and --full.
    """
    mid = mido.MidiFile(input_path)
    velocities, existing_cc7, existing_cc11 = analyze_midi(mid)
    active_channels = get_active_channels(mid)

    print(f"Input  : {input_path}")
    print(f"Mode   : hard-set all volume to {target}")
    print()
    print("── Analysis ──────────────────────────────────────────────────")
    if velocities:
        print(f"  Velocity range : {min(velocities)}–{max(velocities)}  (avg {sum(velocities)/len(velocities):.1f}, {len(velocities)} notes)")
    print(f"  CC7  present   : {'yes, channels ' + str(sorted(existing_cc7.keys())) if existing_cc7 else 'no  (GM default = 100)'}")
    print(f"  CC11 present   : {'yes, channels ' + str(sorted(existing_cc11.keys())) if existing_cc11 else 'no  (GM default = 127)'}")
    print()
    print(f"── Strategy: HARD SET to {target} ────────────────────────────────")
    print(f"  All CC7, CC11, and velocity → {target}")
    print()

    out = mido.MidiFile(type=mid.type, ticks_per_beat=mid.ticks_per_beat)
    injected_channels = set()
    cc7_set  = 0
    cc11_set = 0
    vel_set  = 0
    cc7_inj  = 0

    for track in mid.tracks:
        new_track = mido.MidiTrack()
        out.tracks.append(new_track)

        for msg in track:
            # Inject CC7 before first note on channels that have no CC7
            if msg.type in ('note_on', 'note_off') and hasattr(msg, 'channel'):
                ch = msg.channel
                if ch in active_channels and ch not in injected_channels and ch not in existing_cc7:
                    new_track.append(mido.Message('control_change', channel=ch,
                                                  control=7, value=target, time=0))
                    injected_channels.add(ch)
                    cc7_inj += 1

            if msg.type == 'control_change' and msg.control == 7:
                new_track.append(msg.copy(value=target))
                cc7_set += 1
            elif msg.type == 'control_change' and msg.control == 11:
                new_track.append(msg.copy(value=target))
                cc11_set += 1
            elif msg.type == 'note_on' and msg.velocity > 0:
                new_track.append(msg.copy(velocity=target))
                vel_set += 1
            else:
                new_track.append(msg)

    base, ext = os.path.splitext(input_path)
    output_path = f"{base}_{label}{ext}"
    out.save(output_path)

    print("── Results ───────────────────────────────────────────────────")
    if cc7_inj:
        print(f"  CC7 injected (no prior CC7) : {cc7_inj} channel(s) → {target}")
    print(f"  CC7  events set to {target} : {cc7_set}")
    print(f"  CC11 events set to {target} : {cc11_set}")
    print(f"  Velocity events set to {target} : {vel_set}")
    print(f"\nOutput: {output_path}")
    return output_path


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python midi_volume.py <input.mid> <percent>   # e.g. 150 = 150%")
        print("  python midi_volume.py <input.mid> --max       # hard-set everything to 127")
        print("  python midi_volume.py <input.mid> --full      # hard-set everything to 100")
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.isfile(input_path):
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    flag = sys.argv[2]

    if flag == "--max":
        hard_set_volume(input_path, target=127, label="max")

    elif flag == "--full":
        hard_set_volume(input_path, target=100, label="full")

    else:
        try:
            percent = float(flag)
        except ValueError:
            print(f"Error: expected a percent value or --max / --full, got: {flag}")
            sys.exit(1)
        if percent <= 0:
            print("Error: percent must be greater than 0")
            sys.exit(1)
        pct_str = str(int(percent)) if percent == int(percent) else str(percent).replace('.', '_')
        scale_midi_volume(input_path, percent, label=f"{pct_str}pct")


if __name__ == "__main__":
    main()