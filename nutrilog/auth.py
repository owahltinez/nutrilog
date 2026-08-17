"""OAuth 2.0 authentication manager for Google Health API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
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
    "https://www.googleapis.com/auth/health.nutrition.writeonly",
    "https://www.googleapis.com/auth/health.nutrition.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"


def get_client_config() -> Optional[dict[str, Any]]:
    """Retrieve client credentials from env vars or credentials.json."""
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
            return None

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


def login(
    client_config_path: Optional[Path] = None,
    port: int = 0,
    open_browser: bool = True,
) -> Credentials:
    """Run local server OAuth 2.0 flow to obtain user credentials."""
    client_config = None
    if client_config_path and client_config_path.exists():
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_config_path),
            scopes=SCOPES,
        )
    else:
        client_config = get_client_config()
        if not client_config:
            raise ValueError(
                "No OAuth client credentials found. Please provide a client_secrets.json file, "
                "set NUTRILOG_CLIENT_ID and NUTRILOG_CLIENT_SECRET, or run 'nutrilog auth setup'."
            )
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    creds = flow.run_local_server(
        port=port,
        open_browser=open_browser,
        prompt="consent",
        access_type="offline",
    )

    save_tokens(_token_dict_from_creds(creds))
    return creds


def get_auth_status() -> dict[str, Any]:
    """Get the current authentication status and metadata."""
    creds = get_credentials()
    if not creds:
        return {
            "authenticated": False,
            "has_saved_tokens": load_tokens() is not None,
            "has_credentials_configured": get_client_config() is not None,
        }

    return {
        "authenticated": True,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
        "scopes": creds.scopes,
        "has_credentials_configured": True,
    }


def logout() -> bool:
    """Log out by clearing stored user tokens."""
    return delete_tokens()
