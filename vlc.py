import subprocess
import requests
import time
from urllib.parse import quote

# Path to VLC
VLC_PATH = "/Applications/VLC.app/Contents/MacOS/VLC"

# HTTP API settings
PASSWORD = "pwd"
PLAYLIST_URL = "http://localhost:8080/requests/playlist.json"
STATUS_URL = "http://localhost:8080/requests/status.xml"


# Default local playlist for testing
LOCAL_PLAYLIST = "/Users/azeraliyev/source/playground/Playlist/playlist 1.m3u"


def fetch_playlist_path(url: str = None) -> str:
    """
    Get the playlist path or URL.
    
    Args:
        url: Optional URL to fetch playlist from. If None, returns local path.
    
    Returns:
        Path or URL to the playlist.
    """
    if url:
        # VLC can open URLs directly - just return it
        return url
    
    return LOCAL_PLAYLIST


def open_vlc_with_playlist(playlist_url: str = None, headless: bool = True):
    """Open VLC with the playlist and HTTP interface enabled.
    
    Args:
        playlist_url: Optional URL to fetch playlist from.
        headless: If True, runs VLC without GUI (default: True).
    """
    playlist_path = fetch_playlist_path(playlist_url)
    cmd = [
        VLC_PATH,
        "--intf", "dummy",        # No GUI
        "--extraintf", "http",    # Enable HTTP control interface
        "--http-password", PASSWORD,
        playlist_path
    ]
    
    if not headless:
        cmd.remove("--intf")
        cmd.remove("dummy")
    
    subprocess.Popen(cmd)
    print(f"VLC opened {'(headless)' if headless else ''} with playlist!")


def get_playlist():
    """Get the current playlist from VLC."""
    response = requests.get(PLAYLIST_URL, auth=('', PASSWORD))
    return response.json()['children'][0]


def enqueue_media(file_path):
    """Add a file to the playlist."""
    media_uri = f"file://{file_path}"
    encoded_uri = quote(media_uri, safe='')
    requests.get(f"{STATUS_URL}?command=in_enqueue&input={encoded_uri}", auth=('', PASSWORD))


def play_next():
    """Skip to next track."""
    requests.get(f"{STATUS_URL}?command=pl_next", auth=('', PASSWORD))


if __name__ == "__main__":
    # Option 1: Use local playlist with GUI (for video playback)
    open_vlc_with_playlist(headless=False)
    
    # Option 2: Use a URL
    # open_vlc_with_playlist("https://example.com/playlist.m3u")
    
    # Wait for VLC to start and HTTP interface to be ready
    time.sleep(2)
    
    # Show current playlist
    try:
        playlist = get_playlist()
        print("Current playlist:", playlist)
    except Exception as e:
        print(f"Could not fetch playlist (VLC may still be starting): {e}")

