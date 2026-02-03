#!/bin/bash
# Bootstrap VLC Player for Raspberry Pi using git clone
# Usage (one-liner):
#   curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash
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

DIR="$HOME_DIR/vlc-player"
CONFIG_FILE="$DIR/config.env"

echo "=== VLC Player Bootstrap ==="
echo "User: $USER"
echo "Install directory: $DIR"

# --- Install dependencies -----------------------------------------------------
echo "[1/5] Installing dependencies (git, vlc)..."
apt update
apt install -y git vlc curl

# --- Ensure system time is set (for GitHub SSL verification) ------------------
echo "[2/5] Setting/correcting system time..."
if command -v timedatectl &>/dev/null; then
  timedatectl set-ntp true 2>/dev/null || true
  echo "  NTP enabled. Waiting a few seconds for time sync..."
  sleep 5
fi
echo "  Current time: $(date -Iseconds 2>/dev/null || date)"

# --- Clone or update repo -----------------------------------------------------
echo "[3/5] Fetching code from GitHub..."

if [ -d "$DIR/.git" ]; then
  echo "Repo already exists, updating..."
  cd "$DIR"
  if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree dirty, refusing to overwrite local changes."
    exit 1
  fi
  git fetch origin
  git reset --hard origin/main
else
  echo "Cloning fresh copy..."
  sudo -u "$USER" git clone https://github.com/azikatti/Berlin-dooh-device.git "$DIR"
  cd "$DIR"
fi

chown -R "$USER:$USER" "$DIR"

# --- Ensure config.env exists -------------------------------------------------
if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<EOF
DEVICE_ID=berlin1
DROPBOX_URL=https://www.dropbox.com/scl/fo/YOUR_FOLDER_ID/...?dl=1
# Optional: for remote SSH over Tailscale (create at https://login.tailscale.com/admin/settings/keys)
# TAILSCALE_AUTHKEY=
EOF
  chown "$USER:$USER" "$CONFIG_FILE"
  echo "Created default config.env at $CONFIG_FILE"
else
  echo "Using existing config.env at $CONFIG_FILE"
fi

# Load TAILSCALE_AUTHKEY from config if not already set (for optional step 5)
if [ -z "${TAILSCALE_AUTHKEY:-}" ] && [ -f "$CONFIG_FILE" ]; then
  TAILSCALE_AUTHKEY=$(grep -E '^TAILSCALE_AUTHKEY=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  export TAILSCALE_AUTHKEY
fi

# --- Install systemd services -------------------------------------------------
echo "[4/5] Installing systemd services..."

# Replace placeholders in service files before copying
for service_file in "$DIR/systemd/"*.service "$DIR/systemd/"*.timer; do
  if [ -f "$service_file" ]; then
    sed -i "s|__USER__|$USER|g" "$service_file"
    sed -i "s|__DIR__|$DIR|g" "$service_file"
  fi
done

cp "$DIR/systemd/"*.service "$DIR/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable vlc-player vlc-maintenance.timer
systemctl start vlc-player vlc-maintenance.timer

# --- Install and enable Tailscale (optional join if TAILSCALE_AUTHKEY set) ----
echo "[5/5] Tailscale..."
if command -v tailscale &>/dev/null; then
  echo "Tailscale already installed."
else
  curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled 2>/dev/null || true
if [ -n "${TAILSCALE_AUTHKEY:-}" ]; then
  echo "Joining tailnet with auth key..."
  tailscale up --authkey="$TAILSCALE_AUTHKEY" --accept-dns=false
  TS_IP=$(tailscale ip -4 2>/dev/null || true)
  if [ -n "$TS_IP" ]; then
    echo "Tailscale joined. SSH via: ssh $USER@$TS_IP"
  else
    echo "Tailscale joined. Run 'tailscale status' on the Pi to see its Tailscale IP for SSH."
  fi
else
  echo "TAILSCALE_AUTHKEY not set. Install complete; run 'tailscale up' manually or set TAILSCALE_AUTHKEY in config.env and re-run bootstrap."
fi

echo ""
echo "=== Bootstrap Complete ==="
echo "User:   $USER"
echo "Dir:    $DIR"
echo "Config: $CONFIG_FILE"
