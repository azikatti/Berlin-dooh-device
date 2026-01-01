#!/usr/bin/env python3
"""VLC Playlist Manager. Usage: python main.py [sync|play]"""

import shutil, subprocess, sys, tempfile, time, zipfile
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

DROPBOX_URL = "https://www.dropbox.com/scl/fo/c98dl5jsxp3ae90yx9ww4/AD3YT1lVanI36T3pUaN_crU?rlkey=fzm1pc1qyhl4urkfo7kk3ftss&st=846rj2qj&dl=1"
HEALTHCHECK_URL = "https://hc-ping.com/da226e90-5bfd-4ada-9f12-71959e346ff1"
BASE_DIR = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "media"
TEMP_DIR = BASE_DIR / ".media_temp"
VLC = Path("/Applications/VLC.app/Contents/MacOS/VLC") if sys.platform == "darwin" else Path("/usr/bin/vlc")

MAX_RETRIES = 3
RETRY_DELAY = 1800  # 30 minutes


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
    
    # Heartbeat ping
    try:
        from urllib.request import urlopen
        urlopen(HEALTHCHECK_URL, timeout=10)
        print("Heartbeat sent ✓")
    except Exception as e:
        print(f"Heartbeat failed: {e}")


def play():
    """Play playlist with VLC."""
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

