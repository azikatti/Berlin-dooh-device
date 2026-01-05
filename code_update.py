#!/usr/bin/env python3
"""Code update script for VLC Player. Checks GitHub and updates code if new version available."""

import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import Request

from config import BASE_DIR, load_config, create_http_opener

# ============================================================================
# CONFIGURATION
# ============================================================================

config = load_config()

# GitHub repo setup (public repo - no authentication required)
REPO_OWNER = config["GITHUB_REPO_OWNER"]
REPO_NAME = config["GITHUB_REPO_NAME"]
REPO_BRANCH = config["GITHUB_REPO_BRANCH"]

# Use public repo URL (no authentication required)
REPO = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_version_from_file(file_path):
    """Extract VERSION constant from Python file."""
    try:
        content = file_path.read_text()
        match = re.search(r'VERSION\s*=\s*"([^"]+)"', content)
        return match.group(1) if match else "unknown"
    except Exception:
        return "unknown"


def compare_versions(v1, v2):
    """Compare semantic versions. Returns: -1 if v1 < v2, 0 if equal, 1 if v1 > v2."""
    def version_tuple(v):
        """Convert version string to tuple of integers."""
        try:
            parts = v.split('.')
            return tuple(int(p) for p in parts)
        except (ValueError, AttributeError):
            return None
    
    t1 = version_tuple(v1)
    t2 = version_tuple(v2)
    
    if t1 is None or t2 is None:
        # Fallback to string comparison if not semantic version
        if v1 < v2:
            return -1
        elif v1 > v2:
            return 1
        return 0
    
    if t1 < t2:
        return -1
    elif t1 > t2:
        return 1
    return 0

# ============================================================================
# UPDATE FUNCTION
# ============================================================================

def update(force=False):
    """Check GitHub for code updates and install if new version available.
    
    Args:
        force: If True, skip version check and force update
    """
    lock_file = Path("/tmp/vlc-update.lock")
    
    # Prevent concurrent updates (atomic creation)
    try:
        lock_file.touch(exist_ok=False)  # Fails if file already exists
    except FileExistsError:
        print("Update already in progress, skipping...")
        return
    
    try:
        
        print("=== Checking for code updates ===")
        
        # Get current version
        current_version = get_version_from_file(BASE_DIR / "main.py")
        print(f"Current version: {current_version}")
        
        # Get GitHub version (with cache-busting)
        try:
            opener = create_http_opener()
            cache_buster = int(time.time())
            req = Request(
                f"{REPO}/main.py?t={cache_buster}",
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache"
                }
            )
            github_content = opener.open(req, timeout=30).read().decode('utf-8')
            github_version = re.search(r'VERSION\s*=\s*"([^"]+)"', github_content)
            github_version = github_version.group(1) if github_version else "unknown"
        except Exception as e:
            print(f"Failed to fetch GitHub version: {e}")
            return
        
        print(f"GitHub version: {github_version}")
        
        # Compare versions (semantic versioning) - skip if force
        if not force:
            version_diff = compare_versions(current_version, github_version)
            if version_diff >= 0:
                print(f"Already up to date (v{current_version})")
                return
            
            print(f"Update available: {current_version} -> {github_version}")
        else:
            print(f"Force update requested (current: v{current_version}, GitHub: v{github_version})")
        
        print("=== Updating VLC Player Code ===")
        
        # Create directory
        systemd_dir = BASE_DIR / "systemd"
        systemd_dir.mkdir(parents=True, exist_ok=True)
        
        # Download latest files - ALL code files
        print("Downloading latest code...")
        
        files_to_download = [
            ("main.py", BASE_DIR / "main.py"),
            ("config.py", BASE_DIR / "config.py"),
            ("media_sync.py", BASE_DIR / "media_sync.py"),
            ("bootstrap.sh", BASE_DIR / "bootstrap.sh"),
            ("stop_vlc.sh", BASE_DIR / "stop_vlc.sh"),
            ("config.env", BASE_DIR / "config.env"),
            ("code_update.py", BASE_DIR / "code_update.py"),  # Include itself
            ("systemd/vlc-maintenance.service", systemd_dir / "vlc-maintenance.service"),
            ("systemd/vlc-maintenance.timer", systemd_dir / "vlc-maintenance.timer"),
            ("systemd/vlc-player.service", systemd_dir / "vlc-player.service"),
        ]
        
        # Use single cache-buster timestamp for all downloads in this update
        cache_buster = int(time.time())
        
        for remote_path, local_path in files_to_download:
            try:
                # Add cache-busting to force fresh download
                req = Request(
                    f"{REPO}/{remote_path}?t={cache_buster}",
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache"
                    }
                )
                
                # Download
                content = opener.open(req, timeout=30).read()
                local_path.write_bytes(content)
                print(f"  Downloaded {remote_path}")
            except Exception as e:
                print(f"  Failed to download {remote_path}: {e}")
        
        # Set permissions for executable files
        (BASE_DIR / "main.py").chmod(0o755)
        (BASE_DIR / "config.py").chmod(0o755)
        (BASE_DIR / "media_sync.py").chmod(0o755)
        (BASE_DIR / "bootstrap.sh").chmod(0o755)
        (BASE_DIR / "stop_vlc.sh").chmod(0o755)
        (BASE_DIR / "code_update.py").chmod(0o755)
        
        # Config file is now local - no need to copy to /etc
        if (BASE_DIR / "config.env").exists():
            print("  Config file updated locally ✓")
        
        # Update systemd services
        print("Updating systemd services...")
        try:
            from config import setup_systemd_services
            setup_systemd_services()
            print("  Systemd services updated ✓")
        except Exception as e:
            print(f"  Warning: Failed to update systemd services: {e}")
            print("  Services may still have placeholders - run bootstrap.sh to fix")
            # Don't fail the entire update, but warn the user
        
        # Restart services
        print("Restarting services...")
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "vlc-player", "vlc-maintenance.timer"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        if result.returncode != 0:
            print(f"  Warning: Service restart failed: {result.stderr.strip() if result.stderr else 'Unknown error'}")
            print("  Services may need manual restart")
        
        print("Code update complete!")
        
    finally:
        lock_file.unlink(missing_ok=True)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv or "-f" in sys.argv
    update(force=force)

