#!/usr/bin/env python3
"""VLC Playlist Manager. Usage: python main.py [sync|play|update]"""

# ============================================================================
# IMPORTS
# ============================================================================
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
from urllib.parse import quote

# ============================================================================
# CONFIGURATION
# ============================================================================
DROPBOX_URL = "https://www.dropbox.com/scl/fo/c98dl5jsxp3ae90yx9ww4/AD3YT1lVanI36T3pUaN_crU?rlkey=fzm1pc1qyhl4urkfo7kk3ftss&st=846rj2qj&dl=1"
HEALTHCHECK_URL = "https://hc-ping.com/da226e90-5bfd-4ada-9f12-71959e346ff1"
VERSION = "1.0.0"  # Update this when releasing
REPO = "https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main"

BASE_DIR = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "media"
TEMP_DIR = BASE_DIR / ".media_temp"
VLC = Path("/Applications/VLC.app/Contents/MacOS/VLC") if sys.platform == "darwin" else Path("/usr/bin/vlc")

MAX_RETRIES = 3
RETRY_DELAY = 1800  # 30 minutes

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
    config_file = BASE_DIR / ".device"
    if config_file.exists():
        for line in config_file.read_text().splitlines():
            if line.startswith("DEVICE_ID="):
                return line.split("=", 1)[1].strip()
    return socket.gethostname()


def get_healthcheck_url(device_id):
    """Get Healthchecks.io URL for device, or use default."""
    check_id = HEALTHCHECK_MAP.get(device_id, HEALTHCHECK_URL.split("/")[-1])
    return f"https://hc-ping.com/{check_id}"


def download_with_retry():
    """Download from Dropbox with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Downloading... (attempt {attempt}/{MAX_RETRIES})")
            opener = build_opener(HTTPCookieProcessor(CookieJar()), HTTPRedirectHandler())
            req = Request(DROPBOX_URL, headers={"User-Agent": "Mozilla/5.0"})
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
                f.write(opener.open(req, timeout=300).read())
                return Path(f.name)
        except Exception as e:
            print(f"  Failed: {e}")
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"  Retrying in {wait // 60} minutes...")
                time.sleep(wait)
            else:
                raise Exception(f"Download failed after {MAX_RETRIES} attempts")


def get_version_from_file(file_path):
    """Extract VERSION constant from Python file."""
    try:
        content = file_path.read_text()
        match = re.search(r'VERSION\s*=\s*"([^"]+)"', content)
        return match.group(1) if match else "unknown"
    except Exception:
        return "unknown"


# ============================================================================
# MAIN COMMANDS
# ============================================================================

def sync():
    """Download from Dropbox and atomic swap."""
    device_id = get_device_id()
    print(f"Device: {device_id}")
    
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
        ping_url = f"{get_healthcheck_url(device_id)}?rid={quote(device_id)}"
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
    subprocess.run([str(VLC), "--loop", str(playlist)])


def update():
    """Check GitHub for code updates and install if new version available."""
    lock_file = Path("/tmp/vlc-update.lock")
    
    # Prevent concurrent updates
    if lock_file.exists():
        print("Update already in progress, skipping...")
        return
    
    try:
        lock_file.touch()
        
        print("=== Checking for updates ===")
        
        # Get current version
        current_version = get_version_from_file(BASE_DIR / "main.py")
        print(f"Current version: {current_version}")
        
        # Get GitHub version
        try:
            opener = build_opener(HTTPCookieProcessor(CookieJar()), HTTPRedirectHandler())
            req = Request(f"{REPO}/main.py", headers={"User-Agent": "Mozilla/5.0"})
            github_content = opener.open(req, timeout=30).read().decode('utf-8')
            github_version = re.search(r'VERSION\s*=\s*"([^"]+)"', github_content)
            github_version = github_version.group(1) if github_version else "unknown"
        except Exception as e:
            print(f"Failed to fetch GitHub version: {e}")
            return
        
        print(f"GitHub version: {github_version}")
        
        # Compare versions
        if current_version == github_version:
            print(f"Already up to date (v{current_version})")
            return
        
        print(f"Update available: {current_version} -> {github_version}")
        print("=== Updating VLC Player ===")
        
        # Create directory
        systemd_dir = BASE_DIR / "systemd"
        systemd_dir.mkdir(parents=True, exist_ok=True)
        
        # Download latest files
        print("Downloading latest code...")
        files_to_download = [
            ("main.py", BASE_DIR / "main.py"),
            ("systemd/vlc-maintenance.service", systemd_dir / "vlc-maintenance.service"),
            ("systemd/vlc-maintenance.timer", systemd_dir / "vlc-maintenance.timer"),
            ("systemd/vlc-player.service", systemd_dir / "vlc-player.service"),
        ]
        
        for remote_path, local_path in files_to_download:
            try:
                req = Request(f"{REPO}/{remote_path}", headers={"User-Agent": "Mozilla/5.0"})
                content = opener.open(req, timeout=30).read()
                local_path.write_bytes(content)
                print(f"  Downloaded {remote_path}")
            except Exception as e:
                print(f"  Failed to download {remote_path}: {e}")
        
        # Set permissions
        (BASE_DIR / "main.py").chmod(0o755)
        
        # Update systemd services
        print("Updating systemd services...")
        for file in systemd_dir.glob("*.service"):
            subprocess.run(["sudo", "cp", str(file), "/etc/systemd/system/"], check=False)
        for file in systemd_dir.glob("*.timer"):
            subprocess.run(["sudo", "cp", str(file), "/etc/systemd/system/"], check=False)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=False)
        
        # Restart services
        print("Restarting services...")
        subprocess.run(["sudo", "systemctl", "restart", "vlc-player", "vlc-maintenance.timer"], check=False)
        
        # Save version to file for tracking
        version_file = BASE_DIR / ".version"
        version_file.write_text(github_version)
        print(f"Version saved: {github_version}")
        
        print("Update complete!")
        
    finally:
        lock_file.unlink(missing_ok=True)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    commands = {
        "sync": sync,
        "play": play,
        "update": update,
    }
    func = commands.get(cmd, lambda: print("Usage: python main.py [sync|play|update]"))
    func()
