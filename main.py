#!/usr/bin/env python3
"""VLC Playlist Manager. Usage: python main.py [sync|play]"""

# ============================================================================
# IMPORTS
# ============================================================================
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler, urlopen

# ============================================================================
# CONFIGURATION - Load from config file
# ============================================================================

def load_config():
    """Load configuration from /etc/vlc-player/config or environment."""
    config_file = Path("/etc/vlc-player/config")
    content = ""
    
    if config_file.exists():
        try:
            # Try to read config file directly
            content = config_file.read_text()
        except PermissionError:
            # If permission denied, use sudo to read (only for reading, not execution)
            try:
                result = subprocess.run(
                    ["sudo", "cat", str(config_file)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False
                )
                if result.returncode == 0:
                    content = result.stdout
                else:
                    # Fall back to local config.env if available
                    local_config = Path(__file__).parent / "config.env"
                    if local_config.exists():
                        print("Warning: Cannot read system config, using local config.env")
                        content = local_config.read_text()
            except Exception as e:
                # Fall back to local config.env if available
                local_config = Path(__file__).parent / "config.env"
                if local_config.exists():
                    print("Warning: Cannot read system config, using local config.env")
                    content = local_config.read_text()
        except Exception as e:
            print(f"Warning: Could not read config file: {e}")
    
    # Parse config content
    if content:
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()
    
    # Get values from environment (set by config file or systemd)
    return {
        "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", ""),
        "GITHUB_REPO_OWNER": os.environ.get("GITHUB_REPO_OWNER", "azikatti"),
        "GITHUB_REPO_NAME": os.environ.get("GITHUB_REPO_NAME", "Berlin-dooh-device"),
        "GITHUB_REPO_BRANCH": os.environ.get("GITHUB_REPO_BRANCH", "main"),
        "DROPBOX_URL": os.environ.get("DROPBOX_URL", ""),
        "HEALTHCHECK_URL": os.environ.get("HEALTHCHECK_URL", ""),
        "DEVICE_ID": os.environ.get("DEVICE_ID", ""),
        "MAX_RETRIES": os.environ.get("MAX_RETRIES", "3"),
        "RETRY_DELAY": os.environ.get("RETRY_DELAY", "1800"),
    }

config = load_config()

# Use config values
DROPBOX_URL = config["DROPBOX_URL"]
HEALTHCHECK_URL = config["HEALTHCHECK_URL"]
VERSION = "1.0.10"  # Code version (not config)

# GitHub repo setup
GITHUB_TOKEN = config["GITHUB_TOKEN"]
REPO_OWNER = config["GITHUB_REPO_OWNER"]
REPO_NAME = config["GITHUB_REPO_NAME"]
REPO_BRANCH = config["GITHUB_REPO_BRANCH"]

if GITHUB_TOKEN:
    REPO = f"https://{GITHUB_TOKEN}@raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"
else:
    REPO = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"

BASE_DIR = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "media"
TEMP_DIR = BASE_DIR / ".media_temp"
VLC = Path("/usr/bin/vlc")

MAX_RETRIES = int(config["MAX_RETRIES"])
RETRY_DELAY = int(config["RETRY_DELAY"])  # seconds

