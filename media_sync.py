#!/usr/bin/env python3
"""Media Sync from Dropbox with safety measures. Usage: python media_sync.py"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from config import BASE_DIR, get_device_id, load_config, create_http_opener

# ============================================================================
# CONFIGURATION
# ============================================================================

config = load_config()

MEDIA_DIR = BASE_DIR / "media"
STAGING_DIR = BASE_DIR / ".media_staging"
BACKUP_DIR = BASE_DIR / ".media_backup"
SYNC_LOCK = Path("/tmp/vlc-sync.lock")
VLC_SERVICE = "vlc-player"

DROPBOX_URL = config["DROPBOX_URL"]
HEALTHCHECK_URL = config["HEALTHCHECK_URL"]
MAX_RETRIES = int(config["MAX_RETRIES"])
RETRY_DELAY = int(config["RETRY_DELAY"])

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

def get_healthcheck_url(device_id):
    """Get Healthchecks.io URL for device."""
    # Get check ID from map or extract from HEALTHCHECK_URL
    check_id = HEALTHCHECK_MAP.get(device_id)
    if not check_id and HEALTHCHECK_URL:
        try:
            check_id = HEALTHCHECK_URL.split("/")[-1]
        except (IndexError, AttributeError):
            check_id = ""
    
    return f"https://hc-ping.com/{check_id}" if check_id else ""


def check_disk_space(required_mb=500):
    """Check if enough disk space is available."""
    stat = shutil.disk_usage(BASE_DIR)
    free_mb = stat.free / (1024 * 1024)
    if free_mb < required_mb:
        raise Exception(f"Insufficient disk space: {free_mb:.0f}MB free, need {required_mb}MB")
    return True


def is_vlc_running():
    """Check if VLC process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "main.py play"],
            capture_output=True,
            timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False


def wait_for_vlc_release(timeout=30):
    """Wait for VLC to release file locks, or timeout."""
    print("Waiting for VLC to release file locks...")
    start = time.time()
    while time.time() - start < timeout:
        if not is_vlc_running():
            return True
        # Check if any files in media directory are locked
        try:
            result = subprocess.run(
                ["lsof", "+D", str(MEDIA_DIR)],
                capture_output=True,
                timeout=2
            )
            if result.returncode != 0:  # No locked files
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def restart_vlc_service():
    """Restart VLC service to load new playlist."""
    try:
        print("Restarting VLC service to load new playlist...")
        result = subprocess.run(
            ["sudo", "systemctl", "restart", VLC_SERVICE],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0:
            print("VLC service restarted ✓")
            return True
        else:
            print(f"Warning: Failed to restart VLC service: {result.stderr.decode()}")
            return False
    except Exception as e:
        print(f"Warning: Could not restart VLC service: {e}")
        return False


def download_with_retry():
    """Download from Dropbox with retry logic."""
    if not DROPBOX_URL or not DROPBOX_URL.strip():
        raise Exception("DROPBOX_URL is not configured in config.env")
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Downloading from Dropbox... (attempt {attempt}/{MAX_RETRIES})")
            if len(DROPBOX_URL) > 80:
                print(f"URL: {DROPBOX_URL[:80]}...")
            else:
                print(f"URL: {DROPBOX_URL}")
            
            opener = create_http_opener()
            req = Request(DROPBOX_URL, headers={"User-Agent": "Mozilla/5.0"})
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
                data = opener.open(req, timeout=300).read()
                # Verify ZIP integrity
                try:
                    zipfile.ZipFile(tempfile.BytesIO(data))
                except zipfile.BadZipFile:
                    raise Exception("Downloaded file is not a valid ZIP file")
                f.write(data)
                return Path(f.name)
        except Exception as e:
            print(f"  Failed: {e}")
            if "unknown url type" in str(e).lower():
                print("  Error: Invalid DROPBOX_URL format. Check config file.")
                raise
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"  Retrying in {wait // 60} minutes...")
                time.sleep(wait)
            else:
                raise Exception(f"Download failed after {MAX_RETRIES} attempts")


