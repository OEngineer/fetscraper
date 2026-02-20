"""HTTP client for FetLife with session management and rate limiting."""

import time
from typing import Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import config


class FetLifeClient:
    """HTTP client for interacting with FetLife."""

    def __init__(self):
        """Initialize the FetLife client with session management."""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            # Don't set Accept-Encoding - let requests handle it automatically
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

        # Setup retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.last_request_time: float = 0
        self.csrf_token: Optional[str] = None
        self.authenticated: bool = False

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < config.rate_limit_delay:
            time.sleep(config.rate_limit_delay - time_since_last)

        self.last_request_time = time.time()

    def get(self, url: str, **kwargs) -> requests.Response:
        """
        Send GET request with rate limiting.

        Args:
            url: URL to request
            **kwargs: Additional arguments for requests.get()

        Returns:
            Response object

        Raises:
            requests.RequestException: If request fails
        """
        self._rate_limit()

        if "timeout" not in kwargs:
            kwargs["timeout"] = config.timeout

        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            raise requests.RequestException(f"GET request failed for {url}: {e}")

    def post(self, url: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        """
        Send POST request with rate limiting.

        Args:
            url: URL to request
            data: POST data
            **kwargs: Additional arguments for requests.post()

        Returns:
            Response object

        Raises:
            requests.RequestException: If request fails
        """
        self._rate_limit()

        if "timeout" not in kwargs:
            kwargs["timeout"] = config.timeout

        try:
            response = self.session.post(url, data=data, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            raise requests.RequestException(f"POST request failed for {url}: {e}")

    def download_file(self, url: str, filepath: str, chunk_size: int = 8192) -> int:
        """
        Download file with progress tracking.

        Args:
            url: URL of file to download
            filepath: Local path to save file
            chunk_size: Size of chunks to download

        Returns:
            Total bytes downloaded

        Raises:
            requests.RequestException: If download fails
        """
        self._rate_limit()

        try:
            response = self.session.get(url, stream=True, timeout=config.timeout)
            response.raise_for_status()

            total_size = 0
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            return total_size
        except requests.RequestException as e:
            raise requests.RequestException(f"File download failed for {url}: {e}")

    def close(self) -> None:
        """Close the session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
