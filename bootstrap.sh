#!/bin/bash
# Bootstrap VLC Player for Raspberry Pi
# Run: curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash
# Default device ID: berlin1 (override with: curl ... | sudo DEVICE_ID=berlin-02 bash)
set -e

REPO="https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main"

# Detect the actual user (works with sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"
if [ "$ACTUAL_USER" = "root" ]; then
    # If running as root without sudo, try to find a non-root user
    ACTUAL_USER=$(getent passwd | awk -F: '$3 >= 1000 && $1 != "nobody" {print $1; exit}')
fi

if [ -z "$ACTUAL_USER" ]; then
    echo "Error: Could not determine user. Please run as: sudo -u YOUR_USER bash"
    exit 1
fi

HOME_DIR=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)
DIR="$HOME_DIR/vlc-player"

echo "=== VLC Player Bootstrap ==="
echo "Detected user: $ACTUAL_USER"
echo "Home directory: $HOME_DIR"
echo "Install directory: $DIR"

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
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$DIR"

# Sync media from Dropbox
echo "[1/3] Syncing media from Dropbox..."
if sudo -u "$ACTUAL_USER" python3 "$DIR/main.py" sync; then
    # Verify playlist was created
    if [ -f "$DIR/media/playlist_local.m3u" ] || [ -n "$(find "$DIR/media" -name "*.m3u" 2>/dev/null | head -1)" ]; then
        echo "Media synced ✓ (playlist found)"
    else
        echo "Warning: Sync completed but no playlist found in $DIR/media/"
        ls -la "$DIR/media/" 2>/dev/null || echo "Media directory does not exist"
    fi
else
    echo "Warning: Initial sync failed. Will retry via timer."
    echo "You can manually sync later with: sudo -u $ACTUAL_USER python3 $DIR/main.py sync"
fi

# Check for code updates from GitHub
echo "[1/3] Checking for code updates from GitHub..."
if sudo -u "$ACTUAL_USER" python3 "$DIR/main.py" update; then
    echo "Code updated (if needed) ✓"
else
    echo "Update check completed ✓"
fi

# ============================================================================
# STEP 2: ADD CRON JOBS AND WATCHDOGS
# ============================================================================

echo "[2/3] Installing systemd services..."
# Update systemd service files with actual user and directory using placeholders
for service_file in "$DIR/systemd/"*.service; do
    if [ -f "$service_file" ]; then
        sed -i "s|__USER__|$ACTUAL_USER|g" "$service_file"
        sed -i "s|__DIR__|$DIR|g" "$service_file"
        # Verify replacement worked
        if grep -q "__USER__\|__DIR__" "$service_file"; then
            echo "Warning: Failed to replace placeholders in $service_file"
        fi
    fi
done
cp "$DIR/systemd/"*.service "$DIR/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable vlc-maintenance.timer vlc-player
echo "Systemd services installed ✓"

# Install watchdog cron (restarts if Python or VLC dies)
echo "[2/3] Installing watchdog cron..."
WATCHDOG='*/5 * * * * (pgrep -f "main.py play" && pgrep -x vlc) || systemctl restart vlc-player'
(crontab -u "$ACTUAL_USER" -l 2>/dev/null | grep -v "vlc-player"; echo "$WATCHDOG") | crontab -u "$ACTUAL_USER" -
echo "Watchdog installed ✓"

# ============================================================================
# STEP 3: START VLC WITH PLAYLIST (Only after everything is ready)
# ============================================================================

echo "[3/3] Starting VLC player..."
# Wait a moment for any async operations to complete
sleep 2

# Verify playlist exists before starting
PLAYLIST_FOUND=false
PLAYLIST_FILE=""
if [ -f "$DIR/media/playlist_local.m3u" ]; then
    PLAYLIST_FOUND=true
    PLAYLIST_FILE="$DIR/media/playlist_local.m3u"
    echo "Found playlist: $PLAYLIST_FILE"
elif [ -n "$(find "$DIR/media" -name "*.m3u" 2>/dev/null | head -1)" ]; then
    PLAYLIST_FOUND=true
    PLAYLIST_FILE=$(find "$DIR/media" -name "*.m3u" 2>/dev/null | head -1)
    echo "Found playlist: $PLAYLIST_FILE"
fi

if [ "$PLAYLIST_FOUND" = "true" ]; then
    systemctl start vlc-player
    sleep 2
    if systemctl is-active --quiet vlc-player; then
        echo "VLC player started ✓"
    else
        echo "Warning: VLC player service failed to start."
        echo "Check logs with: journalctl -u vlc-player -n 20"
        systemctl status vlc-player --no-pager -l || true
    fi
else
    echo "Warning: No playlist found. Player will start once media is synced."
    echo "Media directory contents:"
    ls -la "$DIR/media/" 2>/dev/null || echo "Media directory does not exist"
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
