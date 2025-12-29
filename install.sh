#!/bin/bash
#
# Install script for VLC Playlist Manager on Raspberry Pi
# Run this script to set up auto-start on boot
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="vlc-bootloader"
SERVICE_FILE="${SERVICE_NAME}.service"
USER="${SUDO_USER:-pi}"
INSTALL_DIR="/home/${USER}/Berlin-dooh-device"

echo "=========================================="
echo "VLC Playlist Manager - Installation"
echo "=========================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

# Copy files to install directory
echo "Installing to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
cp -r "${SCRIPT_DIR}"/* "${INSTALL_DIR}/"
chown -R "${USER}:${USER}" "${INSTALL_DIR}"
chmod +x "${INSTALL_DIR}/bootloader.py"
chmod +x "${INSTALL_DIR}/vlc.py"

# Update service file with correct paths
echo "Configuring systemd service..."
sed -i "s|/home/pi/Berlin-dooh-device|${INSTALL_DIR}|g" "${INSTALL_DIR}/${SERVICE_FILE}"
sed -i "s|User=pi|User=${USER}|g" "${INSTALL_DIR}/${SERVICE_FILE}"
sed -i "s|Group=pi|Group=${USER}|g" "${INSTALL_DIR}/${SERVICE_FILE}"

# Install systemd service
cp "${INSTALL_DIR}/${SERVICE_FILE}" "/etc/systemd/system/${SERVICE_FILE}"
systemctl daemon-reload

# Enable service
echo "Enabling service to start on boot..."
systemctl enable "${SERVICE_NAME}"

echo ""
echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo ""
echo "Commands:"
echo "  Start now:    sudo systemctl start ${SERVICE_NAME}"
echo "  Stop:         sudo systemctl stop ${SERVICE_NAME}"
echo "  Status:       sudo systemctl status ${SERVICE_NAME}"
echo "  Logs:         journalctl -u ${SERVICE_NAME} -f"
echo "  Disable:      sudo systemctl disable ${SERVICE_NAME}"
echo ""
echo "Configuration:"
echo "  Install dir:  ${INSTALL_DIR}"
echo "  Log file:     ${INSTALL_DIR}/bootloader.log"
echo ""
echo "Optional: Set GITHUB_TOKEN for private repos:"
echo "  Edit /etc/systemd/system/${SERVICE_FILE}"
echo "  Add: Environment=\"GITHUB_TOKEN=your_token_here\""
echo "  Then: sudo systemctl daemon-reload && sudo systemctl restart ${SERVICE_NAME}"
echo ""

