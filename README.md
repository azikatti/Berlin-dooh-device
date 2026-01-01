# VLC Playlist Player

Syncs media from Dropbox and plays on loop using VLC. Designed for Raspberry Pi digital signage.

## Quick Install (Raspberry Pi)

```bash
curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash
```

You'll be prompted to enter a **device ID** (e.g., `berlin-01`, `screen-lobby`). This ID is used for:
- System hostname
- Heartbeat reporting

For automated installs:
```bash
curl ... | sudo DEVICE_ID=berlin-01 bash
```

That's it! The script will:
- Set the system hostname to your device ID
- Install VLC if needed
- Download the player files
- Set up automatic sync every 5 minutes
- Install watchdog cron (auto-restart if crashed)
- Start playing your playlist

## Manual Setup

### 1. Clone the repo
```bash
git clone https://github.com/azikatti/Berlin-dooh-device.git /home/pi/vlc-player
cd /home/pi/vlc-player
```

### 2. Configure your Dropbox folder
Edit `main.py` and update the `DROPBOX_URL` with your shared folder link:
```python
DROPBOX_URL = "https://www.dropbox.com/scl/fo/YOUR_FOLDER_ID/...?dl=1"
```

### 3. Install
```bash
sudo ./install.sh
```
You'll be prompted for a device ID.

## Usage

### Commands
```bash
python3 main.py sync    # Download media from Dropbox
python3 main.py play    # Play playlist with VLC
```

### Service Management
```bash
systemctl status vlc-player      # Check player status
systemctl status vlc-sync.timer  # Check sync timer
systemctl restart vlc-player     # Restart player
journalctl -u vlc-player -f      # View player logs
journalctl -u vlc-sync -f        # View sync logs
```

## How It Works

1. **Sync (every 5 min)**: Downloads your Dropbox folder → extracts to temp → atomic swap to `media/`
2. **Play**: VLC runs in loop mode, auto-restarts if it crashes

## Device Identification

Each device has a unique ID stored in `/home/pi/vlc-player/.device`. This ID is:
- Set during installation (prompted or via `DEVICE_ID` env var)
- Used as the system hostname
- Included in Healthchecks.io pings for device-level monitoring

To check device ID:
```bash
cat /home/pi/vlc-player/.device
```

To change device ID:
```bash
echo "DEVICE_ID=new-name" | sudo tee /home/pi/vlc-player/.device
sudo hostnamectl set-hostname new-name
```

## Reliability Features

### Retry Logic
If Dropbox download fails (network issues), the sync retries up to 3 times with 30-minute delays between attempts.

### Heartbeat Monitoring
After each successful sync, a ping is sent to [Healthchecks.io](https://healthchecks.io) with the device ID. Configure your own URL in `main.py`:
```python
HEALTHCHECK_URL = "https://hc-ping.com/YOUR-UUID-HERE"
```
You'll be alerted if a device stops syncing. The device ID appears in the ping for easy identification.

### Watchdog Cron
A cron job runs every 5 minutes to check if Python and VLC are running. If either dies or freezes, the service is automatically restarted:
```
*/5 * * * * (pgrep -f "main.py play" && pgrep -x vlc) || systemctl restart vlc-player
```

### Auto-Update Mechanism

The player automatically checks GitHub every 5 minutes for code updates. If a new version is detected (by comparing the `VERSION` constant in `main.py`), the update script downloads and installs the latest code, then restarts services.

**To trigger an update:**
1. Update code in GitHub
2. Update `VERSION` constant in `main.py` (e.g., `VERSION = "1.0.1"`)
3. Devices will automatically update within 5 minutes

**Check current version:**
```bash
grep VERSION /home/pi/vlc-player/main.py
```

**Manual update:**
```bash
sudo /home/pi/vlc-player/update.sh
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

## File Structure

```
/home/pi/vlc-player/
├── main.py              # Core script (sync + play)
├── .device              # Device ID config
├── media/               # Downloaded media (auto-synced)
│   ├── playlist.m3u
│   ├── playlist_local.m3u
│   └── *.mp4
└── systemd/             # Service files
```

## Requirements

- Raspberry Pi (any model with display)
- Raspberry Pi OS
- VLC (`sudo apt install vlc`)
- Internet connection (for Dropbox sync)

## Troubleshooting

**No video playing?**
```bash
journalctl -u vlc-player -n 50   # Check logs
python3 /home/pi/vlc-player/main.py sync  # Manual sync
ls /home/pi/vlc-player/media/    # Check downloaded files
```

**Sync not working?**
```bash
systemctl status vlc-sync.timer  # Check timer
curl -I "YOUR_DROPBOX_URL"       # Test URL
```

**Display issues?**
Make sure `DISPLAY=:0` is set. The player runs on the primary display.

**Check device ID?**
```bash
cat /home/pi/vlc-player/.device
hostname
```

## License

MIT
