"""Unit tests for nutrilog.auth."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from google.oauth2.credentials import Credentials

from nutrilog.auth import (
    get_auth_status,
    get_client_config,
    get_credentials,
    login,
    logout,
)
from nutrilog.storage import ENV_CONFIG_DIR, save_credentials, save_tokens


@pytest.fixture
def temp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom_dir = tmp_path / "nutrilog_auth_test"
    monkeypatch.setenv(ENV_CONFIG_DIR, str(custom_dir))
    return custom_dir


def test_get_client_config_from_env(monkeypatch: pytest.MonkeyPatch, temp_config_dir: Path):
    monkeypatch.setenv("NUTRILOG_CLIENT_ID", "env-client-id")
    monkeypatch.setenv("NUTRILOG_CLIENT_SECRET", "env-client-secret")

    config = get_client_config()
    assert config is not None
    assert config["installed"]["client_id"] == "env-client-id"
    assert config["installed"]["client_secret"] == "env-client-secret"


def test_get_client_config_from_storage(monkeypatch: pytest.MonkeyPatch, temp_config_dir: Path):
    monkeypatch.delenv("NUTRILOG_CLIENT_ID", raising=False)
    monkeypatch.delenv("NUTRILOG_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    assert get_client_config() is None

    stored = {"installed": {"client_id": "stored-id", "client_secret": "stored-secret"}}
    save_credentials(stored)
    assert get_client_config() == stored


def test_get_credentials_none_when_empty(temp_config_dir: Path):
    assert get_credentials() is None
    status = get_auth_status()
    assert status["authenticated"] is False


def test_get_credentials_valid(temp_config_dir: Path):
    token_data = {
        "token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "scopes": ["https://www.googleapis.com/auth/health.nutrition.writeonly"],
        "expiry": "2030-01-01T00:00:00Z",
    }
    save_tokens(token_data)

    creds = get_credentials()
    assert creds is not None
    assert creds.token == "test-access-token"

    status = get_auth_status()
    assert status["authenticated"] is True


def test_get_credentials_expired_refreshed(temp_config_dir: Path):
    token_data = {
        "token": "expired-token",
        "refresh_token": "test-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "scopes": ["https://www.googleapis.com/auth/health.nutrition.writeonly"],
        "expiry": "2020-01-01T00:00:00Z",
    }
    save_tokens(token_data)

    with patch.object(Credentials, "refresh") as mock_refresh:
        with patch.object(Credentials, "valid", return_value=True):
            creds = get_credentials()
            assert creds is not None
            mock_refresh.assert_called_once()


def test_logout(temp_config_dir: Path):
    save_tokens({"token": "abc", "expiry": "2030-01-01T00:00:00Z"})
    assert logout() is True
    assert get_auth_status()["authenticated"] is False


def test_login_flow(temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NUTRILOG_CLIENT_ID", "test-id")
    monkeypatch.setenv("NUTRILOG_CLIENT_SECRET", "test-secret")

    mock_creds = MagicMock()
    mock_creds.token = "new-token"
    mock_creds.refresh_token = "new-refresh"
    mock_creds.token_uri = "https://oauth2.googleapis.com/token"
    mock_creds.client_id = "test-id"
    mock_creds.client_secret = "test-secret"
    mock_creds.scopes = ["scope1"]
    mock_creds.expiry = datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)

    with patch("nutrilog.auth.InstalledAppFlow.from_client_config") as mock_flow_init:
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_init.return_value = mock_flow

        creds = login(port=0, open_browser=False)
        assert creds == mock_creds
        mock_flow.run_local_server.assert_called_once()
