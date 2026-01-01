#!/bin/bash
# VLC Player Install for Raspberry Pi. Run: sudo ./install.sh
set -e

DIR="/home/pi/vlc-player"

# Prompt for device ID if not provided
if [ -z "$DEVICE_ID" ]; then
    read -p "Enter device ID (e.g., berlin-01): " DEVICE_ID
fi

if [ -z "$DEVICE_ID" ]; then
    echo "Error: Device ID is required"
    exit 1
fi

echo "Setting up device: $DEVICE_ID"

# Set hostname
hostnamectl set-hostname "$DEVICE_ID"

# Copy files
mkdir -p "$DIR/systemd"
cp main.py "$DIR/"
if [ -f "update.sh" ]; then
    cp update.sh "$DIR/"
    chmod +x "$DIR/update.sh"
fi
cp systemd/*.service systemd/*.timer "$DIR/systemd/" 2>/dev/null || true
chmod +x "$DIR/main.py"

# Save device config
echo "DEVICE_ID=$DEVICE_ID" > "$DIR/.device"
chown pi:pi "$DIR/.device"

# Install systemd services
cp systemd/*.service systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable vlc-sync.timer vlc-player vlc-update.timer
systemctl start vlc-sync.timer vlc-player vlc-update.timer

# Install watchdog cron (restarts if Python or VLC dies)
WATCHDOG='*/5 * * * * (pgrep -f "main.py play" && pgrep -x vlc) || systemctl restart vlc-player'
(crontab -u pi -l 2>/dev/null | grep -v "vlc-player"; echo "$WATCHDOG") | crontab -u pi -

echo ""
echo "Installed! Device: $DEVICE_ID"
echo "Commands:"
echo "  systemctl status vlc-player"
echo "  python3 $DIR/main.py sync"
