# VLC Playlist Player

Syncs media from Dropbox and plays on loop using VLC. Designed for Raspberry Pi digital signage.

## Quick Install (Raspberry Pi)

### One-Line Installation

On a fresh Raspberry Pi, run this single command:

```bash
curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash
```

The bootstrap script will download `config.env` from GitHub. You can edit it after installation, or create `~/vlc-player/config.env` first with your settings:
- `DEVICE_ID=berlin1` (change per device)
- `DROPBOX_URL=your_dropbox_url`

**Note:** Public repo - no GITHUB_TOKEN required!

### Manual Installation

If you prefer to download and run manually:

1. Download the bootstrap script:
   ```bash
   curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh -o /tmp/bootstrap.sh
   chmod +x /tmp/bootstrap.sh
   ```

2. Run the bootstrap:
   ```bash
   sudo /tmp/bootstrap.sh
   ```

**Note:** Public repo - no GITHUB_TOKEN required!

**Note:** The username is auto-detected (works with 'admin', 'user', or any username)

That's it! The bootstrap script follows a 3-step process:

**Step 0: Setup Configuration**
- Config file will be downloaded from GitHub
- Loads all configuration values

**Step 1: Download All Files**
- Install VLC if needed
- Download all code files from GitHub (no pre-installation required)
- Sync media from Dropbox (immediate, not waiting for timer)
- Check for code updates from GitHub

**Step 2: Setup Services**
- Install and enable systemd services
- Services auto-restart on failure (systemd Restart=always)

**Step 3: Start VLC Player**
- Verify playlist is ready
- Start VLC player with playlist
- Start maintenance timer for future syncs

The player starts playing immediately after all files are downloaded and synced!

## Configuration

All configuration is in `config.env` file:

```bash
# Device-specific
DEVICE_ID=berlin1

# GitHub (public repo - GITHUB_TOKEN not required)
# GITHUB_TOKEN=ghp_your_token  # Only needed for private repos

# Dropbox (shared)
DROPBOX_URL=https://www.dropbox.com/scl/fo/YOUR_FOLDER_ID/...?dl=1
```

**To change device ID:**
Edit `config.env` before copying to SD card, or edit `/etc/vlc-player/config` on the device and restart services.

## Usage

### Commands
```bash
python3 ~/vlc-player/media_sync.py         # Download media from Dropbox
python3 ~/vlc-player/main.py               # Play playlist with VLC
python3 ~/vlc-player/code_update.py        # Check for code updates and install if available
sudo ~/vlc-player/verify_bootstrap.sh      # Verify bootstrap completed successfully
sudo ~/vlc-player/cleanup_bootstrap.sh     # Remove legacy items (watchdog cron, hostname entries)
```

### Service Management
```bash
systemctl status vlc-player              # Check player status
systemctl status vlc-maintenance.timer   # Check maintenance timer
systemctl restart vlc-player             # Restart player
journalctl -u vlc-player -f              # View player logs
journalctl -u vlc-maintenance -f         # View maintenance logs
```

## How It Works

### Bootstrap Process (First Install)
1. **Config**: Downloads `config.env` from GitHub
2. **Downloads**: Installs VLC, downloads all code files from GitHub, syncs media from Dropbox
3. **Setup**: Installs and enables systemd services (auto-restart on failure)
4. **Start**: Launches VLC player with playlist (only after everything is ready)

### Runtime Operation
1. **Maintenance (every 5 min)**: Syncs media from Dropbox AND checks for code updates
   - Downloads Dropbox folder → extracts to temp → atomic swap to `media/`
   - Checks GitHub for new code version → downloads and installs if available
2. **Play**: VLC runs in loop mode, auto-restarts if it crashes

## Device Identification

Device ID is stored in `config.env`. This ID is:
- Set in `config.env` (downloaded from GitHub or created manually)
- Used for device identification in logs

To check device ID:
```bash
grep DEVICE_ID ~/vlc-player/config.env
```

