"""OAuth 2.0 authentication manager for Google Health API."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Callable, Optional
import urllib.parse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from nutrilog.storage import (
    delete_tokens,
    get_credentials_path,
    load_credentials,
    load_tokens,
    save_tokens,
)

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.nutrition.writeonly",
    "https://www.googleapis.com/auth/googlehealth.nutrition.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

import base64

TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"

# Default bundled desktop client credentials for zero-friction user OAuth
_DEFAULT_CLIENT_ID_B64 = "MjgxODQyMDk3MjUxLXBucGNpczlhOTN0cGVjNjQyMjFiY2o2MjNrdXZpYjNjLmFwcHMuZ29vZ2xldXNlcmNvbnRlbnQuY29t"
_DEFAULT_CLIENT_SECRET_B64 = "R09DU1BYLWNyZ0RDbHBoQWEwdWxKOUEyOTBwOTRxSEphNHk="

DEFAULT_CLIENT_ID = base64.b64decode(_DEFAULT_CLIENT_ID_B64).decode("utf-8")
DEFAULT_CLIENT_SECRET = base64.b64decode(_DEFAULT_CLIENT_SECRET_B64).decode("utf-8")


def is_headless_or_ssh() -> bool:
    """Detect if running in an SSH session, headless environment, or without GUI display."""
    if os.getenv("SSH_CLIENT") or os.getenv("SSH_TTY") or os.getenv("SSH_CONNECTION"):
        return True
    if os.name == "posix" and not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        return True
    return False


def extract_auth_code(input_str: str) -> str:
    """Extract the authorization code from a raw code or full redirect URL."""
    cleaned = input_str.strip()
    if "code=" in cleaned:
        if cleaned.startswith("code="):
            code_part = cleaned.split("code=", 1)[1]
            return urllib.parse.unquote(code_part.split("&", 1)[0])
        if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
            cleaned = "http://" + cleaned
        parsed = urllib.parse.urlparse(cleaned)
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            return qs["code"][0]
        for part in cleaned.split("&"):
            if part.startswith("code="):
                return urllib.parse.unquote(part.split("=", 1)[1])
    return cleaned


def get_client_config() -> Optional[dict[str, Any]]:
    """Retrieve client credentials from env vars, stored config, or packaged defaults."""
    env_id = os.getenv("NUTRILOG_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID")
    env_secret = os.getenv("NUTRILOG_CLIENT_SECRET") or os.getenv("GOOGLE_CLIENT_SECRET")
    if env_id and env_secret:
        return {
            "installed": {
                "client_id": env_id,
                "client_secret": env_secret,
                "auth_uri": AUTH_URI,
                "token_uri": TOKEN_URI,
                "redirect_uris": ["http://localhost"],
            }
        }

    saved = load_credentials()
    if saved:
        return saved

    creds_path = get_credentials_path()
    if creds_path.exists():
        import json

        try:
            return json.loads(creds_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if DEFAULT_CLIENT_ID and DEFAULT_CLIENT_SECRET:
        return {
            "installed": {
                "client_id": DEFAULT_CLIENT_ID,
                "client_secret": DEFAULT_CLIENT_SECRET,
                "auth_uri": AUTH_URI,
                "token_uri": TOKEN_URI,
                "redirect_uris": ["http://localhost"],
            }
        }

    return None


def _token_dict_from_creds(creds: Credentials) -> dict[str, Any]:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def get_credentials() -> Optional[Credentials]:
    """Load valid credentials from storage, refreshing them if expired."""
    token_data = load_tokens()
    if not token_data:
        return None

    try:
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    except Exception:
        return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_tokens(_token_dict_from_creds(creds))
        except Exception:
            # If refresh fails, creds might be invalid
            return None

    return creds if (creds and (creds.valid or creds.token)) else None


def _create_flow(client_config_path: Optional[Path] = None) -> InstalledAppFlow:
    if client_config_path and client_config_path.exists():
        return InstalledAppFlow.from_client_secrets_file(
            str(client_config_path),
            scopes=SCOPES,
        )
    client_config = get_client_config()
    if not client_config:
        raise ValueError(
            "No OAuth client credentials found. Please provide a client_secrets.json file, "
            "set NUTRILOG_CLIENT_ID and NUTRILOG_CLIENT_SECRET, or run 'nutrilog auth setup'."
        )
    return InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)


def login(
    client_config_path: Optional[Path] = None,
    port: int = 0,
    open_browser: Optional[bool] = None,
) -> Credentials:
    """Run local server OAuth 2.0 flow to obtain user credentials."""
    flow = _create_flow(client_config_path)

    should_open = open_browser if open_browser is not None else (not is_headless_or_ssh())

    creds = flow.run_local_server(
        port=port,
        open_browser=should_open,
        prompt="consent",
        access_type="offline",
    )

    save_tokens(_token_dict_from_creds(creds))
    return creds


def login_remote(
    client_config_path: Optional[Path] = None,
    input_callback: Optional[Callable[[str], str]] = None,
) -> Credentials:
    """Run console/remote copy-paste OAuth 2.0 flow for remote SSH or browserless environments."""
    flow = _create_flow(client_config_path)
    flow.redirect_uri = "http://localhost"

    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    if input_callback:
        raw_input = input_callback(auth_url)
    else:
        from rich.console import Console
        from rich.panel import Panel

        c = Console()
        c.print()
        c.print(
            Panel.fit(
                f"[bold cyan]1. Open this URL in your local browser:[/bold cyan]\n\n"
                f"[bold underline link={auth_url}]{auth_url}[/bold underline link]\n\n"
                f"[bold cyan]2. Grant consent:[/bold cyan]\n"
                f"   Your browser will redirect to a URL starting with [green]http://localhost/?code=...[/green]\n"
                f"   (The browser page will display [italic]\"This site can't be reached\"[/italic]—this is expected!)\n\n"
                f"[bold cyan]3. Copy the URL:[/bold cyan]\n"
                f"   Copy the [bold yellow]ENTIRE URL[/bold yellow] from your browser's address bar and paste it below.",
                title="[bold blue]Google OAuth Remote Authorization[/bold blue]",
                border_style="blue",
            )
        )
        c.print()
        raw_input = input("Paste the redirected URL (or code) from address bar: ")

    code = extract_auth_code(raw_input)
    flow.fetch_token(code=code)
    creds = flow.credentials
    save_tokens(_token_dict_from_creds(creds))
    return creds


# Backward-compatibility alias
login_manual = login_remote


def get_auth_status() -> dict[str, Any]:
    """Get the current authentication status and metadata."""
    creds = get_credentials()
    has_custom = load_credentials() is not None or bool(
        os.getenv("NUTRILOG_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID")
    )
    if not creds:
        return {
            "authenticated": False,
            "has_saved_tokens": load_tokens() is not None,
            "has_credentials_configured": get_client_config() is not None,
            "using_default_credentials": not has_custom,
        }

    return {
        "authenticated": True,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
        "scopes": creds.scopes,
        "has_credentials_configured": True,
        "using_default_credentials": not has_custom,
    }


def logout() -> bool:
    """Log out by clearing stored user tokens."""
    return delete_tokens()
