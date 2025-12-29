#!/usr/bin/env python3
"""
VLC Playlist Manager

Downloads and manages M3U playlists with media files for VLC playback.
Supports remote playlist fetching, parallel downloads, and local caching.
"""

import logging
import os
import subprocess
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse, unquote
from urllib.request import urlopen, Request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Application configuration."""
    vlc_path: Path = field(default_factory=lambda: Path("/Applications/VLC.app/Contents/MacOS/VLC"))
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent.resolve())
    media_dir: Path = field(default=None)
    default_playlist: Path = field(default=None)
    max_download_workers: int = 4
    download_timeout: int = 30
    user_agent: str = "VLC-Playlist-Manager/1.0"
    
    def __post_init__(self):
        if self.media_dir is None:
            self.media_dir = self.base_dir / "media"
        if self.default_playlist is None:
            self.default_playlist = self.base_dir / "Playlist" / "playlist 1.m3u"


@dataclass
class PlaylistEntry:
    """Represents a single entry in an M3U playlist."""
    url: str
    duration: int = -1
    title: str = ""
    
    @property
    def filename(self) -> str:
        """Extract filename from URL."""
        parsed = urlparse(self.url)
        name = os.path.basename(unquote(parsed.path))
        return name if name else f"media_{hashlib.md5(self.url.encode()).hexdigest()[:8]}"
    
    @property
    def is_remote(self) -> bool:
        """Check if this is a remote URL."""
        return self.url.startswith(('http://', 'https://'))


class M3UParser:
    """Parser for M3U/M3U8 playlist files."""
    
    @staticmethod
    def parse(content: str) -> list[PlaylistEntry]:
        """Parse M3U content and return list of playlist entries."""
        entries = []
        lines = content.strip().splitlines()
        
        current_duration = -1
        current_title = ""
        
        for line in lines:
            line = line.strip()
            
            if not line or line == "#EXTM3U":
                continue
            
            if line.startswith("#EXTINF:"):
                # Parse extended info: #EXTINF:duration,title
                try:
                    info = line[8:]  # Remove "#EXTINF:"
                    if ',' in info:
                        duration_str, title = info.split(',', 1)
                        current_duration = int(float(duration_str))
                        current_title = title.strip()
                    else:
                        current_duration = int(float(info))
                except ValueError:
                    pass
            elif line.startswith('#'):
                # Skip other directives
                continue
            else:
                # This is a media URL/path
                entries.append(PlaylistEntry(
                    url=line,
                    duration=current_duration,
                    title=current_title or Path(line).stem
                ))
                current_duration = -1
                current_title = ""
        
        return entries
    
    @staticmethod
    def generate(entries: list[PlaylistEntry], local_paths: dict[str, Path]) -> str:
        """Generate M3U content from entries with updated local paths."""
        lines = ["#EXTM3U"]
        
        for entry in entries:
            # Add extended info
            lines.append(f"#EXTINF:{entry.duration},{entry.title}")
            
            # Use local path if available, otherwise original URL
            if entry.url in local_paths:
                lines.append(str(local_paths[entry.url]))
            else:
                lines.append(entry.url)
        
        return '\n'.join(lines)


class MediaDownloader:
    """Handles downloading media files with progress and retry support."""
    
    def __init__(self, config: Config):
        self.config = config
        self._ensure_media_dir()
    
    def _ensure_media_dir(self) -> None:
        """Create media directory if it doesn't exist."""
        self.config.media_dir.mkdir(parents=True, exist_ok=True)
    
    def _build_request(self, url: str) -> Request:
        """Build a request with proper headers."""
        req = Request(url)
        req.add_header('User-Agent', self.config.user_agent)
        return req
    
    def download_file(self, url: str, filename: str) -> Optional[Path]:
        """Download a single file.
        
        Returns:
            Path to downloaded file, or None if failed.
        """
        destination = self.config.media_dir / filename
        
        # Skip if already exists
        if destination.exists():
            logger.debug(f"Already cached: {filename}")
            return destination
        
        try:
            logger.info(f"Downloading: {filename}")
            req = self._build_request(url)
            
            with urlopen(req, timeout=self.config.download_timeout) as response:
                content = response.read()
            
            # Write to temp file first, then rename (atomic operation)
            temp_path = destination.with_suffix('.tmp')
            temp_path.write_bytes(content)
            temp_path.rename(destination)
            
            logger.info(f"Downloaded: {filename} ({len(content) / 1024:.1f} KB)")
            return destination
            
        except HTTPError as e:
            logger.error(f"HTTP error downloading {filename}: {e.code} {e.reason}")
        except URLError as e:
            logger.error(f"URL error downloading {filename}: {e.reason}")
        except TimeoutError:
            logger.error(f"Timeout downloading {filename}")
        except Exception as e:
            logger.error(f"Failed to download {filename}: {e}")
        
        return None
    
    def download_all(self, entries: list[PlaylistEntry]) -> dict[str, Path]:
        """Download all remote media files in parallel.
        
        Returns:
            Dict mapping original URLs to local paths.
        """
        remote_entries = [e for e in entries if e.is_remote]
        
        if not remote_entries:
            logger.info("No remote files to download")
            return {}
        
        logger.info(f"Downloading {len(remote_entries)} files...")
        local_paths = {}
        
        with ThreadPoolExecutor(max_workers=self.config.max_download_workers) as executor:
            future_to_entry = {
                executor.submit(self.download_file, entry.url, entry.filename): entry
                for entry in remote_entries
            }
            
            for future in as_completed(future_to_entry):
                entry = future_to_entry[future]
                result = future.result()
                if result:
                    local_paths[entry.url] = result
        
        logger.info(f"Downloaded {len(local_paths)}/{len(remote_entries)} files")
        return local_paths


