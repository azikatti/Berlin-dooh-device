#!/usr/bin/env python3
"""
Raspberry Pi Bootloader for VLC Playlist Manager

Checks GitHub for updates, downloads and installs them, then runs vlc.py.
Designed to run on boot via systemd or cron.
"""

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen, Request
import json

# Configure logging
LOG_FILE = Path(__file__).parent / "bootloader.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class BootloaderConfig:
    """Bootloader configuration."""
    # GitHub repository settings
    github_owner: str = "azikatti"
    github_repo: str = "Berlin-dooh-device"
    github_branch: str = "main"
    github_token: Optional[str] = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN"))
    
    # Local paths
    app_dir: Path = field(default_factory=lambda: Path(__file__).parent.resolve())
    version_file: Path = field(default=None)
    python_executable: str = field(default_factory=lambda: sys.executable)
    
    # Timing
    network_retry_attempts: int = 5
    network_retry_delay: int = 10  # seconds
    update_check_timeout: int = 30  # seconds
    
    # Behavior
    auto_reboot_on_failure: bool = False
    run_vlc_after_update: bool = True
    
    def __post_init__(self):
        if self.version_file is None:
            self.version_file = self.app_dir / ".version"
    
    @property
    def github_api_url(self) -> str:
        """GitHub API URL for latest commit."""
        return f"https://api.github.com/repos/{self.github_owner}/{self.github_repo}/commits/{self.github_branch}"
    
    @property
    def github_archive_url(self) -> str:
        """GitHub URL to download repository archive."""
        return f"https://github.com/{self.github_owner}/{self.github_repo}/archive/refs/heads/{self.github_branch}.zip"


class NetworkChecker:
    """Handles network connectivity checks."""
    
    CONNECTIVITY_CHECK_URLS = [
        "https://api.github.com",
        "https://google.com",
        "https://cloudflare.com"
    ]
    
    @staticmethod
    def wait_for_network(max_attempts: int = 5, delay: int = 10) -> bool:
        """Wait for network connectivity.
        
        Returns:
            True if network is available, False otherwise.
        """
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Checking network connectivity (attempt {attempt}/{max_attempts})...")
            
            for url in NetworkChecker.CONNECTIVITY_CHECK_URLS:
                try:
                    req = Request(url, method='HEAD')
                    with urlopen(req, timeout=5):
                        logger.info("Network is available")
                        return True
                except Exception:
                    continue
            
            if attempt < max_attempts:
                logger.warning(f"Network not available, retrying in {delay}s...")
                time.sleep(delay)
        
        logger.error("Network connectivity check failed")
        return False


