"""Utility functions for FetLife scraper."""

import re
from pathlib import Path
from typing import Union


def parse_duration(duration_str: str) -> int:
    """
    Parse duration string to seconds.

    Supports multiple formats:
    - Seconds: "90" -> 90
    - MM:SS: "5:30" -> 330
    - HH:MM:SS: "1:23:45" -> 5025
    - Shorthand: "5m30s" -> 330, "1h30m" -> 5400

    Args:
        duration_str: Duration string in various formats

    Returns:
        Duration in seconds

    Raises:
        ValueError: If duration format is invalid
    """
    if not duration_str:
        return 0

    duration_str = str(duration_str).strip()

    # Try pure seconds first
    if duration_str.isdigit():
        return int(duration_str)

    # Try shorthand format (5m30s, 1h30m, etc.)
    shorthand_pattern = r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?"
    match = re.fullmatch(shorthand_pattern, duration_str)
    if match and any(match.groups()):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    # Try HH:MM:SS or MM:SS format
    time_parts = duration_str.split(":")
    if len(time_parts) == 2:  # MM:SS
        try:
            minutes, seconds = map(int, time_parts)
            return minutes * 60 + seconds
        except ValueError:
            pass
    elif len(time_parts) == 3:  # HH:MM:SS
        try:
            hours, minutes, seconds = map(int, time_parts)
            return hours * 3600 + minutes * 60 + seconds
        except ValueError:
            pass

    raise ValueError(f"Invalid duration format: {duration_str}")


def format_duration(seconds: int) -> str:
    """
    Format seconds into human-readable duration.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string (e.g., "5:30", "1:23:45")
    """
    if seconds < 60:
        return f"{seconds}s"

    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}:{secs:02d}"

    hours, mins = divmod(minutes, 60)
    return f"{hours}:{mins:02d}:{secs:02d}"


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitize filename by removing/replacing invalid characters.

    Args:
        filename: Original filename
        max_length: Maximum filename length

    Returns:
        Sanitized filename safe for filesystem
    """
    # Replace invalid characters with underscore
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, "_", filename)

    # Remove control characters
    sanitized = "".join(char for char in sanitized if ord(char) >= 32)

    # Replace multiple spaces/underscores with single
    sanitized = re.sub(r"[\s_]+", "_", sanitized)

    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(". ")

    # Truncate to max length while preserving extension
    if len(sanitized) > max_length:
        name_part = sanitized[:max_length]
        sanitized = name_part.rstrip(". ")

    return sanitized or "unnamed"


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    Ensure directory exists, creating it if necessary.

    Args:
        path: Directory path

    Returns:
        Path object of the directory
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def format_file_size(size_bytes: int) -> str:
    """
    Format bytes into human-readable file size.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string (e.g., "1.5 MB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
