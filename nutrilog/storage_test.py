"""Unit tests for nutrilog.storage."""

import os
import stat
from pathlib import Path
import pytest

from nutrilog.storage import (
    ENV_CONFIG_DIR,
    delete_tokens,
    get_config_dir,
    get_daily_targets,
    load_config,
    load_credentials,
    load_tokens,
    save_config,
    save_credentials,
    save_tokens,
    set_daily_targets,
)


@pytest.fixture
def temp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom_dir = tmp_path / "nutrilog_test_config"
    monkeypatch.setenv(ENV_CONFIG_DIR, str(custom_dir))
    return custom_dir


def test_get_config_dir_creation(temp_config_dir: Path):
    assert not temp_config_dir.exists()
    d = get_config_dir()
    assert d == temp_config_dir
    assert d.exists()
    assert d.is_dir()


def test_save_and_load_tokens(temp_config_dir: Path):
    assert load_tokens() is None

    tokens_data = {
        "access_token": "mock-test-access-token",
        "refresh_token": "1//test-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test-client-id",
    }
    save_tokens(tokens_data)

    loaded = load_tokens()
    assert loaded == tokens_data

    # Check file permissions on Linux / POSIX
    tokens_file = temp_config_dir / "tokens.json"
    assert tokens_file.exists()
    mode = stat.S_IMODE(tokens_file.stat().st_mode)
    assert mode == 0o600

    assert delete_tokens() is True
    assert load_tokens() is None
    assert delete_tokens() is False


def test_save_and_load_credentials(temp_config_dir: Path):
    assert load_credentials() is None

    creds = {"installed": {"client_id": "cid", "client_secret": "csec"}}
    save_credentials(creds)

    loaded = load_credentials()
    assert loaded == creds


def test_daily_targets_config(temp_config_dir: Path):
    targets = get_daily_targets()
    assert targets.calories == 2000.0
    assert targets.protein == 120.0

    updated = set_daily_targets(calories=2200.0, protein=140.0, carbs=250.0, fat=60.0)
    assert updated.calories == 2200.0
    assert updated.protein == 140.0
    assert updated.carbs == 250.0
    assert updated.fat == 60.0

    # Ensure persistence
    reloaded = get_daily_targets()
    assert reloaded.calories == 2200.0
    assert reloaded.protein == 140.0
    assert reloaded.carbs == 250.0
    assert reloaded.fat == 60.0
