"""Command-line interface for FetLife video scraper."""

import sys
from pathlib import Path
from typing import Optional
import click
from colorama import init as colorama_init

from .client import FetLifeClient
from .config import config
from .auth import authenticate, verify_authentication, prompt_credentials, AuthenticationError
from .search import search_videos, SearchError
from .profile import get_profile_videos, ProfileError
from .downloader import VideoDownloader
from .utils import parse_duration, format_duration


# Initialize colorama for cross-platform colored output
colorama_init()


def parse_duration_arg(ctx, param, value):
    """Parse duration argument from CLI."""
    if value is None:
        return 0
    try:
        return parse_duration(value)
    except ValueError as e:
        raise click.BadParameter(f"Invalid duration format: {e}")


@click.group(invoke_without_command=True)
@click.option("--test-auth", is_flag=True, help="Test authentication and exit")
@click.pass_context
def cli(ctx, test_auth):
    """FetLife Video Scraper - Download videos with search and filtering."""
    if ctx.invoked_subcommand is None and not test_auth:
        # Interactive mode
        click.echo(click.style("=== FetLife Video Scraper ===", fg="cyan", bold=True))
        click.echo("\nAvailable commands:")
        click.echo("  search   - Search for videos by keyword")
        click.echo("  profile  - Download videos from a user profile")
        click.echo("\nUse --help for more information")
        return

    if test_auth:
        # Test authentication
        click.echo("Testing authentication...")
        try:
            with FetLifeClient() as client:
                authenticate(client)
                click.echo(click.style("✓ Authentication successful!", fg="green"))
        except AuthenticationError as e:
            click.echo(click.style(f"✗ Authentication failed: {e}", fg="red"))
            sys.exit(1)


@cli.command()
@click.argument("query")
@click.option("--min-duration", "-d", callback=parse_duration_arg, help="Minimum video duration (e.g., 60, 5:30, 5m30s)")
@click.option("--limit", "-l", type=int, help="Maximum number of videos to download")
@click.option("--output", "-o", type=click.Path(), help="Output directory (default: ./downloads)")
@click.option("--username", "-u", help="FetLife username (overrides .env)")
@click.option("--password", "-p", help="FetLife password (overrides .env)")
@click.option("--no-download", is_flag=True, help="List videos without downloading")
@click.option("--force", "-f", is_flag=True, help="Re-download existing videos")
def search(query, min_duration, limit, output, username, password, no_download, force):
    """Search for videos by keyword and download them."""
    try:
        # Setup output directory
        output_dir = Path(output) if output else config.download_path
        config.ensure_download_path()

        # Get credentials if needed
        if not username or not password:
            if not config.validate_credentials():
                click.echo("Credentials not found in .env file.")
                username, password = prompt_credentials()

        # Create client and authenticate
        with FetLifeClient() as client:
            click.echo("\n" + "=" * 60)
            authenticate(client, username, password)
            click.echo("=" * 60 + "\n")

            # Search for videos
            if min_duration > 0:
                click.echo(f"Minimum duration filter: {format_duration(min_duration)}\n")

            videos = search_videos(client, query, min_duration=min_duration, limit=limit)

            if not videos:
                click.echo(click.style("No videos found matching criteria.", fg="yellow"))
                return

            # List videos
            click.echo(f"\nFound {len(videos)} videos:\n")
            for idx, video in enumerate(videos, 1):
                duration_str = format_duration(video.duration) if video.duration else "Unknown"
                click.echo(f"{idx}. {video.title}")
                click.echo(f"   Uploader: {video.uploader} | Duration: {duration_str}")
                click.echo(f"   URL: {video.url}")

            if no_download:
                click.echo("\n(Download skipped - list only mode)")
                return

            # Download videos
            click.echo("\n")
            downloader = VideoDownloader(client, output_dir)
            downloader.download_videos(videos, skip_existing=not force)

    except (AuthenticationError, SearchError) as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\nDownload cancelled by user.")
        sys.exit(0)
    except Exception as e:
        click.echo(click.style(f"✗ Unexpected error: {e}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.argument("profile_identifier")
@click.option("--min-duration", "-d", callback=parse_duration_arg, help="Minimum video duration (e.g., 60, 5:30, 5m30s)")
@click.option("--limit", "-l", type=int, help="Maximum number of videos to download")
@click.option("--output", "-o", type=click.Path(), help="Output directory (default: ./downloads)")
@click.option("--username", "-u", help="FetLife username (overrides .env)")
@click.option("--password", "-p", help="FetLife password (overrides .env)")
@click.option("--no-download", is_flag=True, help="List videos without downloading")
@click.option("--force", "-f", is_flag=True, help="Re-download existing videos")
def profile(profile_identifier, min_duration, limit, output, username, password, no_download, force):
    """Download videos from a user profile."""
    try:
        # Setup output directory
        output_dir = Path(output) if output else config.download_path
        config.ensure_download_path()

        # Get credentials if needed
        if not username or not password:
            if not config.validate_credentials():
                click.echo("Credentials not found in .env file.")
                username, password = prompt_credentials()

        # Create client and authenticate
        with FetLifeClient() as client:
            click.echo("\n" + "=" * 60)
            authenticate(client, username, password)
            click.echo("=" * 60 + "\n")

            # Get profile videos
            if min_duration > 0:
                click.echo(f"Minimum duration filter: {format_duration(min_duration)}\n")

            videos = get_profile_videos(client, profile_identifier, min_duration=min_duration, limit=limit)

            if not videos:
                click.echo(click.style("No videos found matching criteria.", fg="yellow"))
                return

            # List videos
            click.echo(f"\nFound {len(videos)} videos:\n")
            for idx, video in enumerate(videos, 1):
                duration_str = format_duration(video.duration) if video.duration else "Unknown"
                click.echo(f"{idx}. {video.title}")
                click.echo(f"   Uploader: {video.uploader} | Duration: {duration_str}")
                click.echo(f"   URL: {video.url}")

            if no_download:
                click.echo("\n(Download skipped - list only mode)")
                return

            # Download videos
            click.echo("\n")
            downloader = VideoDownloader(client, output_dir)
            downloader.download_videos(videos, skip_existing=not force)

    except (AuthenticationError, ProfileError) as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\nDownload cancelled by user.")
        sys.exit(0)
    except Exception as e:
        click.echo(click.style(f"✗ Unexpected error: {e}", fg="red"), err=True)
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
