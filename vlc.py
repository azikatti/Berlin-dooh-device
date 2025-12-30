#!/usr/bin/env python3
"""
VLC Playlist Manager

Downloads a Dropbox folder containing playlist.m3u and media files,
extracts everything locally, and plays using VLC.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.error import URLError, HTTPError
from urllib.request import urlopen, Request, build_opener, HTTPRedirectHandler, HTTPCookieProcessor
from http.cookiejar import CookieJar

# =============================================================================
# CONFIGURATION - Update this URL to your Dropbox shared folder
# =============================================================================
DROPBOX_FOLDER_URL = "https://www.dropbox.com/scl/fo/c98dl5jsxp3ae90yx9ww4/AD3YT1lVanI36T3pUaN_crU?rlkey=fzm1pc1qyhl4urkfo7kk3ftss&st=846rj2qj&dl=1"
# =============================================================================

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
    playlist_filename: str = "playlist.m3u"
    download_timeout: int = 300  # 5 minutes for large folders
    user_agent: str = "VLC-Playlist-Manager/1.0"
    
    def __post_init__(self):
        if self.media_dir is None:
            self.media_dir = self.base_dir / "media"


class DropboxFolderDownloader:
    """Downloads and extracts Dropbox shared folders."""
    
    def __init__(self, config: Config):
        self.config = config
        # Create opener with cookie and redirect support for Dropbox
        self.cookie_jar = CookieJar()
        self.opener = build_opener(
            HTTPCookieProcessor(self.cookie_jar),
            HTTPRedirectHandler()
        )
    
    def _ensure_media_dir(self) -> None:
        """Create media directory if it doesn't exist."""
        self.config.media_dir.mkdir(parents=True, exist_ok=True)
    
    def _build_request(self, url: str) -> Request:
        """Build a request with proper headers for Dropbox."""
        req = Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        req.add_header('Accept', '*/*')
        req.add_header('Accept-Language', 'en-US,en;q=0.9')
        return req
    
    def _ensure_direct_download_url(self, url: str) -> str:
        """Ensure URL has dl=1 for direct download."""
        if 'dl=0' in url:
            url = url.replace('dl=0', 'dl=1')
        elif 'dl=1' not in url:
            if '?' in url:
                url += '&dl=1'
            else:
                url += '?dl=1'
        return url
    
    def download_and_extract(self, folder_url: str) -> Path:
        """Download Dropbox folder as zip and extract to media directory.
        
        Args:
            folder_url: Dropbox shared folder URL.
        
        Returns:
            Path to the media directory containing extracted files.
        """
        self._ensure_media_dir()
        
        # Ensure direct download
        folder_url = self._ensure_direct_download_url(folder_url)
        
        logger.info(f"Downloading Dropbox folder...")
        logger.debug(f"URL: {folder_url}")
        
        try:
            req = self._build_request(folder_url)
            
            # Download to temp file using opener with cookie/redirect support
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
                
                with self.opener.open(req, timeout=self.config.download_timeout) as response:
                    content = response.read()
                    tmp_file.write(content)
                
                size_mb = len(content) / 1024 / 1024
                logger.info(f"Downloaded: {size_mb:.1f} MB")
            
            # Extract zip
            logger.info("Extracting files...")
            
            with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                logger.info(f"Found {len(file_list)} items in archive")
                
                for file_info in zip_ref.infolist():
                    if file_info.is_dir():
                        continue
                    
                    # Get the filename without the top-level folder
                    # Dropbox zips have format: FolderName/file.ext
                    parts = Path(file_info.filename).parts
                    if len(parts) > 1:
                        # Skip the top-level folder
                        relative_path = Path(*parts[1:])
                    else:
                        relative_path = Path(file_info.filename)
                    
                    # Skip hidden files
                    if relative_path.name.startswith('.'):
                        continue
                    
                    # Extract to media directory
                    dest_path = self.config.media_dir / relative_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with zip_ref.open(file_info) as src:
                        dest_path.write_bytes(src.read())
                    
                    logger.info(f"Extracted: {relative_path.name}")
            
            # Clean up temp file
            tmp_path.unlink()
            
            logger.info(f"All files extracted to: {self.config.media_dir}")
            return self.config.media_dir
            
        except HTTPError as e:
            logger.error(f"HTTP error downloading folder: {e.code} {e.reason}")
            raise
        except URLError as e:
            logger.error(f"URL error downloading folder: {e.reason}")
            raise
        except zipfile.BadZipFile:
            logger.error("Downloaded file is not a valid zip archive. Make sure you're using a folder link, not a file link.")
            raise
        except Exception as e:
            logger.error(f"Failed to download folder: {e}")
            raise