class GitHubUpdater:
    """Handles checking and downloading updates from GitHub."""
    
    def __init__(self, config: BootloaderConfig):
        self.config = config
    
    def _build_request(self, url: str) -> Request:
        """Build a request with proper headers."""
        req = Request(url)
        req.add_header('User-Agent', 'RaspberryPi-Bootloader/1.0')
        req.add_header('Accept', 'application/vnd.github.v3+json')
        
        if self.config.github_token:
            req.add_header('Authorization', f'token {self.config.github_token}')
        
        return req
    
    def get_local_version(self) -> Optional[str]:
        """Get the locally stored version (commit SHA)."""
        if self.config.version_file.exists():
            return self.config.version_file.read_text().strip()
        
        # Try to get from git if available
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.config.app_dir,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        return None
    
    def get_remote_version(self) -> Optional[str]:
        """Get the latest commit SHA from GitHub."""
        try:
            req = self._build_request(self.config.github_api_url)
            with urlopen(req, timeout=self.config.update_check_timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('sha')
        except Exception as e:
            logger.error(f"Failed to get remote version: {e}")
            return None
    
    def check_for_updates(self) -> tuple[bool, Optional[str]]:
        """Check if updates are available.
        
        Returns:
            Tuple of (update_available, new_version)
        """
        local_version = self.get_local_version()
        remote_version = self.get_remote_version()
        
        logger.info(f"Local version: {local_version[:8] if local_version else 'unknown'}")
        logger.info(f"Remote version: {remote_version[:8] if remote_version else 'unknown'}")
        
        if remote_version is None:
            return False, None
        
        if local_version is None or local_version != remote_version:
            return True, remote_version
        
        return False, remote_version
    
    def download_and_install_update(self, new_version: str) -> bool:
        """Download and install the update using git pull.
        
        Returns:
            True if successful, False otherwise.
        """
        logger.info(f"Installing update: {new_version[:8]}...")
        
        try:
            # Check if this is a git repository
            git_dir = self.config.app_dir / ".git"
            
            if git_dir.exists():
                # Use git pull for updates
                return self._update_via_git(new_version)
            else:
                # Download archive and extract
                return self._update_via_archive(new_version)
                
        except Exception as e:
            logger.error(f"Update failed: {e}")
            return False
    
    def _update_via_git(self, new_version: str) -> bool:
        """Update using git pull."""
        logger.info("Updating via git pull...")
        
        try:
            # Fetch latest changes
            subprocess.run(
                ['git', 'fetch', 'origin', self.config.github_branch],
                cwd=self.config.app_dir,
                check=True,
                capture_output=True
            )
            
            # Reset to latest (discards local changes)
            subprocess.run(
                ['git', 'reset', '--hard', f'origin/{self.config.github_branch}'],
                cwd=self.config.app_dir,
                check=True,
                capture_output=True
            )
            
            # Update version file
            self.config.version_file.write_text(new_version)
            
            logger.info("Git update successful")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git update failed: {e}")
            return False
    
    def _update_via_archive(self, new_version: str) -> bool:
        """Update by downloading and extracting archive."""
        import zipfile
        import tempfile
        import shutil
        
        logger.info("Updating via archive download...")
        
        try:
            # Download archive
            req = self._build_request(self.config.github_archive_url)
            with urlopen(req, timeout=60) as response:
                archive_data = response.read()
            
            # Extract to temp directory
            with tempfile.TemporaryDirectory() as temp_dir:
                archive_path = Path(temp_dir) / "update.zip"
                archive_path.write_bytes(archive_data)
                
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Find extracted folder (usually repo-branch/)
                extracted_dirs = [d for d in Path(temp_dir).iterdir() if d.is_dir()]
                if not extracted_dirs:
                    raise Exception("No directory found in archive")
                
                extracted_dir = extracted_dirs[0]
                
                # Copy files to app directory (excluding certain files)
                exclude = {'.git', '.gitignore', 'bootloader.log', '.version', 'media'}
                for item in extracted_dir.iterdir():
                    if item.name in exclude:
                        continue
                    
                    dest = self.config.app_dir / item.name
                    if item.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
            
            # Update version file
            self.config.version_file.write_text(new_version)
            
            logger.info("Archive update successful")
            return True
            
        except Exception as e:
            logger.error(f"Archive update failed: {e}")
            return False


class DependencyManager:
    """Manages Python dependencies."""
    
    def __init__(self, config: BootloaderConfig):
        self.config = config
    
    def install_dependencies(self) -> bool:
        """Install dependencies from requirements.txt or pyproject.toml."""
        requirements_file = self.config.app_dir / "requirements.txt"
        pyproject_file = self.config.app_dir / "pyproject.toml"
        
        try:
            if requirements_file.exists():
                logger.info("Installing dependencies from requirements.txt...")
                subprocess.run(
                    [self.config.python_executable, '-m', 'pip', 'install', '-r', str(requirements_file), '-q'],
                    check=True,
                    capture_output=True
                )
                logger.info("Dependencies installed")
                return True
            
            elif pyproject_file.exists():
                logger.info("Installing dependencies via poetry...")
                # Check if poetry is available
                try:
                    subprocess.run(
                        ['poetry', 'install', '--no-interaction'],
                        cwd=self.config.app_dir,
                        check=True,
                        capture_output=True
                    )
                    logger.info("Poetry dependencies installed")
                    return True
                except FileNotFoundError:
                    logger.warning("Poetry not found, skipping dependency installation")
                    return True
            
            else:
                logger.info("No dependency file found, skipping")
                return True
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Dependency installation failed: {e}")
            return False


class VLCRunner:
    """Handles running the VLC application."""
    
    def __init__(self, config: BootloaderConfig):
        self.config = config
    
    def run(self, use_poetry: bool = False) -> subprocess.Popen:
        """Run vlc.py and return the process."""
        vlc_script = self.config.app_dir / "vlc.py"
        
        if not vlc_script.exists():
            raise FileNotFoundError(f"vlc.py not found at: {vlc_script}")
        
        logger.info("Starting VLC Playlist Manager...")
        
        if use_poetry and (self.config.app_dir / "pyproject.toml").exists():
            cmd = ['poetry', 'run', 'python', str(vlc_script)]
        else:
            cmd = [self.config.python_executable, str(vlc_script)]
        
        process = subprocess.Popen(
            cmd,
            cwd=self.config.app_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        logger.info(f"VLC started with PID: {process.pid}")
        return process


class Bootloader:
    """Main bootloader class that orchestrates the update and run process."""
    
    def __init__(self, config: Optional[BootloaderConfig] = None):
        self.config = config or BootloaderConfig()
        self.network_checker = NetworkChecker()
        self.updater = GitHubUpdater(self.config)
        self.dependency_manager = DependencyManager(self.config)
        self.vlc_runner = VLCRunner(self.config)
    
    def run(self) -> int:
        """Main bootloader execution.
        
        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        logger.info("=" * 50)
        logger.info("Bootloader started")
        logger.info(f"App directory: {self.config.app_dir}")
        logger.info("=" * 50)
        
        try:
            # Step 1: Wait for network
            if not self.network_checker.wait_for_network(
                max_attempts=self.config.network_retry_attempts,
                delay=self.config.network_retry_delay
            ):
                logger.warning("No network, running with current version")
                return self._run_vlc()
            
            # Step 2: Check for updates
            update_available, new_version = self.updater.check_for_updates()
            
            if update_available and new_version:
                logger.info("Update available!")
                
                # Step 3: Download and install update
                if self.updater.download_and_install_update(new_version):
                    logger.info("Update installed successfully")
                    
                    # Step 4: Install dependencies
                    self.dependency_manager.install_dependencies()
                else:
                    logger.warning("Update failed, continuing with current version")
            else:
                logger.info("Already up to date")
            
            # Step 5: Run VLC
            if self.config.run_vlc_after_update:
                return self._run_vlc()
            
            return 0
            
        except Exception as e:
            logger.exception(f"Bootloader error: {e}")
            
            if self.config.auto_reboot_on_failure:
                logger.info("Rebooting system...")
                subprocess.run(['sudo', 'reboot'], check=False)
            
            return 1
    
    def _run_vlc(self) -> int:
        """Run VLC and wait for it to complete."""
        try:
            use_poetry = (self.config.app_dir / "pyproject.toml").exists()
            process = self.vlc_runner.run(use_poetry=use_poetry)
            
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"VLC exited with code: {process.returncode}")
                if stderr:
                    logger.error(f"VLC stderr: {stderr.decode()}")
            
            return process.returncode
            
        except FileNotFoundError as e:
            logger.error(f"Failed to run VLC: {e}")
            return 1


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Raspberry Pi Bootloader - Auto-updates and runs VLC Playlist Manager"
    )
    parser.add_argument(
        '--check-only',
        action='store_true',
        help="Only check for updates, don't install or run"
    )
    parser.add_argument(
        '--force-update',
        action='store_true',
        help="Force update even if already up to date"
    )
    parser.add_argument(
        '--no-vlc',
        action='store_true',
        help="Don't run VLC after update"
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    config = BootloaderConfig()
    
    if args.no_vlc:
        config.run_vlc_after_update = False
    
    if args.check_only:
        # Just check for updates
        if not NetworkChecker.wait_for_network():
            print("No network available")
            sys.exit(1)
        
        updater = GitHubUpdater(config)
        update_available, version = updater.check_for_updates()
        
        if update_available:
            print(f"Update available: {version[:8] if version else 'unknown'}")
        else:
            print("Already up to date")
        
        sys.exit(0)
    
    if args.force_update:
        # Delete version file to force update
        if config.version_file.exists():
            config.version_file.unlink()
    
    bootloader = Bootloader(config)
    sys.exit(bootloader.run())


if __name__ == "__main__":
    main()

