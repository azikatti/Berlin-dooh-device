#!/usr/bin/env python3
"""VLC Playlist Manager. Usage: python main.py [sync|play]"""

import shutil, socket, subprocess, sys, tempfile, time, zipfile
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

DROPBOX_URL = "https://www.dropbox.com/scl/fo/c98dl5jsxp3ae90yx9ww4/AD3YT1lVanI36T3pUaN_crU?rlkey=fzm1pc1qyhl4urkfo7kk3ftss&st=846rj2qj&dl=1"
HEALTHCHECK_URL = "https://hc-ping.com/da226e90-5bfd-4ada-9f12-71959e346ff1"
VERSION = "1.0.0"  # Update this when releasing
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
        from urllib.request import urlopen
        from urllib.parse import quote
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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    {"sync": sync, "play": play}.get(cmd, lambda: print("Usage: python main.py [sync|play]"))()
