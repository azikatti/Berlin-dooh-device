# VLC Playlist Player

Syncs media from Dropbox and plays on loop using VLC. Designed for Raspberry Pi digital signage.

## Quick Install (Raspberry Pi)

```bash
curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash
```

That's it! The script will:
- Install VLC if needed
- Download the player files
- Set up automatic sync every 5 minutes
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

## License

MIT

