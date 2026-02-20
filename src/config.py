"""Configuration management for FetLife scraper."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self):
        """Initialize configuration from environment variables."""
        # Authentication
        self.username: Optional[str] = os.getenv("FETLIFE_USERNAME")
        self.password: Optional[str] = os.getenv("FETLIFE_PASSWORD")

        # Download settings
        self.download_path: Path = Path(os.getenv("DOWNLOAD_PATH", "./downloads"))
        self.max_workers: int = int(os.getenv("MAX_WORKERS", "3"))
        self.rate_limit_delay: float = float(os.getenv("RATE_LIMIT_DELAY", "2.5"))

        # Video filters
        self.default_min_duration: int = int(os.getenv("DEFAULT_MIN_DURATION", "0"))

        # HTTP settings
        self.user_agent: str = "FetScraper/0.1.0 (Educational/Personal Use)"
        self.timeout: int = 30

        # FetLife URLs
        self.base_url: str = "https://fetlife.com"
        self.login_url: str = f"{self.base_url}/login"
        self.search_url: str = f"{self.base_url}/search"

    def validate_credentials(self) -> bool:
        """Check if credentials are configured."""
        return bool(self.username and self.password)

    def ensure_download_path(self) -> None:
        """Create download directory if it doesn't exist."""
        self.download_path.mkdir(parents=True, exist_ok=True)


# Global configuration instance
config = Config()
