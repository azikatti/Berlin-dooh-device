#!/usr/bin/env python3
"""
Git-based code update for VLC Player.

Forces the local repo to match origin/main and restarts services.
Intended to be run by a systemd timer every N hours, or manually.
"""

import subprocess
from pathlib import Path

from config import BASE_DIR


def run(cmd, check: bool = True) -> int:
    """Run a shell command with basic logging."""
    print(f"+ {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def update() -> None:
    """Force-sync local repo to origin/main and restart services."""
    repo_dir: Path = BASE_DIR

    print("=== Forced git-based code update ===")
    print(f"Repo dir: {repo_dir}")

    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        raise SystemExit(f"Not a git repository: {repo_dir} (no .git directory)")

    # Fetch latest changes and hard reset to origin/main (forced update)
    run(["git", "-C", str(repo_dir), "fetch", "origin"])
    run(["git", "-C", str(repo_dir), "reset", "--hard", "origin/main"])

    # Set display rotation in boot config (vertical screen; takes effect after reboot)
    script = repo_dir / "scripts" / "apply_display_rotation.sh"
    if script.exists():
        subprocess.run(["sudo", str(script)], check=False)

    # Restart services to pick up new code
    # Adjust service names if they ever change
    run(["sudo", "systemctl", "restart", "vlc-player"])
    run(["sudo", "systemctl", "restart", "vlc-maintenance.timer"])

    print("=== Code update complete ===")


if __name__ == "__main__":
    update()