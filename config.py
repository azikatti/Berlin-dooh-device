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

