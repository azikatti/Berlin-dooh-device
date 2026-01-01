#!/bin/bash
# Bootstrap VLC Player for Raspberry Pi
# Run: curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash
# Or with device ID: curl ... | sudo DEVICE_ID=berlin-01 bash
set -e

REPO="https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main"
DIR="/home/pi/vlc-player"

echo "=== VLC Player Bootstrap ==="

# Prompt for device ID if not provided
if [ -z "$DEVICE_ID" ]; then
    read -p "Enter device ID (e.g., berlin-01): " DEVICE_ID
fi

if [ -z "$DEVICE_ID" ]; then
    echo "Error: Device ID is required"
    exit 1
fi

echo "Setting up device: $DEVICE_ID"

# Set system hostname
echo "Setting hostname to $DEVICE_ID..."
hostnamectl set-hostname "$DEVICE_ID"

# Install VLC if missing
if ! command -v vlc &> /dev/null; then
    echo "Installing VLC..."
    apt update && apt install -y vlc
fi

# Create directory
mkdir -p "$DIR/systemd"

# Download files
echo "Downloading files..."
curl -sSL "$REPO/main.py" -o "$DIR/main.py"
curl -sSL "$REPO/systemd/vlc-sync.service" -o "$DIR/systemd/vlc-sync.service"
curl -sSL "$REPO/systemd/vlc-sync.timer" -o "$DIR/systemd/vlc-sync.timer"
curl -sSL "$REPO/systemd/vlc-player.service" -o "$DIR/systemd/vlc-player.service"

# Save device config
echo "DEVICE_ID=$DEVICE_ID" > "$DIR/.device"

# Set permissions
chmod +x "$DIR/main.py"
chown -R pi:pi "$DIR"

# Install systemd services
echo "Installing services..."
cp "$DIR/systemd/"*.service "$DIR/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable vlc-sync.timer vlc-player
systemctl start vlc-sync.timer vlc-player

# Install watchdog cron (restarts if Python or VLC dies)
echo "Installing watchdog..."
WATCHDOG='*/5 * * * * (pgrep -f "main.py play" && pgrep -x vlc) || systemctl restart vlc-player'
(crontab -u pi -l 2>/dev/null | grep -v "vlc-player"; echo "$WATCHDOG") | crontab -u pi -

echo ""
echo "=== Done! ==="
echo "Device: $DEVICE_ID"
echo "VLC Player installed and running."
echo ""
echo "Commands:"
echo "  systemctl status vlc-player    # Check status"
echo "  journalctl -u vlc-player -f    # View logs"
echo "  python3 $DIR/main.py sync      # Manual sync"
