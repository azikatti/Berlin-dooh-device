# VLC Playlist Player

Syncs media from a ZIP URL (e.g. Dropbox) and plays on loop using VLC. Designed for Raspberry Pi digital signage, but works on any Linux box with VLC.

### Configuration

All configuration lives in `config.env`:

```bash
# Device-specific
DEVICE_ID=berlin1

# Content ZIP URL (e.g. Dropbox ?dl=1 link)
DROPBOX_URL=https://www.dropbox.com/scl/fo/YOUR_FOLDER_ID/...?dl=1
```

Place `config.env` in the same directory as the Python scripts.

### One-Line Install (Recommended, Raspberry Pi)

On a fresh device:

```bash
curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/bootstrap.sh | sudo bash
```

This will:

- Install `git` and `vlc`
- Clone/update the repo to `~/vlc-player`
- Ensure `config.env` exists
- Install + enable `vlc-player.service` and `vlc-maintenance.timer`
- Start playback and periodic media sync

### Manual Installation (Alternative)

1. Copy the project folder (e.g. `vlc-player/`) to the device:
   - `main.py`
   - `media_sync.py`
   - `config.py`
   - `config.env`
   - `systemd/` (with service + timer units)
2. Install VLC:
   ```bash
   sudo apt update && sudo apt install -y vlc git
   ```
3. Enable the services:
   ```bash
   cd ~/vlc-player
   sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable vlc-player vlc-maintenance.timer
   sudo systemctl start vlc-player vlc-maintenance.timer
   ```

### Usage

- **Manual media sync**:
  ```bash
  python3 ~/vlc-player/media_sync.py
  ```
- **Manual playback**:
  ```bash
  python3 ~/vlc-player/main.py
  ```
- **Service management**:
  ```bash
  systemctl status vlc-player
  systemctl status vlc-maintenance.timer
  systemctl restart vlc-player
  journalctl -u vlc-player -f
  journalctl -u vlc-maintenance -f
  ```

### Automatic Code Updates (Every 4 Hours, Optional)

Code updates are git-based and handled by `code_update.py`.

1. Install the code-update units:

   ```bash
   cd ~/vlc-player
   sudo cp systemd/vlc-code-update.service systemd/vlc-code-update.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable vlc-code-update.timer
   sudo systemctl start vlc-code-update.timer
   ```

2. To trigger a manual update at any time:

   ```bash
   cd ~/vlc-player
   python3 code_update.py
   ```

This will run `git fetch` + `git reset --hard origin/main` and restart `vlc-player` and `vlc-maintenance.timer`.

### Migrating Existing Devices to Git-Based Setup

On a device that already has an older `vlc-player` install:

```bash
cd /home/pi
curl -sSL https://raw.githubusercontent.com/azikatti/Berlin-dooh-device/main/migrate_to_git.sh -o migrate_to_git.sh
chmod +x migrate_to_git.sh
sudo ./migrate_to_git.sh
```

The script will:

- Stop existing services
- Back up the old `~/vlc-player` to `~/vlc-player-old-<timestamp>`
- Run the latest `bootstrap.sh` from GitHub
- Restore `config.env` and `media/` from the backup (if present)
- Restart `vlc-player` and `vlc-maintenance.timer`

You can then optionally enable the 4‑hour code update timer as described above.

### How It Works

- `media_sync.py` downloads a ZIP from `DROPBOX_URL`, extracts into a staging directory, checks that at least one `.m3u` playlist exists, then atomically swaps it into `media/`.
- `main.py` looks for `media/playlist.m3u` and starts VLC in fullscreen loop mode.
- `vlc-maintenance.timer` runs `media_sync.py` periodically so content stays up to date.
- `vlc-code-update.timer` (optional) runs `code_update.py` every 4 hours to force a git-based code update.

### File Structure

```text
~/vlc-player/  (or /home/<username>/vlc-player/)
├── main.py                   # VLC player script (play only)
├── media_sync.py             # Media sync script (downloads ZIP + extracts)
├── config.py                 # Shared configuration utilities
├── config.env                # Configuration file (DEVICE_ID, DROPBOX_URL)
├── code_update.py            # Git-based code updater (optional timer)
├── migrate_to_git.sh         # One-shot migration helper for old installs
├── media/                    # Downloaded media
│   ├── playlist.m3u
│   └── *.mp4
└── systemd/                  # Service files
    ├── vlc-player.service
    ├── vlc-maintenance.service
    ├── vlc-maintenance.timer
    ├── vlc-code-update.service   # optional
    ├── vlc-code-update.timer     # optional
```

### Requirements

- Raspberry Pi (or any Linux device with display)
- Raspberry Pi OS / Debian-based distro
- VLC (`sudo apt install vlc`)
- Git (`sudo apt install git`)
- Internet connection (for content sync and code updates)

### Troubleshooting

- **No video playing?**
  ```bash
  journalctl -u vlc-player -n 50
  python3 ~/vlc-player/media_sync.py
  ls ~/vlc-player/media/
  ```
- **Sync not working?**
  ```bash
  systemctl status vlc-maintenance.timer
  journalctl -u vlc-maintenance -f
  cat ~/vlc-player/config.env
  ```
- **Code updates not running (optional)?**
  ```bash
  systemctl status vlc-code-update.timer
  journalctl -u vlc-code-update.service -n 50
  ```

## License

MIT
