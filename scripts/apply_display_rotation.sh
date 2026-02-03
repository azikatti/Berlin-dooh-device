#!/bin/bash
# Set display_rotate=1 in boot config for Raspberry Pi vertical (portrait) screen.
# Pi 4/5: /boot/firmware/config.txt; older: /boot/config.txt
# Run with: sudo scripts/apply_display_rotation.sh
# Takes effect after next reboot.

set -e

TARGET=1
if [ -f /boot/firmware/config.txt ]; then
  CONFIG=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
  CONFIG=/boot/config.txt
else
  echo "No boot config found, skipping."
  exit 0
fi

if grep -q "^display_rotate=$TARGET" "$CONFIG"; then
  echo "display_rotate=$TARGET already set in $CONFIG"
  exit 0
fi

# Remove any existing display_rotate line
sed -i '/^display_rotate=/d' "$CONFIG"
echo "display_rotate=$TARGET" >> "$CONFIG"
echo "Set display_rotate=$TARGET in $CONFIG (reboot to apply)"
exit 0
