#!/usr/bin/env python3
"""
dmake_watch.py - Monitors doommake --auto-build-verbose output and beeps on build results.

Usage:
    python dmake_watch.py [extra doommake args...]
    
Press Ctrl+C to stop monitoring and kill doommake.
"""

import subprocess
import sys
import winsound
import threading
import time
import signal
import shutil

# ── Beep definitions ────────────────────────────────────────────────────────
def beep_success():
    """Ascending happy beep."""
    winsound.Beep(600, 100)
    winsound.Beep(800, 100)
    winsound.Beep(1000, 200)

def beep_failure():
    """Descending sad beep."""
    winsound.Beep(600, 200)
    winsound.Beep(400, 400)

# ── Strings to watch for ─────────────────────────────────────────────────────
SUCCESS_STRING = "Build Ended: Success"
FAILURE_STRING = "Build Ended: Failed"

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    # Resolve doommake to its full path so we don't need shell=True
    doommake = shutil.which("doommake")
    if not doommake:
        print("[dmake_watch] ERROR: 'doommake' not found on PATH.")
        sys.exit(1)

    extra_args = sys.argv[1:]
    cmd = [doommake, "--auto-build-verbose"] + extra_args

    print(f"[dmake_watch] Starting: {' '.join(cmd)}")
    print("[dmake_watch] Press Ctrl+C to stop.\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    stop_event = threading.Event()

    def stream_output():
        for line in proc.stdout:
            if stop_event.is_set():
                break
            print(line, end="", flush=True)
            if SUCCESS_STRING in line:
                threading.Thread(target=beep_success, daemon=True).start()
            elif FAILURE_STRING in line:
                threading.Thread(target=beep_failure, daemon=True).start()

    output_thread = threading.Thread(target=stream_output, daemon=True)
    output_thread.start()

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[dmake_watch] Ctrl+C received, stopping doommake...")
        stop_event.set()
        proc.send_signal(signal.CTRL_C_EVENT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    proc.stdout.close()
    output_thread.join(timeout=2)
    print("[dmake_watch] Stopped.")

if __name__ == "__main__":
    main()