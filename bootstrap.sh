#!/bin/bash
# Bootstrap VLC Player for Raspberry Pi
# Run: curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash
# Or with device ID: curl ... | sudo DEVICE_ID=berlin-01 bash
set -e

REPO="https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main"
DIR="/home/pi/vlc-player"

echo "=== VLC Player Bootstrap ==="

# ============================================================================
# STEP 1: DOWNLOAD ALL FILES (Code, VLC, Media)
# ============================================================================

# Set device ID (use provided or default to berlin1)
if [ -z "$DEVICE_ID" ]; then
    DEVICE_ID="berlin1"
    echo "Using default device ID: $DEVICE_ID"
fi

echo "Setting up device: $DEVICE_ID"

# Set system hostname
echo "Setting hostname to $DEVICE_ID..."
hostnamectl set-hostname "$DEVICE_ID"

# Install VLC if missing
echo "[1/3] Installing VLC..."
if ! command -v vlc &> /dev/null; then
    apt update && apt install -y vlc
    echo "VLC installed ✓"
else
    echo "VLC already installed ✓"
fi

# Create directory
mkdir -p "$DIR/systemd"

# Download code files from GitHub
echo "[1/3] Downloading code files from GitHub..."
curl -sSL "$REPO/main.py" -o "$DIR/main.py"
curl -sSL "$REPO/systemd/vlc-maintenance.service" -o "$DIR/systemd/vlc-maintenance.service"
curl -sSL "$REPO/systemd/vlc-maintenance.timer" -o "$DIR/systemd/vlc-maintenance.timer"
curl -sSL "$REPO/systemd/vlc-player.service" -o "$DIR/systemd/vlc-player.service"
echo "Code files downloaded ✓"

# Save device config
echo "DEVICE_ID=$DEVICE_ID" > "$DIR/.device"

# Set permissions
chmod +x "$DIR/main.py"
chown -R pi:pi "$DIR"

# Sync media from Dropbox
echo "[1/3] Syncing media from Dropbox..."
if sudo -u pi python3 "$DIR/main.py" sync; then
    echo "Media synced ✓"
else
    echo "Warning: Initial sync failed. Will retry via timer."
fi

# Check for code updates from GitHub
echo "[1/3] Checking for code updates from GitHub..."
if sudo -u pi python3 "$DIR/main.py" update; then
    echo "Code updated (if needed) ✓"
else
    echo "Update check completed ✓"
fi

# ============================================================================
# STEP 2: ADD CRON JOBS AND WATCHDOGS
# ============================================================================

echo "[2/3] Installing systemd services..."
cp "$DIR/systemd/"*.service "$DIR/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable vlc-maintenance.timer vlc-player
echo "Systemd services installed ✓"

# Install watchdog cron (restarts if Python or VLC dies)
echo "[2/3] Installing watchdog cron..."
WATCHDOG='*/5 * * * * (pgrep -f "main.py play" && pgrep -x vlc) || systemctl restart vlc-player'
(crontab -u pi -l 2>/dev/null | grep -v "vlc-player"; echo "$WATCHDOG") | crontab -u pi -
echo "Watchdog installed ✓"

# ============================================================================
# STEP 3: START VLC WITH PLAYLIST (Only after everything is ready)
# ============================================================================

echo "[3/3] Starting VLC player..."
# Verify playlist exists before starting
if [ -f "$DIR/media/playlist_local.m3u" ] || [ -n "$(find "$DIR/media" -name "*.m3u" 2>/dev/null | head -1)" ]; then
    systemctl start vlc-player
    echo "VLC player started ✓"
else
    echo "Warning: No playlist found. Player will start once media is synced."
    systemctl start vlc-player  # Start anyway, it will retry
fi

# Start maintenance timer for future syncs
systemctl start vlc-maintenance.timer
echo "Maintenance timer started ✓"

echo ""
echo "=== Bootstrap Complete! ==="
echo "Device: $DEVICE_ID"
echo "VLC Player installed and running."
echo ""
echo "Commands:"
echo "  systemctl status vlc-player           # Check player status"
echo "  systemctl status vlc-maintenance.timer # Check maintenance timer"
echo "  journalctl -u vlc-player -f          # View player logs"
echo "  python3 $DIR/main.py sync             # Manual sync"
echo "  python3 $DIR/main.py update           # Manual update check"
