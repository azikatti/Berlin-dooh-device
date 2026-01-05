#!/usr/bin/env python3
"""VLC Playlist Player."""

import os
import subprocess
import sys
from pathlib import Path

from config import BASE_DIR, get_device_id

# ============================================================================
# CONSTANTS
# ============================================================================

MEDIA_DIR = BASE_DIR / "media"
VLC = Path("/usr/bin/vlc")
VERSION = "1.6.0"  # Removed: backup functionality, simplified sync process


# ============================================================================
# MAIN PLAY FUNCTION
# ============================================================================

def play():
    """Play playlist with VLC."""
    # Debug mode
    DEBUG = os.environ.get("DEBUG", "0") == "1"
    
    device_id = get_device_id()
    print(f"Device: {device_id} (v{VERSION})")
    
    if DEBUG:
        print(f"DEBUG: VLC path: {VLC}")
        print(f"DEBUG: VLC exists: {VLC.exists()}")
        print(f"DEBUG: MEDIA_DIR: {MEDIA_DIR}")
        print(f"DEBUG: MEDIA_DIR exists: {MEDIA_DIR.exists()}")
        print(f"DEBUG: DISPLAY: {os.environ.get('DISPLAY', 'not set')}")
        print(f"DEBUG: XDG_RUNTIME_DIR: {os.environ.get('XDG_RUNTIME_DIR', 'not set')}")
    
    # Check if VLC is installed
    if not VLC.exists():
        sys.exit(f"Error: VLC not found at {VLC}. Please install VLC: sudo apt install vlc")
    
    # Try playlist.m3u first (the actual file)
    playlist = MEDIA_DIR / "playlist.m3u"
    if not playlist.exists():
        # Fallback to any .m3u file
        playlist = next(MEDIA_DIR.glob("*.m3u"), None)
    if not playlist:
        sys.exit("No playlist found. Run: python media_sync.py")
    
    if DEBUG:
        print(f"DEBUG: Playlist: {playlist}")
        print(f"DEBUG: Playlist exists: {playlist.exists()}")
    
    print(f"Playing {playlist}")
    
    # VLC flags for Raspberry Pi (improved for headless/wayland)
    vlc_args = [
        str(VLC),
        "--intf", "dummy",              # Use dummy interface (no GUI)
        "--fullscreen",                 # Fullscreen video
        "--no-mouse-events",            # Ignore mouse
        "--no-keyboard-events",         # Ignore keyboard
        "--loop",                       # Loop playlist
        "--quiet",                      # Suppress output
        "--no-osd",                     # Disable all on-screen display
        "--no-xlib",                    # Don't use X11 (for wayland/headless)
        "--aout", "alsa",               # Use ALSA audio (Raspberry Pi)
        str(playlist)
    ]
    
    if DEBUG:
        print(f"DEBUG: VLC command: {' '.join(vlc_args)}")
    
    # Run VLC with error capture
    try:
        result = subprocess.run(
            vlc_args,
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            print(f"VLC stderr: {result.stderr}", file=sys.stderr)
            print(f"VLC stdout: {result.stdout}", file=sys.stdout)
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