# Device to Healthchecks.io mapping
HEALTHCHECK_MAP = {
    "Device1": "b7f24740-19de-4c83-9398-b4fbfdd213ec",
    "Device2": "da226e90-5bfd-4ada-9f12-71959e346ff1",
    "Device3": "7a0a7b43-dbbc-4d0f-89d0-f2bb21df5eb9",
    "Device4": "523f5911-d774-40df-a033-d1cf40e8cd40",
    "Device5": "df591d60-bfcc-46da-b061-72b58e9ec9d3",
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_device_id():
    """Get device ID from config file or fall back to hostname."""
    # Get from config (loaded via EnvironmentFile in systemd)
    device_id = os.environ.get("DEVICE_ID", "")
    
    if device_id:
        return device_id
    
    # Fallback to hostname
    return socket.gethostname()


def get_healthcheck_url(device_id):
    """Get Healthchecks.io URL for device, or use default."""
    check_id = HEALTHCHECK_MAP.get(device_id, HEALTHCHECK_URL.split("/")[-1])
    return f"https://hc-ping.com/{check_id}"


def download_with_retry():
    """Download from Dropbox with retry logic."""
    if not DROPBOX_URL or not DROPBOX_URL.strip():
        raise Exception("DROPBOX_URL is not configured in /etc/vlc-player/config")
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Downloading from Dropbox... (attempt {attempt}/{MAX_RETRIES})")
            if len(DROPBOX_URL) > 80:
                print(f"URL: {DROPBOX_URL[:80]}...")
            else:
                print(f"URL: {DROPBOX_URL}")
            
            opener = build_opener(HTTPCookieProcessor(CookieJar()), HTTPRedirectHandler())
            req = Request(DROPBOX_URL, headers={"User-Agent": "Mozilla/5.0"})
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
                f.write(opener.open(req, timeout=300).read())
                return Path(f.name)
        except Exception as e:
            print(f"  Failed: {e}")
            if "unknown url type" in str(e).lower() or "unknown url" in str(e).lower():
                print("  Error: Invalid DROPBOX_URL format. Check config file.")
                print(f"  Current URL: {DROPBOX_URL}")
                print("  URL should start with http:// or https://")
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"  Retrying in {wait // 60} minutes...")
                time.sleep(wait)
            else:
                raise Exception(f"Download failed after {MAX_RETRIES} attempts")


# ============================================================================
# MAIN COMMANDS
# ============================================================================

def sync():
    """Download from Dropbox and atomic swap."""
    device_id = get_device_id()
    print(f"Device: {device_id}")
    
    # Validate DROPBOX_URL is set
    if not DROPBOX_URL or DROPBOX_URL.strip() == "":
        print("Error: DROPBOX_URL not configured in /etc/vlc-player/config")
        print("Please set DROPBOX_URL in the config file")
        sys.exit(1)
    
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(parents=True)
    
    zip_path = download_with_retry()
    
    print("Extracting...")
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.filename.startswith("."): continue
            parts = Path(info.filename).parts
            name = Path(*parts[1:]) if len(parts) > 1 else Path(info.filename)
            if name.name.startswith("."): continue
            dest = TEMP_DIR / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(info))
            print(f"  {name.name}")
    zip_path.unlink()
    
    # Create local playlist
    for m3u in TEMP_DIR.glob("*.m3u"):
        lines = []
        for line in m3u.read_text().splitlines():
            if line.startswith("#") or not line.strip():
                lines.append(line)
            else:
                lines.append(str(MEDIA_DIR / Path(line).name))
        (TEMP_DIR / "playlist_local.m3u").write_text("\n".join(lines))
        break
    
    # Atomic swap
    shutil.rmtree(MEDIA_DIR, ignore_errors=True)
    TEMP_DIR.rename(MEDIA_DIR)
    print(f"Synced to {MEDIA_DIR}")
    
    # Heartbeat ping with device-specific check
    try:
        ping_url = get_healthcheck_url(device_id)
        urlopen(ping_url, timeout=10)
        print(f"Heartbeat sent ✓ ({device_id})")
    except Exception as e:
        print(f"Heartbeat failed: {e}")


def play():
    """Play playlist with VLC."""
    device_id = get_device_id()
    version_file = BASE_DIR / ".version"
    current_version = version_file.read_text().strip() if version_file.exists() else VERSION
    print(f"Device: {device_id} (v{current_version})")
    
    playlist = MEDIA_DIR / "playlist_local.m3u"
    if not playlist.exists():
        playlist = next(MEDIA_DIR.glob("*.m3u"), None)
    if not playlist:
        sys.exit("No playlist found. Run: python main.py sync")
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
    
    subprocess.run(vlc_args)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    commands = {
        "sync": sync,
        "play": play,
    }
    func = commands.get(cmd, lambda: print("Usage: python main.py [sync|play]"))
    func()
