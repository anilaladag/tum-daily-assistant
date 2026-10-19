from pathlib import Path

from tum_daily_assistant import paths


def test_defaults_use_macos_locations(monkeypatch):
    monkeypatch.delenv("TDA_HOME", raising=False)
    home = Path.home()
    assert paths.config_dir() == home / "Library/Application Support/tum-daily-assistant"
    assert paths.config_path() == paths.config_dir() / "config.json"
    assert paths.weather_cache_path() == paths.config_dir() / "weather.json"
    assert paths.log_path() == home / "Library/Logs/tum-daily-assistant.log"


def test_tda_home_overrides_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("TDA_HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path
    assert paths.config_path() == tmp_path / "config.json"
    assert paths.weather_cache_path() == tmp_path / "weather.json"
    assert paths.log_path() == tmp_path / "tum-daily-assistant.log"


def test_empty_tda_home_is_ignored(monkeypatch):
    monkeypatch.setenv("TDA_HOME", "")
    assert paths.config_dir() == Path.home() / "Library/Application Support/tum-daily-assistant"
