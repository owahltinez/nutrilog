"""Secure local storage management for Nutrilog credentials and configuration."""

from __future__ import annotations

import json
import os
import re
import zoneinfo
from datetime import timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Optional, Union
from dateutil import tz

ENV_CONFIG_DIR = "NUTRILOG_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "nutrilog"

COMMON_TZ_ALIASES = {
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
    "ACST": "Australia/Adelaide",
    "ACDT": "Australia/Adelaide",
    "AWST": "Australia/Perth",
    "NZST": "Pacific/Auckland",
    "NZDT": "Pacific/Auckland",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "GMT": "UTC",
    "UTC": "UTC",
    "Z": "UTC",
}


# Where the OS records which IANA zone it is set to.
_LOCALTIME_LINK = Path("/etc/localtime")
_ZONEINFO_MARKER = "zoneinfo/"


def get_machine_timezone_name() -> Optional[str]:
    """The system's IANA zone name (e.g. "Australia/Sydney"), if one can be determined."""
    env_tz = os.getenv("TZ")
    if env_tz:
        try:
            zoneinfo.ZoneInfo(env_tz)
            return env_tz
        except Exception:
            pass  # TZ can hold a bare offset, which names no zone.

    # The symlink target ends with the zone name, e.g. /var/db/timezone/zoneinfo/Australia/Sydney
    try:
        if _LOCALTIME_LINK.is_symlink():
            target = str(_LOCALTIME_LINK.resolve())
            _, marker, name = target.partition(_ZONEINFO_MARKER)
            if marker and name:
                zoneinfo.ZoneInfo(name)
                return name
    except Exception:
        pass
    return None


def get_machine_timezone() -> tzinfo:
    """Return the user's machine/system local timezone.

    Deliberately not `datetime.now().astimezone().tzinfo`: that captures today's offset as a
    fixed value, so a zone with daylight saving keeps reporting the offset in force when the
    process started. Sydney would stamp December meals +10 instead of +11, putting them an hour
    out and pushing late-evening ones onto the wrong civil day.

    A named zone is preferred over `tzlocal` because both resolve the offset per datetime, but
    only the named one reports which zone it is when displayed.
    """
    name = get_machine_timezone_name()
    if name:
        return zoneinfo.ZoneInfo(name)
    return tz.tzlocal()


def resolve_timezone(tz_input: Union[str, tzinfo, None]) -> tzinfo:
    """Resolve a string, abbreviation, offset, or tzinfo into a valid tzinfo object."""
    if tz_input is None:
        return get_machine_timezone()
    if isinstance(tz_input, tzinfo):
        return tz_input

    tz_str = tz_input.strip()
    if not tz_str or tz_str.lower() in ("auto", "local", "system"):
        return get_machine_timezone()

    upper = tz_str.upper()
    if upper in COMMON_TZ_ALIASES:
        tz_str = COMMON_TZ_ALIASES[upper]

    try:
        return zoneinfo.ZoneInfo(tz_str)
    except Exception:
        pass

    offset_match = re.match(
        r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", tz_str, re.IGNORECASE
    )
    if offset_match:
        sign = -1 if offset_match.group(1) == "-" else 1
        hours = int(offset_match.group(2))
        minutes = int(offset_match.group(3) or 0)
        return timezone(sign * timedelta(hours=hours, minutes=minutes))

    d_tz = tz.gettz(tz_str)
    if d_tz is not None:
        return d_tz

    raise ValueError(f"Unknown or invalid timezone: '{tz_input}'")


def get_config_dir() -> Path:
    """Return the active configuration directory and ensure it exists with secure permissions."""
    custom_dir = os.getenv(ENV_CONFIG_DIR)
    config_dir = Path(custom_dir) if custom_dir else DEFAULT_CONFIG_DIR
    if not config_dir.exists():
        config_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    else:
        try:
            config_dir.chmod(0o700)
        except OSError:
            pass
    return config_dir


def get_tokens_path() -> Path:
    return get_config_dir() / "tokens.json"


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def _write_secure_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON data to a file with 0600 permissions."""
    get_config_dir()  # Ensure parent dir exists
    content = json.dumps(data, indent=2)
    # Write file
    path.write_text(content, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    """Read JSON data from a file, returning None if not found or invalid."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_tokens(tokens: dict[str, Any]) -> None:
    """Save OAuth tokens securely."""
    _write_secure_json(get_tokens_path(), tokens)


def load_tokens() -> Optional[dict[str, Any]]:
    """Load stored OAuth tokens."""
    return _read_json(get_tokens_path())


def delete_tokens() -> bool:
    """Delete stored OAuth tokens (logout)."""
    tokens_file = get_tokens_path()
    if tokens_file.exists():
        tokens_file.unlink()
        return True
    return False


def save_config(config: dict[str, Any]) -> None:
    """Save user configuration settings."""
    _write_secure_json(get_config_path(), config)


def load_config() -> dict[str, Any]:
    """Load user configuration settings."""
    data = _read_json(get_config_path())
    return data if data is not None else {}


def get_configured_timezone_name() -> Optional[str]:
    """Retrieve the configured timezone name from config, or None if using machine local."""
    cfg = load_config()
    tz_val = cfg.get("timezone")
    if tz_val and str(tz_val).strip() and str(tz_val).strip().lower() not in ("auto", "local", "system"):
        return str(tz_val).strip()
    return None


def get_user_timezone(tz_override: Optional[str] = None) -> tzinfo:
    """Retrieve the active timezone.

    1. If tz_override is provided, use that.
    2. If a timezone is saved in config, use that.
    3. Otherwise, use the user's machine/system local timezone.
    """
    if tz_override:
        return resolve_timezone(tz_override)
    cfg_tz = get_configured_timezone_name()
    if cfg_tz:
        try:
            return resolve_timezone(cfg_tz)
        except Exception:
            pass
    return get_machine_timezone()


def set_user_timezone(tz_name: Optional[str]) -> Optional[str]:
    """Set or clear the user configured timezone.

    If tz_name is None, empty, or 'auto'/'system'/'local', removes the configured timezone
    so Nutrilog defaults to the machine's local timezone.
    """
    cfg = load_config()
    if not tz_name or tz_name.strip().lower() in ("auto", "local", "system", "none", "clear"):
        cfg.pop("timezone", None)
        save_config(cfg)
        return None

    # Validate timezone
    resolve_timezone(tz_name)
    tz_cleaned = tz_name.strip()
    upper = tz_cleaned.upper()
    canonical_name = COMMON_TZ_ALIASES.get(upper, tz_cleaned)
    cfg["timezone"] = canonical_name
    save_config(cfg)
    return canonical_name
