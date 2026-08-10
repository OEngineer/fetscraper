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
        # Extract video URL and ID (skip "#comment" jump links to the same video)
        video_links = [
            a for a in element.find_all("a", href=re.compile(r"/videos/\d+"))
            if "#comment" not in a.get("href", "")
        ]
        if not video_links:
            return None
        video_link = video_links[0]

        video_url = video_link.get("href", "")
        if not video_url.startswith("http"):
            video_url = base_url + video_url

        video_id_match = re.search(r"/videos/(\d+)", video_url)
        if not video_id_match:
            return None
        video_id = video_id_match.group(1)

        # Extract uploader information (falls back to the username in the video path)
        uploader = "Unknown"
        uploader_id = "0"
        path_match = re.match(r"/([^/]+)/videos/\d+", video_url[len(base_url):] if video_url.startswith(base_url) else video_url)
        if path_match:
            uploader = path_match.group(1)
        uploader_link = element.find("a", href=re.compile(r"/users/\d+"))
        if uploader_link:
            uploader = uploader_link.get_text(strip=True) or uploader
            uploader_id_match = re.search(r"/users/(\d+)", uploader_link.get("href", ""))
            if uploader_id_match:
                uploader_id = uploader_id_match.group(1)

        # Extract title: dedicated heading, else the "story__copy" caption link,
        # else the "Video by <user> - <title>" title attribute on the thumbnail link
        title = None
        title_elem = element.find("h3") or element.find("h2")
        if title_elem:
            title = title_elem.get_text(strip=True)
        if not title:
            copy_link = element.find("a", class_="story__copy")
            if copy_link:
                title = copy_link.get_text(strip=True)
        if not title:
            attr_title = video_link.get("title", "")
            title_match = re.match(r"Video by .*? - (.+)", attr_title)
            if title_match:
                title = title_match.group(1).strip()
        if not title:
            title = f"Video {video_id}"

        # Extract duration
        duration = 0
        duration_elem = element.find(class_=re.compile(r"duration", re.IGNORECASE))
        if not duration_elem:
            # Try to find a standalone MM:SS / HH:MM:SS text node (e.g. the duration badge)
            duration_text = element.find(string=re.compile(r"^\s*\d+:\d+(:\d+)?\s*$"))
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


def iter_search_videos(
    client: FetLifeClient,
    query: str,
    min_duration: int = 0,
    limit: Optional[int] = None,
    page: int = 1,
):
    """
    Search for videos on FetLife, yielding each matching video as soon as it's found.

    This lets a caller start acting on early results (e.g. downloading) while later
    result pages are still being fetched.

    Args:
        client: Authenticated FetLife client
        query: Search query string
        min_duration: Minimum video duration in seconds (0 for no filter)
        limit: Maximum number of videos to yield (None for all)
        page: Page number to start from

    Yields:
        VideoInfo objects as they are found, in page order

    Raises:
        SearchError: If search fails
    """
    if not client.authenticated:
        raise SearchError("Client must be authenticated to search")

    click.echo(f"Searching for: '{query}'")
    if min_duration > 0:
        from .utils import format_duration
        click.echo(f"Filtering for videos >= {format_duration(min_duration)}")

    yielded = 0
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

            # Search results are rendered as <article id="story_..."> story cards
            stories = soup.find_all("article", id=re.compile(r"^story_"))

            if not stories:
                click.echo("No more search results available.")
                break

            click.echo(f"Found {len(stories)} video stories")

            page_matches = 0
            for story in stories:
                video_info = parse_video_element(story, config.base_url)
                if not video_info:
                    continue

                # Apply duration filter
                if min_duration > 0 and video_info.duration < min_duration:
                    continue

                page_matches += 1
                yielded += 1
                yield video_info

                # Check if we've reached the limit
                if limit and yielded >= limit:
                    click.echo(f"Reached limit of {limit} videos")
                    return

            if page_matches:
                click.echo(f"Found {page_matches} videos on page {current_page} (total: {yielded})")
            else:
                click.echo(f"No videos matching criteria on page {current_page} (continuing...)")

            current_page += 1

        click.echo(click.style(f"✓ Search complete: {yielded} videos found", fg="green"))

    except SearchError:
        raise
    except Exception as e:
        raise SearchError(f"Search failed: {e}")


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
    return list(iter_search_videos(client, query, min_duration=min_duration, limit=limit, page=page))
