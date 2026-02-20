"""Search functionality for finding videos on FetLife."""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from bs4 import BeautifulSoup
import click

from .client import FetLifeClient
from .config import config
from .utils import parse_duration


@dataclass
class VideoInfo:
    """Information about a video."""
    video_id: str
    title: str
    url: str
    uploader: str
    uploader_id: str
    duration: int  # in seconds
    thumbnail_url: Optional[str] = None
    upload_date: Optional[str] = None
    download_url: Optional[str] = None  # Direct download URL (HLS or MP4)


class SearchError(Exception):
    """Raised when search fails."""
    pass


def fetch_video_duration(client: FetLifeClient, video_url: str) -> int:
    """
    Fetch video duration from video page.

    Args:
        client: Authenticated FetLife client
        video_url: URL of the video page

    Returns:
        Duration in seconds, or 0 if not found
    """
    try:
        response = client.get(video_url)
        soup = BeautifulSoup(response.text, "lxml")

        # Look for duration in meta tags or video element
        # Try to find duration in the page
        duration_patterns = [
            r'"duration["\s:]+(\d+)',  # JSON format
            r'duration["\s:]+["\']*(\d+:\d+)',  # HH:MM:SS or MM:SS
            r'<meta\s+property="video:duration"\s+content="(\d+)"',  # Meta tag
        ]

        for pattern in duration_patterns:
            match = re.search(pattern, response.text, re.IGNORECASE)
            if match:
                duration_str = match.group(1)
                try:
                    return parse_duration(duration_str)
                except ValueError:
                    continue

        return 0
    except Exception:
        return 0


def parse_video_element(element, base_url: str) -> Optional[VideoInfo]:
    """
    Parse a video element from search results.

    Args:
        element: BeautifulSoup element containing video information
        base_url: Base URL for constructing full URLs

    Returns:
        VideoInfo object if parsing successful, None otherwise
    """
    try:
        # Extract video URL and ID
        video_link = element.find("a", href=re.compile(r"/videos/\d+"))
        if not video_link:
            return None

        video_url = video_link.get("href", "")
        if not video_url.startswith("http"):
            video_url = base_url + video_url

        video_id_match = re.search(r"/videos/(\d+)", video_url)
        if not video_id_match:
            return None
        video_id = video_id_match.group(1)

        # Extract title
        title_elem = element.find("h3") or element.find("h2") or video_link
        title = title_elem.get_text(strip=True) if title_elem else f"Video {video_id}"

        # Extract uploader information
        uploader_link = element.find("a", href=re.compile(r"/users/\d+"))
        uploader = "Unknown"
        uploader_id = "0"
        if uploader_link:
            uploader = uploader_link.get_text(strip=True)
            uploader_id_match = re.search(r"/users/(\d+)", uploader_link.get("href", ""))
            if uploader_id_match:
                uploader_id = uploader_id_match.group(1)

        # Extract duration
        duration = 0
        duration_elem = element.find(class_=re.compile(r"duration", re.IGNORECASE))
        if not duration_elem:
            # Try to find duration in text
            duration_text = element.find(string=re.compile(r"\d+:\d+"))
            if duration_text:
                duration_elem = duration_text

        if duration_elem:
            duration_str = duration_elem.get_text(strip=True) if hasattr(duration_elem, 'get_text') else str(duration_elem)
            try:
                duration = parse_duration(duration_str)
            except ValueError:
                pass

        # Extract thumbnail
        thumbnail_url = None
        img_elem = element.find("img")
        if img_elem:
            thumbnail_url = img_elem.get("src") or img_elem.get("data-src")

        # Extract upload date
        upload_date = None
        date_elem = element.find("time") or element.find(class_=re.compile(r"date", re.IGNORECASE))
        if date_elem:
            upload_date = date_elem.get("datetime") or date_elem.get_text(strip=True)

        return VideoInfo(
            video_id=video_id,
            title=title,
            url=video_url,
            uploader=uploader,
            uploader_id=uploader_id,
            duration=duration,
            thumbnail_url=thumbnail_url,
            upload_date=upload_date,
        )
    except Exception as e:
        click.echo(f"Warning: Failed to parse video element: {e}", err=True)
        return None


