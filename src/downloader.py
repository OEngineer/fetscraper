"""Video downloader with progress tracking and organization."""

import itertools
import html
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Set, Optional
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
        # Guards downloaded_ids + history file writes, and the position counter below,
        # against concurrent access from multiple download worker threads.
        self._history_lock = threading.Lock()
        self._position_counter = itertools.count()

    def _extract_embedded_hls_urls(self, html_text: str) -> List[str]:
        """Extract signed HLS URLs embedded directly in the video page HTML."""
        found = []
        urls: List[str] = []
        patterns = [
            r"https?://[^\\\"'<> \n]+?\.m3u8[^\\\"'<> \n]*",
            r"https?:\\?/\\?/[^\"'<> \n]+?\.m3u8[^\"'<> \n]*",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, html_text):
                found.append((match.start(), match.group(0)))

        for _, match in sorted(found):
            url = html.unescape(match).replace("\\/", "/")
            try:
                url = url.encode("utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                pass

            if ".m3u8" in url:
                if url not in urls:
                    urls.append(url)

        return urls

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
        """Save history of downloaded video IDs. Caller must hold self._history_lock."""
        ensure_directory(self.output_dir)
        try:
            with open(self.download_history_file, "w") as f:
                json.dump({"downloaded_videos": list(self.downloaded_ids)}, f, indent=2)
        except Exception as e:
            tqdm.write(f"Warning: Failed to save download history: {e}")

    def _get_video_download_url(self, video_url: str) -> Optional[str]:
        """
        Extract direct download URL from video page.

        Args:
            video_url: URL of the video page

        Returns:
            Direct download URL if found, None otherwise
        """
        try:
            response = self.client.get(video_url)
            soup = BeautifulSoup(response.text, "lxml")

            # The video page embeds its story data (including video sources) as a
            # <script type="application/json" id="story-data"> block.
            story_data_elem = soup.find("script", id="story-data", type="application/json")
            if story_data_elem and story_data_elem.string:
                try:
                    story_data = json.loads(story_data_elem.string)
                except json.JSONDecodeError:
                    story_data = {}

                videos = story_data.get("attributes", {}).get("videos", [])

                if videos:
                    # Prefer the video whose path matches the requested video ID, in case
                    # the story bundles more than one video.
                    video_id_match = re.search(r"/videos/(\d+)", video_url)
                    video_data = videos[0]
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        for candidate in videos:
                            if str(candidate.get("id")) == video_id:
                                video_data = candidate
                                break

                    sources = video_data.get("sources", [])
                    if sources:
                        # Return the HLS master playlist URL (full quality)
                        return sources[0].get("src")

            hls_urls = self._extract_embedded_hls_urls(response.text)
            if hls_urls:
                return hls_urls[0]

            return None

        except Exception as e:
            tqdm.write(f"Warning: Failed to extract video URL: {e}")
            return None

    def download_video(self, video_info: VideoInfo, skip_existing: bool = True, position: Optional[int] = None) -> bool:
        """
        Download a single video.

        Safe to call concurrently from multiple threads (e.g. via
        `download_videos_as_found`) for different videos.

        Args:
            video_info: Video information
            skip_existing: Skip if already downloaded
            position: Terminal line offset for this download's progress bar, so
                concurrent downloads don't overwrite each other's line. None lets
                tqdm pick automatically (fine for single-threaded use).

        Returns:
            True if download successful, False otherwise
        """
        # Check if already downloaded
        with self._history_lock:
            if skip_existing and video_info.video_id in self.downloaded_ids:
                tqdm.write(f"Skipping {video_info.title} (already downloaded)")
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
            tqdm.write(f"Skipping {video_info.title} (file exists)")
            with self._history_lock:
                self.downloaded_ids.add(video_info.video_id)
                self._save_download_history()
            return True

        try:
            # Get direct download URL
            tqdm.write(f"Processing: {video_info.title}")

            # Use download_url from search results if available
            download_url = video_info.download_url
            if not download_url:
                # Fall back to extracting from video page
                download_url = self._get_video_download_url(video_info.url)

            if not download_url:
                tqdm.write(click.style(f"✗ Could not find download URL for: {video_info.title}", fg="red"))
                return False

            # Ensure URL is absolute
            if not download_url.startswith("http"):
                download_url = config.base_url + download_url

            tqdm.write(f"Downloading to: {filepath}")

            # Check if it's an HLS stream (m3u8)
            if ".m3u8" in download_url:
                # Use ffmpeg to download HLS stream
                import subprocess
                tqdm.write("Downloading HLS stream with ffmpeg...")

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
                        tqdm.write(f"ffmpeg error: {result.stderr[:200]}")
                        return False
                except subprocess.TimeoutExpired:
                    tqdm.write("Download timeout (10 minutes)")
                    return False

            else:
                # Regular HTTP download
                response = self.client.session.get(download_url, stream=True, timeout=config.timeout)
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))

                with open(filepath, "wb") as f:
                    with tqdm(total=total_size, unit="B", unit_scale=True, desc=video_info.title[:30], position=position, leave=False) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))

            # Mark as downloaded
            with self._history_lock:
                self.downloaded_ids.add(video_info.video_id)
                self._save_download_history()

            file_size = filepath.stat().st_size
            tqdm.write(click.style(f"✓ Downloaded: {video_info.title} ({format_file_size(file_size)})", fg="green"))
            return True

        except Exception as e:
            tqdm.write(click.style(f"✗ Download failed for {video_info.title}: {e}", fg="red"))
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

    def download_videos_as_found(
        self,
        videos: Iterable[VideoInfo],
        skip_existing: bool = True,
        max_workers: Optional[int] = None,
    ) -> Dict[str, int]:
        """
        Download videos from a (possibly still-growing) iterable as they arrive.

        Unlike `download_videos`, this doesn't require the full list of videos up
        front: `videos` can be a generator that's still paging through search
        results. Videos are submitted to a thread pool as soon as they're yielded,
        so downloading overlaps with fetching later results instead of waiting for
        every page to finish first.

        Args:
            videos: Iterable (e.g. a generator) of videos to download
            skip_existing: Skip already downloaded videos
            max_workers: Number of concurrent download workers (default: config.max_workers)

        Returns:
            Dictionary with download statistics
        """
        max_workers = max_workers or config.max_workers
        stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0}

        click.echo(f"\nStarting download (up to {max_workers} at a time) as results are found...")
        click.echo("=" * 60)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for video in videos:
                stats["total"] += 1

                if skip_existing and video.video_id in self.downloaded_ids:
                    tqdm.write(f"⊘ Already downloaded (skipping): {video.title}")
                    stats["skipped"] += 1
                    continue

                position = next(self._position_counter) % max_workers
                future = executor.submit(self.download_video, video, skip_existing, position)
                futures[future] = video

            for future in as_completed(futures):
                video = futures[future]
                try:
                    success = future.result()
                except Exception as e:
                    tqdm.write(click.style(f"✗ Download failed for {video.title}: {e}", fg="red"))
                    success = False

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
