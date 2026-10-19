"""Filesystem locations. All of them can be redirected with the TDA_HOME env var (tests)."""

import os
from pathlib import Path

APP_NAME = "tum-daily-assistant"


def _override() -> Path | None:
    value = os.environ.get("TDA_HOME")
    return Path(value) if value else None


def config_dir() -> Path:
    """Directory holding config.json and the weather cache."""
    return _override() or Path.home() / "Library" / "Application Support" / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def weather_cache_path() -> Path:
    return config_dir() / "weather.json"


def log_path() -> Path:
    base = _override() or Path.home() / "Library" / "Logs"
    return base / f"{APP_NAME}.log"