def validate_playlist(playlist_path, media_dir):
    """Validate playlist: check all files exist and filter out missing ones."""
    if not playlist_path.exists():
        return None
    
    lines = []
    valid_files = []
    for line in playlist_path.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            lines.append(line)
        else:
            # Extract filename from path
            file_path = Path(line)
            media_file = media_dir / file_path.name
            if media_file.exists():
                lines.append(str(media_file))
                valid_files.append(media_file.name)
            else:
                print(f"  Warning: Playlist references missing file: {file_path.name}")
    
    if not valid_files:
        raise Exception("No valid media files found in playlist")
    
    # Write validated playlist
    validated_playlist = playlist_path.parent / "playlist_local.m3u"
    validated_playlist.write_text("\n".join(lines))
    print(f"  Validated playlist: {len(valid_files)} files")
    return validated_playlist


def create_backup():
    """Create backup of current media directory."""
    if MEDIA_DIR.exists() and any(MEDIA_DIR.iterdir()):
        if BACKUP_DIR.exists():
            shutil.rmtree(BACKUP_DIR, ignore_errors=True)
        shutil.copytree(MEDIA_DIR, BACKUP_DIR, ignore_errors=True)
        print("Backup created ✓")
        return True
    return False


def restore_backup():
    """Restore media from backup if sync failed."""
    if BACKUP_DIR.exists() and any(BACKUP_DIR.iterdir()):
        print("Restoring from backup...")
        if MEDIA_DIR.exists():
            shutil.rmtree(MEDIA_DIR, ignore_errors=True)
        shutil.copytree(BACKUP_DIR, MEDIA_DIR, ignore_errors=True)
        print("Backup restored ✓")
        return True
    return False


# ============================================================================
# MAIN SYNC FUNCTION
# ============================================================================

def sync():
    """Download from Dropbox and safely swap media with all safety measures."""
    # Lock file to prevent concurrent syncs
    if SYNC_LOCK.exists():
        print("Sync already in progress, skipping...")
        return
    
    try:
        SYNC_LOCK.touch()
        
        device_id = get_device_id()
        print(f"=== Media Sync ===")
        print(f"Device: {device_id}")
        
        # Validate DROPBOX_URL
        if not DROPBOX_URL or DROPBOX_URL.strip() == "":
            print("Error: DROPBOX_URL not configured in config.env")
            sys.exit(1)
        
        # Check disk space
        print("Checking disk space...")
        check_disk_space(required_mb=500)
        
        # Create backup of current media
        print("Creating backup...")
        backup_created = create_backup()
        
        # Clean staging directory
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR, ignore_errors=True)
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        
        # Download and extract
        zip_path = download_with_retry()
        
        print("Extracting...")
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir() or info.filename.startswith("."):
                    continue
                parts = Path(info.filename).parts
                name = Path(*parts[1:]) if len(parts) > 1 else Path(info.filename)
                if name.name.startswith("."):
                    continue
                dest = STAGING_DIR / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(info))
                print(f"  {name.name}")
        zip_path.unlink()
        
        # Find and validate playlist
        print("Validating playlist...")
        playlist_found = False
        for m3u in STAGING_DIR.glob("*.m3u"):
            validated = validate_playlist(m3u, STAGING_DIR)
            if validated:
                playlist_found = True
                break
        
        if not playlist_found:
            raise Exception("No valid playlist found in downloaded content")
        
        # Wait for VLC to release files (if running)
        if is_vlc_running():
            print("VLC is running, waiting for file release...")
            if not wait_for_vlc_release(timeout=30):
                print("Warning: VLC still has files locked, proceeding anyway...")
        
        # Atomic swap: staging → media
        print("Performing atomic swap...")
        if MEDIA_DIR.exists():
            shutil.rmtree(MEDIA_DIR, ignore_errors=True)
        STAGING_DIR.rename(MEDIA_DIR)
        print(f"Media synced to {MEDIA_DIR} ✓")
        
        # Force VLC to reload new playlist
        if is_vlc_running():
            restart_vlc_service()
        else:
            print("VLC not running, will start on next play command")
        
        # Heartbeat ping
        try:
            ping_url = get_healthcheck_url(device_id)
            if ping_url:
                urlopen(ping_url, timeout=10)
                print(f"Heartbeat sent ✓ ({device_id})")
        except Exception as e:
            print(f"Heartbeat failed: {e}")
        
        print("=== Sync Complete ===")
        
    except Exception as e:
        print(f"=== Sync Failed: {e} ===")
        # Restore backup if sync failed
        if backup_created:
            print("Attempting to restore backup...")
            restore_backup()
        sys.exit(1)
    
    finally:
        SYNC_LOCK.unlink(missing_ok=True)
        # Clean up staging if it still exists (shouldn't after successful swap)
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR, ignore_errors=True)


if __name__ == "__main__":
    sync()

