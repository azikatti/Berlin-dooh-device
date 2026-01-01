#!/bin/bash
# Auto-update script (runs via systemd timer or Dropbox trigger)
set -e

REPO="https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main"
DIR="/home/pi/vlc-player"
LOCK="/tmp/vlc-update.lock"

# Prevent concurrent updates
if [ -f "$LOCK" ]; then
    echo "Update already in progress, skipping..."
    exit 0
fi
touch "$LOCK"
trap "rm -f $LOCK" EXIT

echo "=== Updating VLC Player ==="

# Create directory
mkdir -p "$DIR/systemd"

# Download latest files
echo "Downloading latest code..."
curl -sSL "$REPO/main.py" -o "$DIR/main.py"
curl -sSL "$REPO/systemd/vlc-sync.service" -o "$DIR/systemd/vlc-sync.service"
curl -sSL "$REPO/systemd/vlc-sync.timer" -o "$DIR/systemd/vlc-sync.timer"
curl -sSL "$REPO/systemd/vlc-player.service" -o "$DIR/systemd/vlc-player.service"
curl -sSL "$REPO/systemd/vlc-update.service" -o "$DIR/systemd/vlc-update.service"
curl -sSL "$REPO/systemd/vlc-update.timer" -o "$DIR/systemd/vlc-update.timer"
curl -sSL "$REPO/update.sh" -o "$DIR/update.sh"

# Set permissions
chmod +x "$DIR/main.py"
chmod +x "$DIR/update.sh"
chown -R pi:pi "$DIR"

# Update systemd services
echo "Updating systemd services..."
cp "$DIR/systemd/"*.service "$DIR/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload

# Restart services
echo "Restarting services..."
systemctl restart vlc-player vlc-sync.timer
systemctl restart vlc-update.timer 2>/dev/null || systemctl enable --now vlc-update.timer

echo "Update complete!"

