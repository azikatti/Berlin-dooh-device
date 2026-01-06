#!/bin/bash
# Migrate existing device to git-based VLC player setup
# Run as: sudo ./migrate_to_git.sh

set -e

# --- Detect user/home/dir -----------------------------------------------------
if [ -n "$SUDO_USER" ]; then
  USER="$SUDO_USER"
elif [ "$USER" != "root" ] && [ -n "$USER" ]; then
  # Already running as a non-root user
  USER="$USER"
else
  # Running as root, try to detect the actual user
  # First try to get the user from the process that invoked sudo
  USER=$(logname 2>/dev/null || echo "")
  if [ -z "$USER" ] || [ "$USER" = "root" ]; then
    # Fallback: find first non-root user with UID >= 1000
    USER=$(getent passwd | awk -F: '$3 >= 1000 && $1 != "nobody" {print $1; exit}')
    [ -z "$USER" ] && USER="pi"
  fi
fi

# Get the actual home directory for this user (don't assume /home/$USER)
HOME_DIR=$(getent passwd "$USER" | cut -d: -f6)
if [ -z "$HOME_DIR" ] || [ ! -d "$HOME_DIR" ]; then
  # Fallback to /home/$USER if getent fails
  HOME_DIR="/home/$USER"
fi

NEW_DIR="$HOME_DIR/vlc-player"
BACKUP_DIR="$HOME_DIR/vlc-player-old-$(date +%Y%m%d-%H%M%S)"

echo "=== VLC Player Migration ==="
echo "User:        $USER"
echo "Home:        $HOME_DIR"
echo "New install: $NEW_DIR"
echo "Backup:      $BACKUP_DIR"
echo

# 1) Stop old services (best-effort)
echo "[1/4] Stopping existing services (if any)..."
systemctl stop vlc-player vlc-maintenance.timer 2>/dev/null || true

# 2) Backup existing install
if [ -d "$NEW_DIR" ]; then
  echo "[2/4] Backing up existing vlc-player to: $BACKUP_DIR"
  mv "$NEW_DIR" "$BACKUP_DIR"
else
  echo "[2/4] No existing vlc-player directory, skipping backup."
  BACKUP_DIR=""
fi

# 3) Run new git-based bootstrap from GitHub
echo "[3/4] Running new bootstrap.sh from GitHub..."
curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash

# 4) Restore config.env and media (if backup exists)
echo "[4/4] Restoring config and media (if backup exists)..."

if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
  # Restore config.env
  if [ -f "$BACKUP_DIR/config.env" ]; then
    echo "  - Restoring config.env from backup"
    cp "$BACKUP_DIR/config.env" "$NEW_DIR/config.env"
  else
    echo "  - No config.env in backup, keeping new default"
  fi

  # Restore media
  if [ -d "$BACKUP_DIR/media" ]; then
    echo "  - Restoring media/ from backup"
    rm -rf "$NEW_DIR/media"
    cp -r "$BACKUP_DIR/media" "$NEW_DIR/media"
  else
    echo "  - No media/ in backup, will rely on next sync"
  fi
else
  echo "  - No backup directory, nothing to restore"
fi

# Restart services to pick up restored config/media
echo
echo "Restarting services..."
systemctl restart vlc-player vlc-maintenance.timer || true

echo
echo "=== Migration Complete ==="
echo "New install: $NEW_DIR"
[ -n "$BACKUP_DIR" ] && echo "Backup:      $BACKUP_DIR"


