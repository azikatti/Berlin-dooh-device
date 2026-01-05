#!/bin/bash
# Bootstrap VLC Player for Raspberry Pi
# Run: sudo ~/vlc-player/bootstrap.sh
# Note: Username is auto-detected. Public repo - no GITHUB_TOKEN required
set -e

# Prevent multiple runs
LOCK_FILE="/tmp/vlc-bootstrap.lock"
if [ -f "$LOCK_FILE" ]; then
    echo "Bootstrap already completed. Skipping..."
    exit 0
fi
touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

# Auto-detect username
if [ -n "$SUDO_USER" ]; then
    # Running with sudo, use the original user
    USER="$SUDO_USER"
elif [ "$USER" = "root" ] || [ -z "$USER" ]; then
    # Running as root or USER not set, find first non-root user
    USER=$(getent passwd | awk -F: '$3 >= 1000 && $1 != "nobody" {print $1; exit}')
    [ -z "$USER" ] && USER="user"
fi
HOME_DIR="/home/$USER"
DIR="$HOME_DIR/vlc-player"
CONFIG_FILE="$DIR/config.env"

echo "=== VLC Player Bootstrap ==="
echo "User: $USER"
echo "Install directory: $DIR"

# ============================================================================
# STEP 0: SETUP CONFIG
# ============================================================================

echo "[0/3] Setting up configuration..."
# Fresh install - assume no config file exists
# Config file will be downloaded from GitHub in step 1
echo "Config file will be downloaded from GitHub ✓"

# Get DEVICE_ID from defaults (will be updated after config download)
DEVICE_ID="${DEVICE_ID:-berlin1}"

# ============================================================================
# STEP 1: DOWNLOAD ALL FILES (Code, VLC, Media)
# ============================================================================

echo "Setting up device: $DEVICE_ID"
hostnamectl set-hostname "$DEVICE_ID"

echo "[1/3] Installing VLC..."
if ! command -v vlc &> /dev/null; then
    apt update && apt install -y vlc
    echo "VLC installed ✓"
else
    echo "VLC already installed ✓"
fi

mkdir -p "$DIR/systemd"

# Always download all files from GitHub (no pre-installation assumption)
echo "[1/3] Downloading code files from GitHub..."

# Get repo info from config or use defaults
GITHUB_REPO_OWNER="${GITHUB_REPO_OWNER:-azikatti}"
GITHUB_REPO_NAME="${GITHUB_REPO_NAME:-Berlin-dooh-device}"
GITHUB_REPO_BRANCH="${GITHUB_REPO_BRANCH:-main}"

# Use public repo URL (no authentication required)
REPO_PUBLIC="https://raw.githubusercontent.com/${GITHUB_REPO_OWNER}/${GITHUB_REPO_NAME}/${GITHUB_REPO_BRANCH}"

# Download all code files (always from GitHub, no pre-installation assumption)
curl -sSL "$REPO_PUBLIC/main.py" -o "$DIR/main.py"
curl -sSL "$REPO_PUBLIC/config.py" -o "$DIR/config.py"
curl -sSL "$REPO_PUBLIC/media_sync.py" -o "$DIR/media_sync.py"
curl -sSL "$REPO_PUBLIC/code_update.py" -o "$DIR/code_update.py"
curl -sSL "$REPO_PUBLIC/bootstrap.sh" -o "$DIR/bootstrap.sh"
curl -sSL "$REPO_PUBLIC/config.env" -o "$DIR/config.env"
curl -sSL "$REPO_PUBLIC/systemd/vlc-maintenance.service" -o "$DIR/systemd/vlc-maintenance.service"
curl -sSL "$REPO_PUBLIC/systemd/vlc-maintenance.timer" -o "$DIR/systemd/vlc-maintenance.timer"
curl -sSL "$REPO_PUBLIC/systemd/vlc-player.service" -o "$DIR/systemd/vlc-player.service"
echo "Code files downloaded ✓"

chmod +x "$DIR/main.py" "$DIR/config.py" "$DIR/media_sync.py" "$DIR/code_update.py" "$DIR/bootstrap.sh"
chown -R "$USER:$USER" "$DIR"