class PlaylistManager:
    """Manages playlist downloading, parsing, and local storage."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.downloader = MediaDownloader(self.config)
    
    def fetch_playlist(self, url: str) -> str:
        """Fetch playlist content from URL."""
        logger.info(f"Fetching playlist: {url}")
        req = Request(url)
        req.add_header('User-Agent', self.config.user_agent)
        
        with urlopen(req, timeout=self.config.download_timeout) as response:
            return response.read().decode('utf-8')
    
    def download_playlist_and_media(self, playlist_url: str) -> Path:
        """Download playlist and all referenced media files.
        
        Args:
            playlist_url: URL to the M3U playlist.
        
        Returns:
            Path to the local playlist file.
        """
        # Fetch and parse playlist
        content = self.fetch_playlist(playlist_url)
        entries = M3UParser.parse(content)
        
        logger.info(f"Found {len(entries)} media entries")
        
        # Download all media files
        local_paths = self.downloader.download_all(entries)
        
        # Generate updated playlist with local paths
        updated_content = M3UParser.generate(entries, local_paths)
        
        # Save playlist
        playlist_path = self.config.media_dir / "playlist.m3u"
        playlist_path.write_text(updated_content)
        
        logger.info(f"Playlist saved: {playlist_path}")
        return playlist_path


class VLCController:
    """Controls VLC media player."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.playlist_manager = PlaylistManager(self.config)
        self._process: Optional[subprocess.Popen] = None
    
    def _validate_vlc(self) -> None:
        """Check if VLC is available."""
        if not self.config.vlc_path.exists():
            raise FileNotFoundError(f"VLC not found at: {self.config.vlc_path}")
    
    def open_with_playlist(self, playlist_url: Optional[str] = None) -> subprocess.Popen:
        """Open VLC with the specified playlist.
        
        Args:
            playlist_url: Optional URL to fetch playlist from. 
                         If None, uses default local playlist.
        
        Returns:
            The VLC subprocess.
        """
        self._validate_vlc()
        
        if playlist_url:
            playlist_path = self.playlist_manager.download_playlist_and_media(playlist_url)
        else:
            playlist_path = self.config.default_playlist
            if not playlist_path.exists():
                raise FileNotFoundError(f"Default playlist not found: {playlist_path}")
        
        logger.info(f"Opening VLC with: {playlist_path}")
        self._process = subprocess.Popen([
            str(self.config.vlc_path),
            str(playlist_path)
        ])
        
        return self._process
    
    @property
    def is_running(self) -> bool:
        """Check if VLC process is still running."""
        return self._process is not None and self._process.poll() is None
    
    def terminate(self) -> None:
        """Terminate VLC process if running."""
        if self.is_running:
            self._process.terminate()
            self._process.wait()
            logger.info("VLC terminated")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="VLC Playlist Manager - Download and play M3U playlists"
    )
    parser.add_argument(
        'url',
        nargs='?',
        help="URL to M3U playlist (uses local playlist if not provided)"
    )
    parser.add_argument(
        '--download-only',
        action='store_true',
        help="Download playlist and media without opening VLC"
    )
    parser.add_argument(
        '--media-dir',
        type=Path,
        help="Directory to store downloaded media"
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Configure
    config = Config()
    if args.media_dir:
        config.media_dir = args.media_dir
    
    if args.download_only and args.url:
        manager = PlaylistManager(config)
        playlist_path = manager.download_playlist_and_media(args.url)
        print(f"Downloaded to: {playlist_path}")
    else:
        vlc = VLCController(config)
        vlc.open_with_playlist(args.url)
        print("VLC opened with playlist!")


if __name__ == "__main__":
    main()
