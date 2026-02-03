#!/bin/bash
# Bootstrap Verification Script
# Checks if all bootstrap operations completed successfully
# Usage: sudo ./verify_bootstrap.sh

# Remove set -e - we want to continue even if checks fail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Auto-detect user and directory (same logic as bootstrap.sh)
if [ -n "$SUDO_USER" ]; then
    USER="$SUDO_USER"
elif [ "$USER" = "root" ] || [ -z "$USER" ]; then
    USER=$(getent passwd | awk -F: '$3 >= 1000 && $1 != "nobody" {print $1; exit}')
    [ -z "$USER" ] && USER="user"
fi
HOME_DIR="/home/$USER"
DIR="$HOME_DIR/vlc-player"
CONFIG_FILE="$DIR/config.env"

echo "=== Bootstrap Verification ==="
echo "User: $USER"
echo "Install directory: $DIR"
echo ""

# Function to check and report (takes result code as first arg)
check() {
    local result=$1
    shift
    local message="$@"
    if [ $result -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $message"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $message"
        ((FAILED++))
        return 1
    fi
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

# ============================================================================
# 1. SYSTEM CONFIGURATION
# ============================================================================

echo "=== 1. System Configuration ==="

# Check VLC installation
if command -v vlc &> /dev/null; then
    VLC_VERSION=$(vlc --version 2>/dev/null | head -1 || echo "installed")
    check 0 "VLC installed ($VLC_VERSION)"
else
    warn "VLC not installed"
fi

echo ""

# ============================================================================
# 2. FILE STRUCTURE
# ============================================================================

echo "=== 2. File Structure ==="

# Check directory exists
if [ -d "$DIR" ]; then
    check 0 "Install directory exists: $DIR"
else
    warn "Install directory missing: $DIR"
fi

# Required code files
REQUIRED_FILES=(
    "main.py"
    "config.py"
    "media_sync.py"
    "code_update.py"
    "bootstrap.sh"
    "stop_vlc.sh"
    "verify_bootstrap.sh"
    "config.env"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$DIR/$file" ]; then
        check 0 "File exists: $file"
        
        # Check if executable (for Python/Shell scripts)
        if [[ "$file" == *.py ]] || [[ "$file" == *.sh ]]; then
            if [ -x "$DIR/$file" ]; then
                check 0 "  → Executable permission set"
            else
                warn "  → Missing executable permission"
            fi
        fi
    else
        warn "File missing: $file"
    fi
done

# Check systemd directory
if [ -d "$DIR/systemd" ]; then
    check 0 "Systemd directory exists"
    
    # Check systemd files
    for file in "vlc-player.service" "vlc-maintenance.service" "vlc-maintenance.timer"; do
        if [ -f "$DIR/systemd/$file" ]; then
            check 0 "Systemd file exists: $file"
        else
            warn "Systemd file missing: $file"
        fi
    done
else
    warn "Systemd directory missing"
fi

# Check ownership
if [ -d "$DIR" ]; then
    OWNER=$(stat -c '%U' "$DIR" 2>/dev/null || stat -f '%Su' "$DIR" 2>/dev/null)
    if [ "$OWNER" = "$USER" ]; then
        check 0 "Directory owned by $USER"
    else
        warn "Directory owned by $OWNER (expected $USER)"
    fi
fi

echo ""

# ============================================================================
# 3. CONFIGURATION
# ============================================================================

echo "=== 3. Configuration ==="

if [ -f "$CONFIG_FILE" ]; then
    check 0 "Config file exists: $CONFIG_FILE"
    
    # Parse config values reliably (handles URLs with special characters)
    DROPBOX_URL=$(grep "^DROPBOX_URL=" "$CONFIG_FILE" 2>/dev/null | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    DEVICE_ID=$(grep "^DEVICE_ID=" "$CONFIG_FILE" 2>/dev/null | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    GITHUB_REPO_OWNER=$(grep "^GITHUB_REPO_OWNER=" "$CONFIG_FILE" 2>/dev/null | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    
    if [ -n "$DROPBOX_URL" ] && [ "$DROPBOX_URL" != "" ]; then
        check 0 "  → DROPBOX_URL configured"
    else
        warn "  → DROPBOX_URL missing"
    fi
    
    if [ -n "$DEVICE_ID" ] && [ "$DEVICE_ID" != "" ]; then
        check 0 "  → DEVICE_ID configured ($DEVICE_ID)"
    else
        warn "  → DEVICE_ID missing"
    fi
    
    if [ -n "$GITHUB_REPO_OWNER" ] && [ "$GITHUB_REPO_OWNER" != "" ]; then
        check 0 "  → GITHUB_REPO_OWNER configured"
    else
        warn "  → GITHUB_REPO_OWNER missing"
    fi
else
    warn "Config file missing: $CONFIG_FILE"
fi

echo ""

# ============================================================================
# 4. MEDIA
# ============================================================================

echo "=== 4. Media ==="

if [ -d "$DIR/media" ]; then
    check 0 "Media directory exists"
    
    if [ -f "$DIR/media/playlist.m3u" ]; then
        check 0 "Playlist exists: playlist.m3u"
        
        # Count media files
        MEDIA_COUNT=$(find "$DIR/media" -type f \( -name "*.mp4" -o -name "*.avi" -o -name "*.mkv" \) 2>/dev/null | wc -l)
        if [ "$MEDIA_COUNT" -gt 0 ]; then
            check 0 "Media files found: $MEDIA_COUNT"
        else
            warn "No media files found in media directory"
        fi
    else
        warn "Playlist missing (media sync may have failed)"
    fi
else
    warn "Media directory missing (media sync may have failed)"
fi

echo ""

# ============================================================================
# 5. SYSTEMD SERVICES
# ============================================================================

echo "=== 5. Systemd Services ==="

# Check if services exist in /etc/systemd/system/
for service in "vlc-player.service" "vlc-maintenance.service" "vlc-maintenance.timer"; do
    if [ -f "/etc/systemd/system/$service" ]; then
        check 0 "Service file installed: $service"
        
        # Check if placeholders are replaced
        if grep -q "__USER__\|__DIR__" "/etc/systemd/system/$service" 2>/dev/null; then
            warn "  → Placeholders not replaced in $service"
        else
            check 0 "  → Placeholders replaced"
        fi
        
        # Check if enabled
        if systemctl is-enabled "$service" &>/dev/null; then
            check 0 "  → Service enabled"
        else
            warn "  → Service not enabled"
        fi
    else
        warn "Service file missing: $service"
    fi
done

# Check service status
if systemctl is-active --quiet vlc-player 2>/dev/null; then
    check 0 "vlc-player service is running"
elif systemctl is-enabled --quiet vlc-player 2>/dev/null; then
    warn "vlc-player service enabled but not running"
else
    warn "vlc-player service not running"
fi

if systemctl is-active --quiet vlc-maintenance.timer 2>/dev/null; then
    check 0 "vlc-maintenance.timer is active"
elif systemctl is-enabled --quiet vlc-maintenance.timer 2>/dev/null; then
    warn "vlc-maintenance.timer enabled but not active"
else
    warn "vlc-maintenance.timer not active"
fi

echo ""

# ============================================================================
# 6. TAILSCALE (optional)
# ============================================================================

echo "=== 6. Tailscale ==="

if command -v tailscale &>/dev/null; then
    check 0 "Tailscale installed"
    if systemctl is-active --quiet tailscaled 2>/dev/null; then
        check 0 "tailscaled is running"
    else
        warn "tailscaled not running"
    fi
    if tailscale status &>/dev/null; then
        TS_IP=$(tailscale ip -4 2>/dev/null || true)
        if [ -n "$TS_IP" ]; then
            check 0 "Tailscale connected ($TS_IP)"
        else
            check 0 "Tailscale logged in"
        fi
    else
        warn "Tailscale not logged in (run 'tailscale up' or set TAILSCALE_AUTHKEY)"
    fi
else
    warn "Tailscale not installed (optional; set TAILSCALE_AUTHKEY in config.env to enable)"
fi

echo ""

# ============================================================================
# SUMMARY
# ============================================================================

echo "=== Summary ==="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"
echo ""

if [ $FAILED -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! Bootstrap completed successfully.${NC}"
    exit 0
elif [ $FAILED -eq 0 ]; then
    echo -e "${YELLOW}⚠ Bootstrap completed with warnings.${NC}"
    exit 0
else
    echo -e "${RED}✗ Bootstrap has failures. Please review above.${NC}"
    exit 1
fi