To change device ID:
```bash
nano ~/vlc-player/config.env
# Change DEVICE_ID=berlin1 to DEVICE_ID=new-name
sudo systemctl restart vlc-player
```

## Reliability Features

### Retry Logic
If Dropbox download fails (network issues), the sync retries once (2 attempts total) with a 5-second delay.

### Auto-Restart (Systemd)
The `vlc-player` service is configured with `Restart=always`, so systemd automatically restarts the service if it crashes. No watchdog cron needed.

### Auto-Update Mechanism

The player automatically checks GitHub every 5 minutes for code updates. If a new version is detected (by comparing the `VERSION` constant in `main.py`), the update function downloads and installs the latest code, then restarts services.

**To trigger an update:**
1. Update code in GitHub
2. Update `VERSION` constant in `main.py` (e.g., `VERSION = "1.0.1"`)
3. Devices will automatically update within 5 minutes

**Check current version:**
```bash
grep VERSION ~/vlc-player/main.py
```

**Manual code update:**
```bash
python3 ~/vlc-player/code_update.py
```

```
Dropbox Folder          Raspberry Pi
┌─────────────┐         ┌─────────────┐
│ playlist.m3u│  ──▶    │ Download    │
│ video1.mp4  │  sync   │ Extract     │
│ video2.mp4  │         │ Play (VLC)  │
└─────────────┘         └─────────────┘
```

## Dropbox Setup

1. Create a folder on Dropbox with your media files
2. Add a `playlist.m3u` file listing your videos:
   ```
   #EXTM3U
   video1.mp4
   video2.mp4
   video3.mp4
   ```
3. Share the folder and get the link
4. Add `?dl=1` to the end of the link for direct download
5. Add the URL to `config.env` as `DROPBOX_URL`

## File Structure

```
~/vlc-player/  (or /home/<username>/vlc-player/)
├── main.py              # VLC player script (play only)
├── media_sync.py        # Media sync script (downloads from Dropbox)
├── code_update.py       # Code update script (checks GitHub)
├── config.py            # Shared configuration utilities
├── bootstrap.sh          # Bootstrap installer
├── verify_bootstrap.sh   # Verification script (checks bootstrap)
├── cleanup_bootstrap.sh # Cleanup script (removes legacy items)
├── stop_vlc.sh          # Stop VLC services script
├── config.env            # Configuration file (all settings)
├── media/               # Downloaded media (auto-synced)
│   ├── playlist.m3u
│   └── *.mp4
└── systemd/             # Service files
    ├── vlc-maintenance.service  # Sync + code update
    ├── vlc-maintenance.timer    # Every 5 min
    └── vlc-player.service       # VLC player
```

Configuration is stored in `~/vlc-player/config.env` (downloaded from GitHub during bootstrap).

## Requirements

- Raspberry Pi (any model with display)
- Raspberry Pi OS
- VLC (`sudo apt install vlc`)
- Internet connection (for Dropbox sync and GitHub updates)

## Troubleshooting

**No video playing?**
```bash
journalctl -u vlc-player -n 50   # Check logs
python3 ~/vlc-player/media_sync.py  # Manual sync
ls ~/vlc-player/media/    # Check downloaded files
```

**Sync not working?**
```bash
systemctl status vlc-maintenance.timer  # Check timer
journalctl -u vlc-maintenance -f         # View maintenance logs
# Check config file
cat ~/vlc-player/config.env
```

**Clean up legacy items?**
If you upgraded from an older version, run the cleanup script to remove watchdog cron and hostname entries:
```bash
sudo ~/vlc-player/cleanup_bootstrap.sh
```

**Display issues?**
Make sure `DISPLAY=:0` is set. The player runs on the primary display.

**Check device ID?**
```bash
grep DEVICE_ID ~/vlc-player/config.env
```

**Verify bootstrap completed?**
```bash
sudo ~/vlc-player/verify_bootstrap.sh
```

**Authentication errors?**
Make sure `DROPBOX_URL` and other settings are configured in `~/vlc-player/config.env`:
```bash
cat ~/vlc-player/config.env
```

## License

MIT
