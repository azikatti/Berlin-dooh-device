#!/usr/bin/env python3
"""VLC Playlist Player."""

import subprocess
import sys
from pathlib import Path

from config import BASE_DIR, get_device_id

# ============================================================================
# CONSTANTS
# ============================================================================

MEDIA_DIR = BASE_DIR / "media"
VLC = Path("/usr/bin/vlc")
VERSION = "1.9.0"  # Simplified: VLC picks up new playlist naturally on loop cycle


# ============================================================================
# MAIN PLAY FUNCTION
# ============================================================================

def play():
    """Play playlist with VLC."""
    device_id = get_device_id()
    print(f"Device: {device_id} (v{VERSION})")
    
    # Find playlist
    playlist = MEDIA_DIR / "playlist.m3u"
    if not playlist.exists():
        sys.exit("No playlist found. Run: python media_sync.py")
    
    print(f"Playing {playlist}")
    
    # VLC flags for Raspberry Pi (improved for headless/wayland)
    vlc_args = [
        str(VLC),
        "--intf", "dummy",              # Use dummy interface (no GUI)
        "--fullscreen",                 # Fullscreen video
        "--no-mouse-events",            # Ignore mouse
        "--no-keyboard-events",         # Ignore keyboard
        "--loop",                       # Loop playlist (will pick up new playlist on next cycle)
        "--quiet",                      # Suppress output
        "--no-osd",                     # Disable all on-screen display
        "--no-xlib",                    # Don't use X11 (for wayland/headless)
        "--aout", "alsa",               # Use ALSA audio (Raspberry Pi)
        str(playlist)
    ]
    
    # Run VLC (don't capture output - VLC needs to run in foreground to display)
    try:
        result = subprocess.run(
            vlc_args,
            stderr=subprocess.PIPE,  # Only capture stderr for error logging
            stdout=None,  # Let stdout go to console/display (VLC needs this)
            text=True,
            check=False
        )
        if result.returncode != 0:
            if result.stderr:
                print(f"VLC stderr: {result.stderr}", file=sys.stderr)
            sys.exit(f"VLC failed with exit code {result.returncode}")
    except Exception as e:
        print(f"Error running VLC: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    play()
