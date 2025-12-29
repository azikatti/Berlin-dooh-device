import subprocess
import tempfile
from urllib.request import urlopen

# Path to VLC
VLC_PATH = "/Applications/VLC.app/Contents/MacOS/VLC"

# Playlist path (m3u file)
PLAYLIST_PATH = "/Users/azeraliyev/source/playground/Playlist/playlist 1.m3u"


def fetch_playlist_from_url(url: str) -> str:
    """Fetch playlist from URL and save to a temp file.
    
    Args:
        url: URL to fetch the m3u playlist from.
    
    Returns:
        Path to the downloaded playlist file.
    """
    with urlopen(url) as response:
        content = response.read()
    
    # Save to temp file
    temp_file = tempfile.NamedTemporaryFile(suffix='.m3u', delete=False)
    temp_file.write(content)
    temp_file.close()
    
    return temp_file.name


def open_vlc_with_playlist(playlist_url: str = None):
    """Open VLC with the playlist.
    
    Args:
        playlist_url: Optional URL to fetch playlist from. If None, uses local file.
    """
    if playlist_url:
        playlist_path = fetch_playlist_from_url(playlist_url)
    else:
        playlist_path = PLAYLIST_PATH
    
    subprocess.Popen([VLC_PATH, playlist_path])
    print("VLC opened with playlist!")


if __name__ == "__main__":
    # Use local playlist
    open_vlc_with_playlist()
    
    # Or fetch from URL:
    # open_vlc_with_playlist("https://example.com/playlist.m3u")
