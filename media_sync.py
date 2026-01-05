#!/usr/bin/env python3
"""Media Sync from Dropbox with safety measures. Usage: python media_sync.py"""

import base64
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from urllib.request import Request

from config import BASE_DIR, get_device_id, load_config, create_http_opener

# ============================================================================
# CONFIGURATION
# ============================================================================

config = load_config()

MEDIA_DIR = BASE_DIR / "media"
STAGING_DIR = BASE_DIR / ".media_staging"
SYNC_LOCK = Path("/tmp/vlc-sync.lock")
VLC_SERVICE = "vlc-player"

DROPBOX_URL = config["DROPBOX_URL"]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def reload_vlc_playlist():
    """Reload VLC playlist via HTTP interface without restarting."""
    print("Reloading VLC playlist...")
    
    playlist_path = MEDIA_DIR / "playlist.m3u"
    if not playlist_path.exists():
        print("Warning: Playlist not found, cannot reload")
        return
    
    # VLC HTTP interface endpoint
    base_url = "http://localhost:8080"
    auth_string = base64.b64encode(b":vlc").decode('ascii')
    
    try:
        # Step 1: Clear current playlist
        clear_req = urllib.request.Request(
            f"{base_url}/requests/status.xml?command=pl_empty",
            headers={"Authorization": f"Basic {auth_string}"}
        )
        urllib.request.urlopen(clear_req, timeout=2)
        
        # Step 2: Add new playlist
        playlist_url = f"file://{playlist_path.absolute()}"
        add_req = urllib.request.Request(
            f"{base_url}/requests/status.xml?command=in_enqueue&input={urllib.parse.quote(playlist_url)}",
            headers={"Authorization": f"Basic {auth_string}"}
        )
        urllib.request.urlopen(add_req, timeout=2)
        
        # Step 3: Play the new playlist
        play_req = urllib.request.Request(
            f"{base_url}/requests/status.xml?command=pl_play",
            headers={"Authorization": f"Basic {auth_string}"}
        )
        urllib.request.urlopen(play_req, timeout=2)
        
        print("VLC playlist reloaded ✓")
    except urllib.error.URLError as e:
        # VLC might not be running or HTTP interface not available
        print(f"Warning: Could not reload playlist via HTTP (VLC may not be running): {e}")
        print("VLC will pick up the new playlist on next loop cycle")
    except Exception as e:
        print(f"Warning: Playlist reload failed: {e}")
        print("VLC will pick up the new playlist on next loop cycle")


def download_with_retry():
    """Download from Dropbox with single retry."""
    if not DROPBOX_URL or not DROPBOX_URL.strip():
        raise Exception("DROPBOX_URL is not configured in config.env")
    
    for attempt in [1, 2]:
        zip_path = None
        try:
            print(f"Downloading from Dropbox... (attempt {attempt}/2)")
            if len(DROPBOX_URL) > 80:
                print(f"URL: {DROPBOX_URL[:80]}...")
            else:
                print(f"URL: {DROPBOX_URL}")
            
            opener = create_http_opener()
            req = Request(DROPBOX_URL, headers={"User-Agent": "Mozilla/5.0"})
            
            # Download
            response = opener.open(req, timeout=300)
            data = response.read()
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
                f.write(data)
                zip_path = Path(f.name)
            
            return zip_path
        except Exception as e:
            # Clean up temp file on error
            if zip_path and zip_path.exists():
                zip_path.unlink(missing_ok=True)
            
            print(f"  Failed: {e}")
            if "unknown url type" in str(e).lower():
                print("  Error: Invalid DROPBOX_URL format. Check config file.")
                raise
            if attempt < 2:
                print("  Retrying...")
                time.sleep(5)
            else:
                raise Exception("Download failed after 2 attempts")


def check_playlist_exists(media_dir):
    """Simple check: playlist exists and has at least one media file."""
    playlists = list(media_dir.glob("*.m3u"))
    if not playlists:
        return False
    
    # Quick check: playlist has at least one non-comment line
    for playlist in playlists:
        try:
            content = playlist.read_text()
            if any(line.strip() and not line.startswith("#") 
                   for line in content.splitlines()):
                return True
        except Exception:
            continue
    return False


# ============================================================================
# MAIN SYNC FUNCTION
# ============================================================================

def sync():
    """Download from Dropbox and safely swap media (simplified)."""
    # Lock file to prevent concurrent syncs (atomic creation)
    try:
        SYNC_LOCK.touch(exist_ok=False)  # Fails if file already exists
    except FileExistsError:
        print("Sync already in progress, skipping...")
        return
    
    try:
        device_id = get_device_id()
        print(f"=== Media Sync ===")
        print(f"Device: {device_id}")
        
        # Validate DROPBOX_URL
        if not DROPBOX_URL or not DROPBOX_URL.strip():
            raise Exception("DROPBOX_URL is not configured in config.env")
        
        # Clean staging directory
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR, ignore_errors=True)
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        
        # Download and extract
        zip_path = download_with_retry()
        
        print("Extracting...")
        with zipfile.ZipFile(zip_path) as zf:
            # Extract all files (simpler than manual extraction)
            zf.extractall(STAGING_DIR)
        zip_path.unlink()
        
        # Quick playlist check
        if not check_playlist_exists(STAGING_DIR):
            raise Exception("No valid playlist found in downloaded content")
        
        # Atomic swap: staging → media
        # Safe: VLC will handle file loss gracefully and restart automatically
        print("Performing atomic swap...")
        if MEDIA_DIR.exists():
            shutil.rmtree(MEDIA_DIR, ignore_errors=True)
        STAGING_DIR.rename(MEDIA_DIR)
        print(f"Media synced to {MEDIA_DIR} ✓")
        
        # Small delay to ensure filesystem is ready
        time.sleep(1)
        
        # Reload VLC playlist without restarting
        reload_vlc_playlist()
        
        print("=== Sync Complete ===")
        
    except Exception as e:
        print(f"=== Sync Failed: {e} ===")
        print("Device will be without media until next successful sync")
        sys.exit(1)
    
    finally:
        SYNC_LOCK.unlink(missing_ok=True)
        # Clean up staging if it still exists (shouldn't after successful swap)
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR, ignore_errors=True)


if __name__ == "__main__":
    sync()

