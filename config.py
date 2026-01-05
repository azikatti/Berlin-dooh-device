#!/usr/bin/env python3
"""Shared configuration utilities for VLC Player scripts."""

import os
import socket
from pathlib import Path
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler

# ============================================================================
# CONSTANTS
# ============================================================================

BASE_DIR = Path(__file__).parent

# ============================================================================
# CONFIGURATION FUNCTIONS
# ============================================================================

def load_config():
    """Load configuration from local config.env file.
    
    Returns a dictionary with all configuration values.
    Missing values will be empty strings or defaults.
    """
    config_file = BASE_DIR / "config.env"
    content = ""
    
    if config_file.exists():
        try:
            content = config_file.read_text()
        except Exception as e:
            print(f"Warning: Could not read config file: {e}")
    
    # Parse config content and set environment variables
    if content:
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()
    
    # Return all config values
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


def get_device_id():
    """Get device ID from config or fall back to hostname.
    
    Returns:
        str: Device ID from config, or hostname if not configured.
    """
    device_id = os.environ.get("DEVICE_ID", "")
    return device_id if device_id else socket.gethostname()


def create_http_opener():
    """Create HTTP opener with cookie and redirect handling.
    
    Returns:
        OpenerDirector: Configured opener for HTTP requests.
    """
    return build_opener(HTTPCookieProcessor(CookieJar()), HTTPRedirectHandler())


def setup_systemd_services():
    """Replace placeholders in systemd service files and install them.
    
    This function:
    1. Detects the actual user (reads from existing service first, then detects)
    2. Uses BASE_DIR as the installation directory
    3. Replaces __USER__ and __DIR__ placeholders with atomic writes
    4. Copies files to /etc/systemd/system/ with error checking
    5. Reloads systemd daemon
    
    Returns:
        tuple: (actual_user, actual_dir) for reference
        
    Raises:
        Exception: If service setup fails at any step
    """
    import getpass
    import subprocess
    import re
    
    # 1. Try to read from existing service first (most reliable)
    actual_user = None
    actual_dir = None
    
    existing_service = Path("/etc/systemd/system/vlc-player.service")
    if existing_service.exists():
        try:
            content = existing_service.read_text()
            user_match = re.search(r'User=([^\n]+)', content)
            dir_match = re.search(r'WorkingDirectory=([^\n]+)', content)
            if user_match and dir_match:
                actual_user = user_match.group(1).strip()
                actual_dir = dir_match.group(1).strip()
                print(f"  Using existing service config: user={actual_user}, dir={actual_dir}")
        except Exception as e:
            print(f"  Warning: Could not read existing service: {e}")
    
    # 2. Fallback to detection if reading failed
    if not actual_user:
        if os.getenv("SUDO_USER"):
            actual_user = os.getenv("SUDO_USER")
        else:
            try:
                detected_user = getpass.getuser()
                if detected_user == "root":
                    # Replicate bootstrap.sh logic: find first non-root user
                    try:
                        import pwd
                        for user in pwd.getpwall():
                            if user.pw_uid >= 1000 and user.pw_name != "nobody":
                                actual_user = user.pw_name
                                break
                    except (ImportError, Exception):
                        pass
                
                if not actual_user:
                    actual_user = detected_user if detected_user != "root" else "user"
            except Exception:
                actual_user = "user"  # Final fallback
        
        print(f"  Detected user: {actual_user}")
    
    if not actual_dir:
        actual_dir = str(BASE_DIR)
        print(f"  Using directory: {actual_dir}")
    
    # 3. Validate paths exist
    systemd_dir = BASE_DIR / "systemd"
    if not systemd_dir.exists():
        raise Exception(f"Systemd directory not found: {systemd_dir}")
    
    # 4. Process service files with atomic writes (idempotent)
    processed_files = []
    for service_file in sorted(systemd_dir.glob("*.service")):
        try:
            content = service_file.read_text()
            
            # Skip if already processed (no placeholders) - makes function idempotent
            if "__USER__" not in content and "__DIR__" not in content:
                print(f"  Skipping {service_file.name} (already processed)")
                continue
            
            # Replace placeholders
            content = content.replace("__USER__", actual_user)
            content = content.replace("__DIR__", actual_dir)
            
            # Validate replacement worked
            if "__USER__" in content or "__DIR__" in content:
                raise Exception(f"Placeholders not fully replaced in {service_file.name}")
            
            # Write to temp file first (atomic operation)
            temp_file = service_file.with_suffix('.service.tmp')
            temp_file.write_text(content)
            temp_file.replace(service_file)  # Atomic move
            processed_files.append(service_file)
            print(f"  Processed {service_file.name}")
        except Exception as e:
            print(f"  Error processing {service_file.name}: {e}")
            raise
    
    # 5. Copy to systemd with error checking and timeouts
    errors = []
    for file in sorted(systemd_dir.glob("*.service")):
        try:
            result = subprocess.run(
                ["sudo", "cp", str(file), "/etc/systemd/system/"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                errors.append(f"Failed to copy {file.name}: {error_msg}")
            else:
                print(f"  Installed {file.name}")
        except subprocess.TimeoutExpired:
            errors.append(f"Timeout copying {file.name}")
        except Exception as e:
            errors.append(f"Error copying {file.name}: {e}")
    
    for file in sorted(systemd_dir.glob("*.timer")):
        try:
            result = subprocess.run(
                ["sudo", "cp", str(file), "/etc/systemd/system/"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                errors.append(f"Failed to copy {file.name}: {error_msg}")
            else:
                print(f"  Installed {file.name}")
        except subprocess.TimeoutExpired:
            errors.append(f"Timeout copying {file.name}")
        except Exception as e:
            errors.append(f"Error copying {file.name}: {e}")
    
    if errors:
        error_summary = "; ".join(errors)
        raise Exception(f"Service installation errors: {error_summary}")
    
    # 6. Reload systemd with error checking
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise Exception(f"Failed to reload systemd: {error_msg}")
        print("  Systemd daemon reloaded ✓")
    except subprocess.TimeoutExpired:
        raise Exception("Timeout reloading systemd daemon")
    except Exception as e:
        raise Exception(f"Error reloading systemd: {e}")
    
    return actual_user, actual_dir

