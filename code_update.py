#!/usr/bin/env python3
"""Code update script for VLC Player. Checks GitHub and updates code if new version available."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from http.cookiejar import CookieJar
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config():
    """Load configuration from /etc/vlc-player/config or environment."""
    config_file = Path("/etc/vlc-player/config")
    
    if config_file.exists():
        for line in config_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()
    
    return {
        "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", ""),
    }

config = load_config()

# GitHub repo setup
GITHUB_TOKEN = config["GITHUB_TOKEN"]
REPO_OWNER = "azikatti"
REPO_NAME = "Berlin-dooh-device"
REPO_BRANCH = "main"

if GITHUB_TOKEN:
    REPO = f"https://{GITHUB_TOKEN}@raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"
else:
    REPO = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"

BASE_DIR = Path(__file__).parent

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

# ============================================================================
# UPDATE FUNCTION
# ============================================================================

def update():
    """Check GitHub for code updates and install if new version available."""
    lock_file = Path("/tmp/vlc-update.lock")
    
    # Prevent concurrent updates
    if lock_file.exists():
        print("Update already in progress, skipping...")
        return
    
    try:
        lock_file.touch()
        
        print("=== Checking for code updates ===")
        
        # Get current version
        current_version = get_version_from_file(BASE_DIR / "main.py")
        print(f"Current version: {current_version}")
        
        # Get GitHub version (with cache-busting)
        try:
            opener = build_opener(HTTPCookieProcessor(CookieJar()), HTTPRedirectHandler())
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
            if "401" in str(e) or "403" in str(e):
                print("Authentication failed. Is GITHUB_TOKEN set in config?")
            return
        
        print(f"GitHub version: {github_version}")
        
        # Compare versions
        if current_version == github_version:
            print(f"Already up to date (v{current_version})")
            return
        
        print(f"Update available: {current_version} -> {github_version}")
        print("=== Updating VLC Player Code ===")
        
        # Create directory
        systemd_dir = BASE_DIR / "systemd"
        systemd_dir.mkdir(parents=True, exist_ok=True)
        
        # Download latest files - ALL code files
        print("Downloading latest code...")
        files_to_download = [
            ("main.py", BASE_DIR / "main.py"),
            ("bootstrap.sh", BASE_DIR / "bootstrap.sh"),
            ("config.env", BASE_DIR / "config.env"),
            ("code_update.py", BASE_DIR / "code_update.py"),  # Include itself
            ("systemd/vlc-maintenance.service", systemd_dir / "vlc-maintenance.service"),
            ("systemd/vlc-maintenance.timer", systemd_dir / "vlc-maintenance.timer"),
            ("systemd/vlc-player.service", systemd_dir / "vlc-player.service"),
        ]
        
        for remote_path, local_path in files_to_download:
            try:
                # Add cache-busting to force fresh download
                cache_buster = int(time.time())
                req = Request(
                    f"{REPO}/{remote_path}?t={cache_buster}",
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache"
                    }
                )
                content = opener.open(req, timeout=30).read()
                local_path.write_bytes(content)
                print(f"  Downloaded {remote_path}")
            except Exception as e:
                print(f"  Failed to download {remote_path}: {e}")
                if "401" in str(e) or "403" in str(e):
                    print("    Authentication failed. Check GITHUB_TOKEN in config.")
        
        # Set permissions for executable files
        (BASE_DIR / "main.py").chmod(0o755)
        (BASE_DIR / "bootstrap.sh").chmod(0o755)
        (BASE_DIR / "code_update.py").chmod(0o755)
        
        # Update system config file if config.env was downloaded
        print("Updating system config...")
        if (BASE_DIR / "config.env").exists():
            # Create directory if it doesn't exist (requires sudo)
            subprocess.run(["sudo", "mkdir", "-p", "/etc/vlc-player"], check=False)
            
            # Copy config file (requires sudo)
            subprocess.run(["sudo", "cp", str(BASE_DIR / "config.env"), "/etc/vlc-player/config"], check=False)
            subprocess.run(["sudo", "chmod", "600", "/etc/vlc-player/config"], check=False)
            subprocess.run(["sudo", "chown", "root:root", "/etc/vlc-player/config"], check=False)
            print("  Config file updated ✓")
        
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
        
        print("Code update complete!")
        
    finally:
        lock_file.unlink(missing_ok=True)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    update()

