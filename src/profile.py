"""Profile video extraction for FetLife users."""

import re
from typing import List, Optional
from bs4 import BeautifulSoup
import click

from .client import FetLifeClient
from .config import config
from .search import VideoInfo, parse_video_element


class ProfileError(Exception):
    """Raised when profile operations fail."""
    pass


def extract_user_id(profile_identifier: str) -> Optional[str]:
    """
    Extract user ID from username or profile URL.

    Args:
        profile_identifier: Username, user ID, or profile URL

    Returns:
        User ID if found, None otherwise
    """
    # If it's already a number, return it
    if profile_identifier.isdigit():
        return profile_identifier

    # Try to extract from URL
    url_match = re.search(r"/users/(\d+)", profile_identifier)
    if url_match:
        return url_match.group(1)

    # If it's a username, we'll need to search for it
    return None


def get_user_id_from_nickname(client: FetLifeClient, nickname: str) -> Optional[str]:
    """
    Get user ID from nickname by searching.

    Args:
        client: Authenticated FetLife client
        nickname: User's nickname

    Returns:
        User ID if found, None otherwise
    """
    try:
        # Search for the user
        search_url = f"{config.search_url}?q={nickname}&type=users"
        response = client.get(search_url)
        soup = BeautifulSoup(response.text, "lxml")

        # Find user links
        user_link = soup.find("a", href=re.compile(r"/users/\d+"), string=re.compile(f"^{re.escape(nickname)}$", re.IGNORECASE))
        if user_link:
            user_id_match = re.search(r"/users/(\d+)", user_link.get("href", ""))
            if user_id_match:
                return user_id_match.group(1)

        return None
    except Exception:
        return None


def get_profile_videos(
    client: FetLifeClient,
    profile_identifier: str,
    min_duration: int = 0,
    limit: Optional[int] = None,
) -> List[VideoInfo]:
    """
    Get videos from a user's profile.

    Args:
        client: Authenticated FetLife client
        profile_identifier: Username, user ID, or profile URL
        min_duration: Minimum video duration in seconds (0 for no filter)
        limit: Maximum number of videos to return (None for all)

    Returns:
        List of VideoInfo objects

    Raises:
        ProfileError: If profile operations fail
    """
    if not client.authenticated:
        raise ProfileError("Client must be authenticated to access profiles")

    click.echo(f"Fetching videos from profile: {profile_identifier}")

    try:
        # Extract or find user ID
        user_id = extract_user_id(profile_identifier)

        if not user_id:
            click.echo(f"Looking up user ID for nickname: {profile_identifier}")
            user_id = get_user_id_from_nickname(client, profile_identifier)

        if not user_id:
            raise ProfileError(f"Could not find user: {profile_identifier}")

        click.echo(f"User ID: {user_id}")

        videos = []
        page = 1

        while True:
            # Construct videos URL for this user
            videos_url = f"{config.base_url}/users/{user_id}/videos?page={page}"

            click.echo(f"Fetching page {page}...")
            response = client.get(videos_url)
            soup = BeautifulSoup(response.text, "lxml")

            # Find video elements
            video_elements = soup.find_all(class_=re.compile(r"video[-_]?(item|card)", re.IGNORECASE))

            if not video_elements:
                # Try alternative selectors
                video_elements = soup.find_all("article") or soup.find_all(class_="media")

            if not video_elements:
                click.echo("No more videos found.")
                break

            page_videos = []
            for element in video_elements:
                video_info = parse_video_element(element, config.base_url)
                if video_info:
                    # Apply duration filter
                    if min_duration > 0 and video_info.duration < min_duration:
                        continue

                    page_videos.append(video_info)

                    # Check if we've reached the limit
                    if limit and len(videos) + len(page_videos) >= limit:
                        videos.extend(page_videos[:limit - len(videos)])
                        click.echo(f"Reached limit of {limit} videos")
                        return videos

            if not page_videos:
                click.echo("No more videos matching criteria.")
                break

            videos.extend(page_videos)
            click.echo(f"Found {len(page_videos)} videos on page {page} (total: {len(videos)})")

            # Check for next page
            next_page = soup.find("a", rel="next")
            if not next_page:
                break

            page += 1

        click.echo(click.style(f"✓ Found {len(videos)} videos from profile", fg="green"))
        return videos

    except Exception as e:
        if isinstance(e, ProfileError):
            raise
        raise ProfileError(f"Failed to get profile videos: {e}")