def search_videos(
    client: FetLifeClient,
    query: str,
    min_duration: int = 0,
    limit: Optional[int] = None,
    page: int = 1,
) -> List[VideoInfo]:
    """
    Search for videos on FetLife.

    Args:
        client: Authenticated FetLife client
        query: Search query string
        min_duration: Minimum video duration in seconds (0 for no filter)
        limit: Maximum number of videos to return (None for all)
        page: Page number to start from

    Returns:
        List of VideoInfo objects

    Raises:
        SearchError: If search fails
    """
    if not client.authenticated:
        raise SearchError("Client must be authenticated to search")

    click.echo(f"Searching for: '{query}'")
    if min_duration > 0:
        from .utils import format_duration
        click.echo(f"Filtering for videos >= {format_duration(min_duration)}")

    videos = []
    current_page = page

    try:
        while True:
            # Construct search URL - FetLife uses /search/videos?q=query format
            search_url = f"{config.base_url}/search/videos?q={query}"
            if current_page > 1:
                search_url += f"&page={current_page}"

            click.echo(f"Fetching page {current_page}...")
            response = client.get(search_url)
            soup = BeautifulSoup(response.text, "lxml")

            # Extract video data from Vue component JSON
            import json
            import html as html_module

            # Find the VideoSearchStories component
            video_component = soup.find(attrs={"data-component": "VideoSearchStories"})
            if not video_component:
                click.echo("No VideoSearchStories component found.")
                break

            # Extract and parse the JSON data
            props_data = video_component.get("data-props", "")
            if not props_data:
                click.echo("No data-props found in component.")
                break

            try:
                # Decode HTML entities and parse JSON
                props_json = json.loads(html_module.unescape(props_data))
                stories = props_json.get("stories", [])

                if not stories:
                    click.echo("No videos found in search results.")
                    break

                click.echo(f"Found {len(stories)} video stories")

                page_videos = []
                for story in stories:
                    story_videos = story.get("attributes", {}).get("videos", [])
                    for video_data in story_videos:
                        # Extract video information
                        video_id = str(video_data.get("id", ""))
                        video_path = video_data.get("path", "")
                        title = video_data.get("formattedTitle", f"Video {video_id}")
                        video_url = config.base_url + video_path if video_path else ""

                        # Extract uploader from path (format: /username/videos/id)
                        uploader = "Unknown"
                        if video_path:
                            parts = video_path.split("/")
                            if len(parts) >= 2:
                                uploader = parts[1]

                        # Parse duration from search results
                        duration = 0
                        duration_str = video_data.get("durationString", "")
                        if duration_str:
                            try:
                                duration = parse_duration(duration_str)
                            except ValueError:
                                pass

                        # Extract download URL from sources
                        download_url = None
                        sources = video_data.get("sources", [])
                        if sources and len(sources) > 0:
                            download_url = sources[0].get("src")

                        video_info = VideoInfo(
                            video_id=video_id,
                            title=title,
                            url=video_url,
                            uploader=uploader,
                            uploader_id="0",  # Not available in search results
                            duration=duration,
                            thumbnail_url=video_data.get("screencapSrc"),
                            upload_date=video_data.get("createdAt"),
                            download_url=download_url,
                        )

                        # Apply duration filter
                        if min_duration > 0 and video_info.duration < min_duration:
                            continue

                        page_videos.append(video_info)

                        # Check if we've reached the limit
                        if limit and len(videos) + len(page_videos) >= limit:
                            videos.extend(page_videos[:limit - len(videos)])
                            click.echo(f"Reached limit of {limit} videos")
                            return videos

            except json.JSONDecodeError as e:
                click.echo(f"Failed to parse video data: {e}")
                break

            # Add videos that passed the filter
            videos.extend(page_videos)

            if page_videos:
                click.echo(f"Found {len(page_videos)} videos on page {current_page} (total: {len(videos)})")
            else:
                click.echo(f"No videos matching criteria on page {current_page} (continuing...)")

            # Continue to next page if we haven't reached limit and there are more results
            # Check if there were any stories (even if filtered out)
            if not stories:
                click.echo("No more search results available.")
                break

            current_page += 1

        click.echo(click.style(f"✓ Search complete: {len(videos)} videos found", fg="green"))
        return videos

    except Exception as e:
        raise SearchError(f"Search failed: {e}")
