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
    load_tokens,
    save_config,
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


def test_timezone_storage_and_resolution(temp_config_dir: Path):
    from datetime import timedelta, timezone
    from nutrilog.storage import (
        get_configured_timezone_name,
        get_machine_timezone,
        get_user_timezone,
        resolve_timezone,
        set_user_timezone,
    )

    # Defaults to machine timezone when not set
    assert get_configured_timezone_name() is None
    assert get_user_timezone() == get_machine_timezone()

    # Resolve common aliases
    syd = resolve_timezone("AEST")
    assert str(syd) == "Australia/Sydney"

    ny = resolve_timezone("America/New_York")
    assert str(ny) == "America/New_York"

    offset_tz = resolve_timezone("UTC+10")
    assert offset_tz == timezone(timedelta(hours=10))

    # Set timezone in config
    saved = set_user_timezone("Australia/Sydney")
    assert saved == "Australia/Sydney"
    assert get_configured_timezone_name() == "Australia/Sydney"
    assert str(get_user_timezone()) == "Australia/Sydney"

    # Reset to auto/machine local
    set_user_timezone("auto")
    assert get_configured_timezone_name() is None
    assert get_user_timezone() == get_machine_timezone()

    # Invalid timezone raises ValueError
    with pytest.raises(ValueError, match="Unknown or invalid timezone"):
        resolve_timezone("Invalid/NonExistentZone")
