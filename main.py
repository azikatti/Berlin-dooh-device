#!/usr/bin/env python3
"""VLC Playlist Player. Usage: python main.py play"""

import subprocess
import sys
from pathlib import Path

from config import BASE_DIR, get_device_id

# ============================================================================
# CONSTANTS
# ============================================================================

MEDIA_DIR = BASE_DIR / "media"
VLC = Path("/usr/bin/vlc")
VERSION = "1.5.0"  # Fixed: improved error handling, validation, and robustness


# ============================================================================
# MAIN PLAY FUNCTION
# ============================================================================

def play():
    """Play playlist with VLC."""
    device_id = get_device_id()
    print(f"Device: {device_id} (v{VERSION})")
    
    # Check if VLC is installed
    if not VLC.exists():
        sys.exit(f"Error: VLC not found at {VLC}. Please install VLC: sudo apt install vlc")
    
    playlist = MEDIA_DIR / "playlist_local.m3u"
    if not playlist.exists():
        playlist = next(MEDIA_DIR.glob("*.m3u"), None)
    if not playlist:
        sys.exit("No playlist found. Run: python media_sync.py")
    print(f"Playing {playlist}")
    
    # VLC flags for Raspberry Pi
    vlc_args = [
        str(VLC),
        "--intf", "dummy",              # Use dummy interface (no GUI, works with Wayland)
        "--fullscreen",                 # Fullscreen video
        "--no-mouse-events",            # Ignore mouse
        "--no-keyboard-events",         # Ignore keyboard
        "--loop",                       # Loop playlist
        "--quiet",                      # Suppress output
        "--no-osd",                     # Disable all on-screen display
        str(playlist)
    ]
    
    result = subprocess.run(vlc_args)
    if result.returncode != 0:
        sys.exit(f"VLC failed with exit code {result.returncode}")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "play"
    if cmd == "play":
        play()
    else:
        print("Usage: python main.py play")
        print("For sync, use: python media_sync.py")
        sys.exit(1)