class PlaylistProcessor:
    """Processes M3U playlists to use local file paths."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def find_playlist(self) -> Optional[Path]:
        """Find the playlist file in media directory."""
        # First, check for the expected filename
        playlist_path = self.config.media_dir / self.config.playlist_filename
        if playlist_path.exists():
            logger.info(f"Found playlist: {playlist_path}")
            return playlist_path
        
        # Search for any .m3u file
        m3u_files = list(self.config.media_dir.glob("**/*.m3u"))
        if m3u_files:
            logger.info(f"Found playlist: {m3u_files[0]}")
            return m3u_files[0]
        
        logger.warning("No playlist file found!")
        return None
    
    def update_playlist_paths(self, playlist_path: Path) -> Path:
        """Update playlist to use local file paths.
        
        Args:
            playlist_path: Path to the M3U playlist file.
        
        Returns:
            Path to the updated playlist.
        """
        logger.info("Updating playlist with local paths...")
        
        content = playlist_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.splitlines()
        updated_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            if not stripped or stripped.startswith('#'):
                # Keep comments and metadata as-is
                updated_lines.append(line)
            else:
                # This is a media file reference - extract just the filename
                original_filename = Path(stripped).name
                
                # Look for the file in media directory
                local_file = self.config.media_dir / original_filename
                
                if local_file.exists():
                    updated_lines.append(str(local_file))
                    logger.debug(f"Mapped: {original_filename}")
                else:
                    # Try to find the file anywhere in media directory
                    found_files = list(self.config.media_dir.glob(f"**/{original_filename}"))
                    if found_files:
                        updated_lines.append(str(found_files[0]))
                        logger.debug(f"Found: {original_filename}")
                    else:
                        # Keep original reference
                        updated_lines.append(line)
                        logger.warning(f"Media file not found: {original_filename}")
        
        # Write updated playlist
        updated_playlist = self.config.media_dir / "playlist_local.m3u"
        updated_playlist.write_text('\n'.join(updated_lines))
        
        logger.info(f"Local playlist created: {updated_playlist}")
        return updated_playlist


class VLCController:
    """Controls VLC media player."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.downloader = DropboxFolderDownloader(self.config)
        self.processor = PlaylistProcessor(self.config)
        self._process: Optional[subprocess.Popen] = None
    
    def _validate_vlc(self) -> None:
        """Check if VLC is available."""
        if not self.config.vlc_path.exists():
            raise FileNotFoundError(f"VLC not found at: {self.config.vlc_path}")
    
    def download_and_play(self, dropbox_url: str) -> subprocess.Popen:
        """Download Dropbox folder and play the playlist.
        
        Args:
            dropbox_url: Dropbox shared folder URL.
        
        Returns:
            The VLC subprocess.
        """
        self._validate_vlc()
        
        # Step 1: Download and extract Dropbox folder
        logger.info("=" * 50)
        logger.info("Step 1: Downloading Dropbox folder...")
        logger.info("=" * 50)
        self.downloader.download_and_extract(dropbox_url)
        
        # Step 2: Find playlist
        logger.info("=" * 50)
        logger.info("Step 2: Finding playlist...")
        logger.info("=" * 50)
        playlist_path = self.processor.find_playlist()
        if not playlist_path:
            raise FileNotFoundError(
                f"No {self.config.playlist_filename} found in downloaded files. "
                f"Make sure your Dropbox folder contains a playlist.m3u file."
            )
        
        # Step 3: Update playlist with local paths
        logger.info("=" * 50)
        logger.info("Step 3: Processing playlist...")
        logger.info("=" * 50)
        local_playlist = self.processor.update_playlist_paths(playlist_path)
        
        # Step 4: Open VLC
        logger.info("=" * 50)
        logger.info("Step 4: Starting VLC...")
        logger.info("=" * 50)
        self._process = subprocess.Popen([
            str(self.config.vlc_path),
            str(local_playlist)
        ])
        
        logger.info("VLC started successfully!")
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
        description="VLC Playlist Manager - Download Dropbox folder and play media"
    )
    parser.add_argument(
        'url',
        nargs='?',
        default=DROPBOX_FOLDER_URL,
        help="Dropbox shared folder URL (defaults to DROPBOX_FOLDER_URL)"
    )
    parser.add_argument(
        '--download-only',
        action='store_true',
        help="Download files without opening VLC"
    )
    parser.add_argument(
        '--media-dir',
        type=Path,
        help="Directory to store downloaded media"
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help="Clean media directory before downloading"
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
    
    # Clean if requested
    if args.clean and config.media_dir.exists():
        logger.info(f"Cleaning media directory: {config.media_dir}")
        shutil.rmtree(config.media_dir)
    
    if args.download_only:
        # Just download, don't play
        downloader = DropboxFolderDownloader(config)
        downloader.download_and_extract(args.url)
        
        processor = PlaylistProcessor(config)
        playlist = processor.find_playlist()
        if playlist:
            processor.update_playlist_paths(playlist)
        
        print(f"\nDownloaded to: {config.media_dir}")
        print(f"Contents:")
        for f in config.media_dir.iterdir():
            print(f"  - {f.name}")
    else:
        # Download and play
        vlc = VLCController(config)
        vlc.download_and_play(args.url)
        print("\nVLC opened with playlist!")


if __name__ == "__main__":
    main()
