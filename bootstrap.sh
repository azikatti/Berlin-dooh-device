#!/bin/bash
# Bootstrap VLC Player for Raspberry Pi
# Run: sudo ~/vlc-player/bootstrap.sh
# Note: Username is auto-detected. GITHUB_TOKEN should be set in config.env file
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
if [ -f "$CONFIG_FILE" ]; then
    # Source config to get values
    set -a
    source "$CONFIG_FILE"
    set +a
    echo "Config file loaded ✓"
else
    echo "Error: No config file found at $CONFIG_FILE"
    exit 1
fi

# Get DEVICE_ID from config (no .device file needed)
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

# Check if files are pre-installed
if [ -f "$DIR/main.py" ] && [ -f "$DIR/systemd/vlc-player.service" ]; then
    echo "[1/3] Using pre-installed files..."
    echo "Code files found ✓"
else
    echo "[1/3] Downloading code files from GitHub..."
    
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "Error: GITHUB_TOKEN not found in config"
        exit 1
    fi
    
    # Get repo info from config or use defaults
    GITHUB_REPO_OWNER="${GITHUB_REPO_OWNER:-azikatti}"
    GITHUB_REPO_NAME="${GITHUB_REPO_NAME:-Berlin-dooh-device}"
    GITHUB_REPO_BRANCH="${GITHUB_REPO_BRANCH:-main}"
    
    REPO_AUTH="https://${GITHUB_TOKEN}@raw.githubusercontent.com/${GITHUB_REPO_OWNER}/${GITHUB_REPO_NAME}/${GITHUB_REPO_BRANCH}"
    
    curl -sSL "$REPO_AUTH/main.py" -o "$DIR/main.py"
    curl -sSL "$REPO_AUTH/config.py" -o "$DIR/config.py"
    curl -sSL "$REPO_AUTH/media_sync.py" -o "$DIR/media_sync.py"
    curl -sSL "$REPO_AUTH/systemd/vlc-maintenance.service" -o "$DIR/systemd/vlc-maintenance.service"
    curl -sSL "$REPO_AUTH/systemd/vlc-maintenance.timer" -o "$DIR/systemd/vlc-maintenance.timer"
    curl -sSL "$REPO_AUTH/systemd/vlc-player.service" -o "$DIR/systemd/vlc-player.service"
    echo "Code files downloaded ✓"
fi

chmod +x "$DIR/main.py" "$DIR/config.py" "$DIR/media_sync.py"
chown -R "$USER:$USER" "$DIR"

# Sync media from Dropbox
echo "[1/3] Syncing media from Dropbox..."
if sudo -u "$USER" python3 "$DIR/media_sync.py"; then
    if [ -f "$DIR/media/playlist_local.m3u" ] || [ -n "$(find "$DIR/media" -name "*.m3u" 2>/dev/null | head -1)" ]; then
        echo "Media synced ✓"
    else
        echo "Warning: No playlist found"
    fi
else
    echo "Warning: Initial sync failed. Will retry via timer."
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
WATCHDOG='*/5 * * * * (pgrep -f "main.py play" && pgrep -x vlc) || systemctl restart vlc-player'
(crontab -u "$USER" -l 2>/dev/null | grep -v "vlc-player"; echo "$WATCHDOG") | crontab -u "$USER" -
echo "Watchdog installed ✓"

# ============================================================================
# STEP 3: START VLC
# ============================================================================

echo "[3/3] Starting VLC player..."
sleep 2

if [ -f "$DIR/media/playlist_local.m3u" ] || [ -n "$(find "$DIR/media" -name "*.m3u" 2>/dev/null | head -1)" ]; then
    systemctl start vlc-player
    sleep 2
    if systemctl is-active --quiet vlc-player; then
        echo "VLC player started ✓"
    else
        echo "Warning: VLC player failed to start"
    fi
else
    echo "Warning: No playlist found. Player will start once media is synced."
    systemctl start vlc-player
fi

systemctl start vlc-maintenance.timer
echo "Maintenance timer started ✓"

echo ""
echo "=== Bootstrap Complete! ==="
echo "Device: $DEVICE_ID"
echo "Config: $CONFIG_FILE (local)"
