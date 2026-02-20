"""Authentication module for FetLife."""

import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import click

from .client import FetLifeClient
from .config import config


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


def extract_csrf_token(html: str) -> Optional[str]:
    """
    Extract CSRF token from HTML page.

    Args:
        html: HTML content

    Returns:
        CSRF token if found, None otherwise
    """
    soup = BeautifulSoup(html, "lxml")

    # Try meta tag first
    meta_token = soup.find("meta", {"name": "csrf-token"})
    if meta_token and meta_token.get("content"):
        return meta_token["content"]

    # Try hidden input field
    token_input = soup.find("input", {"name": "authenticity_token"})
    if token_input and token_input.get("value"):
        return token_input["value"]

    # Try to find in JavaScript
    token_match = re.search(r'csrf[_-]?token["\s:]+["\']([\w-]+)["\']', html, re.IGNORECASE)
    if token_match:
        return token_match.group(1)

    return None


def authenticate(client: FetLifeClient, username: Optional[str] = None, password: Optional[str] = None) -> bool:
    """
    Authenticate with FetLife.

    Args:
        client: FetLife client instance
        username: FetLife username (optional, uses config if not provided)
        password: FetLife password (optional, uses config if not provided)

    Returns:
        True if authentication successful

    Raises:
        AuthenticationError: If authentication fails
    """
    # Use provided credentials or fall back to config
    username = username or config.username
    password = password or config.password

    if not username or not password:
        raise AuthenticationError(
            "Username and password required. "
            "Set FETLIFE_USERNAME and FETLIFE_PASSWORD in .env file or provide as arguments."
        )

    try:
        # Get login page to obtain CSRF token
        click.echo("Fetching login page...")
        response = client.get(config.login_url)

        # Debug: check if response is properly decoded
        content_encoding = response.headers.get('Content-Encoding', 'none')
        click.echo(f"Response: {response.status_code}, encoding: {content_encoding}")
        click.echo(f"Raw size: {len(response.content)} bytes, decoded size: {len(response.text)} chars")

        # Check if we got binary data instead of text
        if response.text.startswith('\x1f\x8b') or '�' in response.text[:100]:
            click.echo("Warning: Response appears to be compressed/binary data")

        csrf_token = extract_csrf_token(response.text)

        if not csrf_token:
            # Save the response for debugging
            with open("debug_login_page.html", "w", encoding='utf-8', errors='replace') as f:
                f.write(response.text)
            click.echo("Saved login page to debug_login_page.html")
            raise AuthenticationError("Could not extract CSRF token from login page")

        client.csrf_token = csrf_token
        click.echo(f"CSRF token obtained: {csrf_token[:20]}...")

        # Prepare login data (matching FetLife's actual form fields)
        login_data = {
            "authenticity_token": csrf_token,
            "user[otp_attempt]": "step_1",
            "user[locale]": "en",
            "user[login]": username,
            "user[password]": password,
            "user[remember_me]": "1",
        }

        # Submit login form
        click.echo("Submitting login credentials...")
        response = client.post(config.login_url, data=login_data, allow_redirects=True)

        # Check if login was successful
        # FetLife redirects to /home on successful login
        if response.status_code == 200 and "/home" in response.url:
            client.authenticated = True
            click.echo(click.style("✓ Authentication successful!", fg="green"))
            return True

        # If we didn't get redirected to home, check for error messages
        soup = BeautifulSoup(response.text, "lxml")
        error_elem = soup.find(class_=re.compile(r"error|alert", re.IGNORECASE))
        if error_elem:
            error_text = error_elem.get_text(strip=True)
            raise AuthenticationError(f"Login failed: {error_text}")

        # Generic failure
        raise AuthenticationError(
            "Authentication failed. Please check your username and password."
        )

    except Exception as e:
        if isinstance(e, AuthenticationError):
            raise
        raise AuthenticationError(f"Authentication error: {e}")


def verify_authentication(client: FetLifeClient) -> bool:
    """
    Verify if the current session is authenticated.

    Args:
        client: FetLife client instance

    Returns:
        True if authenticated, False otherwise
    """
    if not client.authenticated:
        return False

    try:
        # Try to access a page that requires authentication
        response = client.get(f"{config.base_url}/home")
        soup = BeautifulSoup(response.text, "lxml")

        # Check for logout link
        logout_link = soup.find("a", href=re.compile(r"/session.*method=delete"))
        return bool(logout_link)
    except Exception:
        return False


def prompt_credentials() -> Tuple[str, str]:
    """
    Prompt user for credentials interactively.

    Returns:
        Tuple of (username, password)
    """
    username = click.prompt("FetLife username", type=str)
    password = click.prompt("FetLife password", type=str, hide_input=True)
    return username, password
