"""Unit tests for nutrilog.storage."""

import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nutrilog.models import TimeInterval
from nutrilog.storage import (
    ENV_CONFIG_DIR,
    delete_tokens,
    get_config_dir,
    get_configured_timezone_name,
    get_machine_timezone,
    get_user_timezone,
    load_tokens,
    resolve_timezone,
    save_tokens,
    set_user_timezone,
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


def test_timezone_storage_and_resolution(temp_config_dir: Path):
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


@pytest.fixture
def system_timezone(monkeypatch: pytest.MonkeyPatch):
    """Set process timezone the way the OS would, restoring it afterwards."""

    def _set(name: str):
        monkeypatch.setenv("TZ", name)
        time.tzset()

    yield _set
    monkeypatch.undo()
    time.tzset()


def test_machine_timezone_tracks_dst(system_timezone):
    """A fixed-offset snapshot goes wrong when the zone changes offset.

    Sydney is UTC+10 in August and UTC+11 in December; a machine timezone
    captured once would misreport December.
    """
    system_timezone("Australia/Sydney")
    machine_tz = get_machine_timezone()

    winter = datetime(2026, 8, 19, 12, 0, tzinfo=machine_tz).utcoffset()
    summer = datetime(2026, 12, 19, 12, 0, tzinfo=machine_tz).utcoffset()

    assert winter == timedelta(hours=10)
    assert summer == timedelta(hours=11)


def test_machine_timezone_handles_northern_hemisphere_dst(system_timezone):
    system_timezone("America/New_York")
    machine_tz = get_machine_timezone()

    assert datetime(
        2026, 1, 15, 12, 0, tzinfo=machine_tz
    ).utcoffset() == timedelta(hours=-5)
    assert datetime(
        2026, 7, 15, 12, 0, tzinfo=machine_tz
    ).utcoffset() == timedelta(hours=-4)


def test_resolve_timezone_auto_tracks_dst(system_timezone):
    """'auto' must inherit the same DST awareness, not just the raw default."""
    system_timezone("Australia/Sydney")

    resolved = resolve_timezone("auto")

    assert datetime(
        2026, 12, 19, 12, 0, tzinfo=resolved
    ).utcoffset() == timedelta(hours=11)


def test_logged_meal_offset_follows_dst(system_timezone):
    """Logged meal offset must follow DST (e.g. +11 in Sydney summer)."""
    system_timezone("Australia/Sydney")
    summer_meal = datetime(2026, 12, 19, 9, 30, tzinfo=get_machine_timezone())

    interval = TimeInterval.from_datetimes(summer_meal)

    assert interval.startUtcOffset == "39600s"


def test_machine_timezone_is_named_not_anonymous(system_timezone):
    """`config show` prints named zone: "Australia/Sydney", not "tzlocal()"."""
    system_timezone("Australia/Sydney")

    assert str(get_machine_timezone()) == "Australia/Sydney"


def test_machine_timezone_falls_back_when_zone_is_unnameable(system_timezone):
    """A TZ set to a bare offset names no IANA zone, but must still resolve."""
    system_timezone("UTC+5")
    machine_tz = get_machine_timezone()

    assert (
        datetime(2026, 8, 19, 12, 0, tzinfo=machine_tz).utcoffset() is not None
    )
