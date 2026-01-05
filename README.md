# VLC Playlist Player

Syncs media from Dropbox and plays on loop using VLC. Designed for Raspberry Pi digital signage.

## Quick Install (Raspberry Pi)

**Setup:**
1. Edit `config.env` with your settings:
   - `DEVICE_ID=berlin1` (change per device)
   - `GITHUB_TOKEN=ghp_your_token` (shared token for private repo)
   - `DROPBOX_URL=your_dropbox_url`
   - `HEALTHCHECK_URL=your_healthcheck_url`

2. Copy entire `vlc-player` folder to SD card at `~/vlc-player/` (or `/home/<username>/vlc-player/`)

3. On Raspberry Pi, run:
   ```bash
   sudo ~/vlc-player/bootstrap.sh
   ```
   Note: The username is auto-detected (works with 'admin', 'user', or any username)

That's it! The bootstrap script follows a 4-step process:

**Step 0: Setup Configuration**
- Copies `config.env` to `/etc/vlc-player/config`
- Loads all configuration values

**Step 1: Download All Files**
- Set the system hostname to your device ID
- Install VLC if needed
- Use pre-installed files (if present) or download from GitHub
- Sync media from Dropbox (immediate, not waiting for timer)
- Check for code updates from GitHub

**Step 2: Setup Services**
- Install systemd services
- Install watchdog cron (auto-restart if crashed)

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

# GitHub (shared across all devices)
GITHUB_TOKEN=ghp_your_shared_token_here

# Dropbox (shared)
DROPBOX_URL=https://www.dropbox.com/scl/fo/YOUR_FOLDER_ID/...?dl=1

# Healthcheck (can be per-device or shared)
HEALTHCHECK_URL=https://hc-ping.com/YOUR-UUID-HERE
```

**To change device ID:**
Edit `config.env` before copying to SD card, or edit `/etc/vlc-player/config` on the device and restart services.

## Usage

### Commands
```bash
python3 ~/vlc-player/main.py sync         # Download media from Dropbox
python3 ~/vlc-player/main.py play          # Play playlist with VLC
python3 ~/vlc-player/code_update.py        # Check for code updates and install if available
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
1. **Config**: Copies `config.env` to `/etc/vlc-player/config`
2. **Downloads**: Installs VLC, uses pre-installed files or downloads from GitHub, syncs media from Dropbox
3. **Setup**: Installs systemd services and watchdog cron
4. **Start**: Launches VLC player with playlist (only after everything is ready)

### Runtime Operation
1. **Maintenance (every 5 min)**: Syncs media from Dropbox AND checks for code updates
   - Downloads Dropbox folder → extracts to temp → atomic swap to `media/`
   - Checks GitHub for new code version → downloads and installs if available
2. **Play**: VLC runs in loop mode, auto-restarts if it crashes

## Device Identification

Device ID is stored in `config.env` (or `/etc/vlc-player/config` on device). This ID is:
- Set in `config.env` before copying to SD card
- Used as the system hostname
- Included in Healthchecks.io pings for device-level monitoring

To check device ID:
```bash
grep DEVICE_ID /etc/vlc-player/config
hostname
```

To change device ID:
```bash
sudo nano /etc/vlc-player/config
# Change DEVICE_ID=berlin1 to DEVICE_ID=new-name
sudo hostnamectl set-hostname new-name
sudo systemctl restart vlc-player
```

## Reliability Features

### Retry Logic
If Dropbox download fails (network issues), the sync retries up to 3 times with 30-minute delays between attempts.

### Heartbeat Monitoring
After each successful sync, a ping is sent to [Healthchecks.io](https://healthchecks.io) with the device ID. Configure your URL in `config.env`:
```bash
HEALTHCHECK_URL=https://hc-ping.com/YOUR-UUID-HERE
```
You'll be alerted if a device stops syncing. The device ID appears in the ping for easy identification.

### Watchdog Cron
A cron job runs every 5 minutes to check if Python and VLC are running. If either dies or freezes, the service is automatically restarted:
```
*/5 * * * * (pgrep -f "main.py play" && pgrep -x vlc) || systemctl restart vlc-player
```

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
├── main.py              # Core script (sync, play)
├── code_update.py       # Code update script (checks GitHub)
├── bootstrap.sh          # Bootstrap installer
├── config.env            # Configuration file (all settings)
├── media/               # Downloaded media (auto-synced)
│   ├── playlist.m3u
│   ├── playlist_local.m3u
│   └── *.mp4
└── systemd/             # Service files
    ├── vlc-maintenance.service  # Sync + code update
    ├── vlc-maintenance.timer    # Every 5 min
    └── vlc-player.service       # VLC player
```

Configuration is stored at `/etc/vlc-player/config` (copied from `config.env` during bootstrap).

## Requirements

- Raspberry Pi (any model with display)
- Raspberry Pi OS
- VLC (`sudo apt install vlc`)
- Internet connection (for Dropbox sync and GitHub updates)

## Troubleshooting

**No video playing?**
```bash
journalctl -u vlc-player -n 50   # Check logs
python3 ~/vlc-player/main.py sync  # Manual sync
ls ~/vlc-player/media/    # Check downloaded files
```

**Sync not working?**
```bash
systemctl status vlc-maintenance.timer  # Check timer
journalctl -u vlc-maintenance -f         # View maintenance logs
# Check config file
cat /etc/vlc-player/config
```

**Display issues?**
Make sure `DISPLAY=:0` is set. The player runs on the primary display.

**Check device ID?**
```bash
grep DEVICE_ID /etc/vlc-player/config
hostname
```

**Authentication errors?**
Make sure `GITHUB_TOKEN` is set correctly in `/etc/vlc-player/config`:
```bash
cat /etc/vlc-player/config | grep GITHUB_TOKEN
```

## License

MIT
