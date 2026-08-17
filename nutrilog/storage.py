"""Secure local storage management for Nutrilog credentials and configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from nutrilog.models import DailyTarget

ENV_CONFIG_DIR = "NUTRILOG_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "nutrilog"


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


def get_credentials_path() -> Path:
    return get_config_dir() / "credentials.json"


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


def save_credentials(creds: dict[str, Any]) -> None:
    """Save client secrets/credentials JSON."""
    _write_secure_json(get_credentials_path(), creds)


def load_credentials() -> Optional[dict[str, Any]]:
    """Load client secrets JSON."""
    return _read_json(get_credentials_path())


def save_config(config: dict[str, Any]) -> None:
    """Save user configuration settings."""
    _write_secure_json(get_config_path(), config)


def load_config() -> dict[str, Any]:
    """Load user configuration settings."""
    data = _read_json(get_config_path())
    return data if data is not None else {}


def get_daily_targets() -> DailyTarget:
    """Retrieve saved daily nutrition targets or defaults."""
    cfg = load_config()
    targets = cfg.get("targets", {})
    return DailyTarget(
        calories=float(targets.get("calories", 2000.0)),
        protein=float(targets.get("protein", 120.0)),
        carbs=float(targets["carbs"]) if targets.get("carbs") is not None else None,
        fat=float(targets["fat"]) if targets.get("fat") is not None else None,
    )


def set_daily_targets(
    calories: Optional[float] = None,
    protein: Optional[float] = None,
    carbs: Optional[float] = None,
    fat: Optional[float] = None,
) -> DailyTarget:
    """Update saved daily nutrition targets."""
    cfg = load_config()
    targets = cfg.get("targets", {})
    if calories is not None:
        targets["calories"] = calories
    if protein is not None:
        targets["protein"] = protein
    if carbs is not None:
        targets["carbs"] = carbs
    if fat is not None:
        targets["fat"] = fat

    cfg["targets"] = targets
    save_config(cfg)
    return get_daily_targets()
