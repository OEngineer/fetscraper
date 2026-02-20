"""Video downloader with progress tracking and organization."""

import json
import re
from pathlib import Path
from typing import List, Dict, Set, Optional
from bs4 import BeautifulSoup
import click
from tqdm import tqdm

from .client import FetLifeClient
from .config import config
from .search import VideoInfo
from .utils import sanitize_filename, ensure_directory, format_file_size


class DownloadError(Exception):
    """Raised when download fails."""
    pass


class VideoDownloader:
    """Manages video downloads and tracks downloaded files."""

    def __init__(self, client: FetLifeClient, output_dir: Optional[Path] = None):
        """
        Initialize the downloader.

        Args:
            client: Authenticated FetLife client
            output_dir: Base output directory (default from config)
        """
        self.client = client
        self.output_dir = output_dir or config.download_path
        self.download_history_file = self.output_dir / ".download_history.json"
        self.downloaded_ids: Set[str] = self._load_download_history()

    def _load_download_history(self) -> Set[str]:
        """Load history of downloaded video IDs."""
        if self.download_history_file.exists():
            try:
                with open(self.download_history_file, "r") as f:
                    data = json.load(f)
                    return set(data.get("downloaded_videos", []))
            except Exception:
                pass
        return set()

    def _save_download_history(self) -> None:
        """Save history of downloaded video IDs."""
        ensure_directory(self.output_dir)
        try:
            with open(self.download_history_file, "w") as f:
                json.dump({"downloaded_videos": list(self.downloaded_ids)}, f, indent=2)
        except Exception as e:
            click.echo(f"Warning: Failed to save download history: {e}", err=True)

    def _get_video_download_url(self, video_url: str) -> Optional[str]:
        """
        Extract direct download URL from video page.

        Args:
            video_url: URL of the video page

        Returns:
            Direct download URL if found, None otherwise
        """
        try:
            import json
            import html as html_module

            response = self.client.get(video_url)
            soup = BeautifulSoup(response.text, "lxml")

            # FetLife uses Vue components with video data in JSON
            video_component = soup.find(attrs={"data-component": "VideoStoriesGallery"})
            if video_component:
                props_data = video_component.get("data-props", "")
                if props_data:
                    try:
                        props_json = json.loads(html_module.unescape(props_data))
                        # Navigate through the JSON structure
                        entries = props_json.get("preload", {}).get("entries", [])
                        if entries:
                            videos = entries[0].get("attributes", {}).get("videos", [])
                            if videos:
                                # Get the first video's sources
                                sources = videos[0].get("sources", [])
                                if sources:
                                    # Return the HLS stream URL
                                    return sources[0].get("src")
                    except json.JSONDecodeError:
                        pass

            return None

        except Exception as e:
            click.echo(f"Warning: Failed to extract video URL: {e}", err=True)
            return None

    def download_video(self, video_info: VideoInfo, skip_existing: bool = True) -> bool:
        """
        Download a single video.

        Args:
            video_info: Video information
            skip_existing: Skip if already downloaded

        Returns:
            True if download successful, False otherwise
        """
        # Check if already downloaded
        if skip_existing and video_info.video_id in self.downloaded_ids:
            click.echo(f"Skipping {video_info.title} (already downloaded)")
            return True

        # Create user directory
        user_dir = self.output_dir / sanitize_filename(video_info.uploader)
        ensure_directory(user_dir)

        # Generate filename
        safe_title = sanitize_filename(video_info.title)
        filename = f"{safe_title}_{video_info.video_id}.mp4"
        filepath = user_dir / filename

        # Check if file already exists
        if filepath.exists() and skip_existing:
            click.echo(f"Skipping {video_info.title} (file exists)")
            self.downloaded_ids.add(video_info.video_id)
            self._save_download_history()
            return True

        try:
            # Get direct download URL
            click.echo(f"Processing: {video_info.title}")

            # Use download_url from search results if available
            download_url = video_info.download_url
            if not download_url:
                # Fall back to extracting from video page
                download_url = self._get_video_download_url(video_info.url)

            if not download_url:
                click.echo(click.style(f"✗ Could not find download URL for: {video_info.title}", fg="red"))
                return False

            # Ensure URL is absolute
            if not download_url.startswith("http"):
                download_url = config.base_url + download_url

            click.echo(f"Downloading to: {filepath}")

            # Check if it's an HLS stream (m3u8)
            if ".m3u8" in download_url:
                # Use ffmpeg to download HLS stream
                import subprocess
                click.echo("Downloading HLS stream with ffmpeg...")

                cmd = [
                    "ffmpeg",
                    "-i", download_url,
                    "-c", "copy",  # Copy without re-encoding
                    "-bsf:a", "aac_adtstoasc",  # Fix audio format if needed
                    "-y",  # Overwrite output file
                    str(filepath)
                ]

                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=600  # 10 minute timeout
                    )
                    if result.returncode != 0:
                        click.echo(f"ffmpeg error: {result.stderr[:200]}")
                        return False
                except subprocess.TimeoutExpired:
                    click.echo("Download timeout (10 minutes)")
                    return False

            else:
                # Regular HTTP download
                response = self.client.session.get(download_url, stream=True, timeout=config.timeout)
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))

                with open(filepath, "wb") as f:
                    with tqdm(total=total_size, unit="B", unit_scale=True, desc=video_info.title[:30]) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))

            # Mark as downloaded
            self.downloaded_ids.add(video_info.video_id)
            self._save_download_history()

            file_size = filepath.stat().st_size
            click.echo(click.style(f"✓ Downloaded: {video_info.title} ({format_file_size(file_size)})", fg="green"))
            return True

        except Exception as e:
            click.echo(click.style(f"✗ Download failed for {video_info.title}: {e}", fg="red"))
            # Clean up partial download
            if filepath.exists():
                try:
                    filepath.unlink()
                except Exception:
                    pass
            return False

    def download_videos(self, videos: List[VideoInfo], skip_existing: bool = True) -> Dict[str, int]:
        """
        Download multiple videos.

        Args:
            videos: List of videos to download
            skip_existing: Skip already downloaded videos

        Returns:
            Dictionary with download statistics
        """
        stats = {"total": len(videos), "success": 0, "failed": 0, "skipped": 0}

        click.echo(f"\nStarting download of {len(videos)} videos...")
        click.echo("=" * 60)

        for idx, video in enumerate(videos, 1):
            click.echo(f"\n[{idx}/{len(videos)}] {video.title}")
            click.echo(f"Uploader: {video.uploader}")
            if video.duration:
                from .utils import format_duration
                click.echo(f"Duration: {format_duration(video.duration)}")

            if skip_existing and video.video_id in self.downloaded_ids:
                click.echo(click.style("⊘ Already downloaded (skipping)", fg="yellow"))
                stats["skipped"] += 1
                continue

            success = self.download_video(video, skip_existing=skip_existing)
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1

        # Print summary
        click.echo("\n" + "=" * 60)
        click.echo("Download Summary:")
        click.echo(f"  Total videos: {stats['total']}")
        click.echo(click.style(f"  ✓ Successfully downloaded: {stats['success']}", fg="green"))
        if stats["skipped"] > 0:
            click.echo(click.style(f"  ⊘ Skipped (already downloaded): {stats['skipped']}", fg="yellow"))
        if stats["failed"] > 0:
            click.echo(click.style(f"  ✗ Failed: {stats['failed']}", fg="red"))

        return stats