# Re-source config file after download (needed for subsequent steps)
if [ -f "$CONFIG_FILE" ]; then
    set -a
    source "$CONFIG_FILE"
    set +a
    # Update DEVICE_ID from downloaded config
    DEVICE_ID="${DEVICE_ID:-berlin1}"
    echo "Config file loaded from download ✓"
fi

# Sync media from Dropbox
echo "[1/3] Syncing media from Dropbox..."
if sudo -u "$USER" python3 "$DIR/media_sync.py"; then
    if [ -f "$DIR/media/playlist_local.m3u" ] || [ -n "$(find "$DIR/media" -name "*.m3u" 2>/dev/null | head -1)" ]; then
        echo "Media synced ✓"
    else
        echo "Warning: No playlist found after sync"
        echo "The device will retry via maintenance timer"
    fi
else
    echo "Error: Initial sync failed"
    echo "The device will retry via maintenance timer, but VLC may not start until sync succeeds."
    # Continue bootstrap - timer will handle retries
fi

# Check for code updates
echo "[1/3] Checking for code updates..."
if sudo -u "$USER" python3 "$DIR/code_update.py"; then
    echo "Code updated (if needed) ✓"
else
    echo "Update check completed ✓"
fi

# ============================================================================
# STEP 2: SETUP SERVICES
# ============================================================================

echo "[2/3] Installing systemd services..."
for service_file in "$DIR/systemd/"*.service; do
    if [ -f "$service_file" ]; then
        sed -i "s|__USER__|$USER|g" "$service_file"
        sed -i "s|__DIR__|$DIR|g" "$service_file"
    fi
done
cp "$DIR/systemd/"*.service "$DIR/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable vlc-maintenance.timer vlc-player
echo "Systemd services installed ✓"

# Install watchdog cron
echo "[2/3] Installing watchdog cron..."
WATCHDOG='*/5 * * * * (pgrep -f "main.py" && pgrep -x vlc) || systemctl restart vlc-player'
(crontab -u "$USER" -l 2>/dev/null | grep -v "vlc-player"; echo "$WATCHDOG") | crontab -u "$USER" -
echo "Watchdog installed ✓"

# ============================================================================
# STEP 3: START VLC
# ============================================================================

echo "[3/3] Starting VLC player..."
sleep 2

# Check if playlist exists
if [ -f "$DIR/media/playlist_local.m3u" ] || [ -n "$(find "$DIR/media" -name "*.m3u" 2>/dev/null | head -1)" ]; then
    echo "Playlist found, starting VLC player..."
    systemctl start vlc-player
    sleep 3  # Give it more time to start
    
    if systemctl is-active --quiet vlc-player; then
        echo "VLC player started ✓"
        systemctl status vlc-player --no-pager | head -5 || true
    else
        echo "ERROR: VLC player failed to start"
        echo "Service status:"
        systemctl status vlc-player --no-pager -l | head -15 || true
        echo ""
        echo "Recent logs:"
        journalctl -u vlc-player -n 30 --no-pager | tail -20 || true
        echo ""
        echo "Troubleshooting:"
        echo "1. Check if VLC is installed: which vlc"
        echo "2. Check if playlist exists: ls -la $DIR/media/*.m3u"
        echo "3. Check permissions: ls -la $DIR/main.py"
        echo "4. Try manual start: sudo -u $USER python3 $DIR/main.py"
    fi
else
    echo "Warning: No playlist found. Player will start once media is synced."
    systemctl start vlc-player
    sleep 2
    if systemctl is-active --quiet vlc-player; then
        echo "Service started (waiting for playlist) ✓"
    else
        echo "Service started but will wait for playlist"
        echo "Checking service status..."
        systemctl status vlc-player --no-pager -l | head -10 || true
    fi
fi

systemctl start vlc-maintenance.timer
echo "Maintenance timer started ✓"

echo ""
echo "=== Bootstrap Complete! ==="
echo "Device: $DEVICE_ID"
echo "Config: $CONFIG_FILE (downloaded from GitHub)"
