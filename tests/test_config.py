import copy
import json
from pathlib import Path

import pytest

from tum_daily_assistant.config import (
    DEFAULT_CONFIG,
    ConfigError,
    load_config,
    save_config,
    validate_config,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def fresh():
    return copy.deepcopy(DEFAULT_CONFIG)


# --- defaults -------------------------------------------------------------------------


def test_defaults_are_valid():
    validate_config(fresh())


def test_default_values_match_design():
    cfg = DEFAULT_CONFIG
    assert cfg["language"] == "en"
    assert cfg["timezone"] == "Europe/Berlin"
    assert cfg["location"] == {"name": "Heilbronn", "latitude": 49.1427, "longitude": 9.2109}
    assert cfg["reminder_list"] == "Prep"
    assert cfg["summaries"] == [
        {"id": "morning", "time": "08:00", "day": "today"},
        {"id": "evening", "time": "23:00", "day": "tomorrow"},
    ]
    assert cfg["minutes"] == {"travel": 20, "prep": 20, "breakfast": 15, "buffer": 0}
    assert cfg["thresholds"] == {"rain_probability": 40, "wind_kmh": 40, "layer_delta_c": 8}
    assert cfg["parts"] == {"wake": True, "weather": True, "wear": True, "bag": True}
    assert cfg["calendars"]["exclude"] == ["TUM CHN Events"]
    assert cfg["calendars"]["only"] == []
    assert cfg["keep_days"] == 2


def test_default_types_order_and_groups():
    types = DEFAULT_CONFIG["types"]
    assert [t["id"] for t in types] == [
        "exam",
        "lecture",
        "swimming",
        "gym",
        "meeting",
        "meal",
        "travel",
        "appointment",
    ]
    groups = {t["id"]: t["group"] for t in types}
    assert groups == {
        "exam": "School",
        "lecture": "School",
        "swimming": "Sport",
        "gym": "Sport",
        "meeting": "Work",
        "meal": "Other",
        "travel": "Other",
        "appointment": "Other",
    }


def test_default_types_have_english_and_turkish_items():
    for type_ in DEFAULT_CONFIG["types"]:
        assert type_["enabled"] is True
        assert type_["keywords"]
        assert type_["items"]["en"]
        assert type_["items"]["tr"]


def test_default_keywords_cover_three_languages():
    lecture = next(t for t in DEFAULT_CONFIG["types"] if t["id"] == "lecture")
    assert {"lecture", "vorlesung", "ders"} <= set(lecture["keywords"])
    exam = next(t for t in DEFAULT_CONFIG["types"] if t["id"] == "exam")
    assert {"exam", "klausur", "prüfung", "sınav"} <= set(exam["keywords"])


def test_default_clothing_bands_are_ordered_with_open_last_band():
    bands = DEFAULT_CONFIG["clothing_bands"]
    limits = [b["max_c"] for b in bands]
    assert limits[:-1] == sorted(limits[:-1])
    assert limits[-1] is None
    assert len({b["id"] for b in bands}) == len(bands)


def test_example_file_matches_defaults():
    example = json.loads((REPO_ROOT / "config.example.json").read_text(encoding="utf-8"))
    assert example == DEFAULT_CONFIG


# --- load -----------------------------------------------------------------------------


def test_load_missing_file_returns_defaults(tmp_path):
    assert load_config(tmp_path / "config.json") == DEFAULT_CONFIG


def test_load_returns_independent_copy(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    cfg["minutes"]["travel"] = 99
    cfg["types"].clear()
    assert DEFAULT_CONFIG["minutes"]["travel"] == 20
    assert DEFAULT_CONFIG["types"]


def test_load_deep_merges_nested_dicts(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"language": "tr", "minutes": {"travel": 35}}), encoding="utf-8")
    cfg = load_config(path)
    assert cfg["language"] == "tr"
    assert cfg["minutes"] == {"travel": 35, "prep": 20, "breakfast": 15, "buffer": 0}
    assert cfg["location"] == DEFAULT_CONFIG["location"]


def test_load_replaces_lists_instead_of_merging(tmp_path):
    path = tmp_path / "config.json"
    summaries = [{"id": "noon", "time": "12:00", "day": "today"}]
    path.write_text(json.dumps({"summaries": summaries}), encoding="utf-8")
    assert load_config(path)["summaries"] == summaries


def test_load_rejects_invalid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_config(path)


def test_load_rejects_non_object_root(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON object"):
        load_config(path)


# --- validate -------------------------------------------------------------------------


def set_path(cfg, dotted, value):
    parts = dotted.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return cfg


INVALID_CASES = [
    ("language", "de", "language"),
    ("language", 5, "language"),
    ("timezone", "Mars/Base", "timezone"),
    ("location.latitude", 91, "latitude"),
    ("location.latitude", -90.5, "latitude"),
    ("location.longitude", 181, "longitude"),
    ("location.longitude", "9.2", "longitude"),
    ("reminder_list", "", "reminder_list"),
    ("summaries.0.time", "25:00", "time"),
    ("summaries.0.time", "8:00", "time"),
    ("summaries.0.time", "08:60", "time"),
    ("summaries.0.day", "yesterday", "day"),
    ("summaries.0.id", "Bad Id", "id"),
    ("minutes.travel", -1, "minutes.travel"),
    ("minutes.prep", "20", "minutes.prep"),
    ("minutes.buffer", True, "minutes.buffer"),
    ("thresholds.rain_probability", 101, "rain_probability"),
    ("thresholds.wind_kmh", -5, "wind_kmh"),
    ("thresholds.layer_delta_c", -1, "layer_delta_c"),
    ("parts.wake", "yes", "parts.wake"),
    ("keep_days", -1, "keep_days"),
    ("calendars.exclude", "TUM", "calendars.exclude"),
    ("calendars.default_type", {"Cal": "nonexistent"}, "default_type"),
    ("title_items", {"Math": "pen"}, "title_items"),
    ("types.0.group", "", "group"),
    ("types.0.keywords", "exam", "keywords"),
    ("types.0.items", {"tr": ["kalem"]}, "items"),
    ("types.0.enabled", "yes", "enabled"),
    ("clothing_bands.0.max_c", "cold", "max_c"),
    ("clothing_bands.0.text", {"tr": "x"}, "text"),
]


@pytest.mark.parametrize(("path", "value", "fragment"), INVALID_CASES)
def test_validate_rejects_bad_values(path, value, fragment):
    cfg = set_path(fresh(), path, value)
    with pytest.raises(ConfigError, match=fragment):
        validate_config(cfg)


def test_validate_rejects_duplicate_summary_ids():
    cfg = fresh()
    cfg["summaries"][1]["id"] = cfg["summaries"][0]["id"]
    with pytest.raises(ConfigError, match="duplicate summary id"):
        validate_config(cfg)


def test_validate_rejects_duplicate_type_ids():
    cfg = fresh()
    cfg["types"][1]["id"] = cfg["types"][0]["id"]
    with pytest.raises(ConfigError, match="duplicate type id"):
        validate_config(cfg)


def test_validate_rejects_unsorted_clothing_bands():
    cfg = fresh()
    cfg["clothing_bands"][0], cfg["clothing_bands"][1] = (
        cfg["clothing_bands"][1],
        cfg["clothing_bands"][0],
    )
    with pytest.raises(ConfigError, match="ascending"):
        validate_config(cfg)


def test_validate_requires_open_last_clothing_band():
    cfg = fresh()
    cfg["clothing_bands"][-1]["max_c"] = 40
    with pytest.raises(ConfigError, match="last clothing band"):
        validate_config(cfg)


def test_validate_rejects_unknown_top_level_key():
    cfg = fresh()
    cfg["langauge"] = "tr"
    with pytest.raises(ConfigError, match="unknown key"):
        validate_config(cfg)


def test_validate_reports_all_problems_at_once():
    cfg = fresh()
    cfg["language"] = "de"
    cfg["minutes"]["travel"] = -3
    with pytest.raises(ConfigError) as info:
        validate_config(cfg)
    assert len(info.value.errors) == 2
    assert "language" in str(info.value) and "minutes.travel" in str(info.value)


def test_validate_accepts_turkish_and_valid_edge_values():
    cfg = fresh()
    cfg["language"] = "tr"
    cfg["location"]["latitude"] = 90
    cfg["location"]["longitude"] = -180
    cfg["minutes"]["buffer"] = 0
    cfg["summaries"][0]["time"] = "00:00"
    cfg["summaries"][1]["time"] = "23:59"
    validate_config(cfg)


def test_validate_returns_the_config_for_chaining():
    cfg = fresh()
    assert validate_config(cfg) is cfg


# --- save -----------------------------------------------------------------------------


def test_save_roundtrip(tmp_path):
    path = tmp_path / "sub" / "config.json"
    cfg = fresh()
    cfg["language"] = "tr"
    save_config(path, cfg)
    assert load_config(path)["language"] == "tr"
    assert not path.with_name("config.json.bak").exists()


def test_save_keeps_backup_of_previous_file(tmp_path):
    path = tmp_path / "config.json"
    first = fresh()
    first["reminder_list"] = "First"
    save_config(path, first)
    second = fresh()
    second["reminder_list"] = "Second"
    save_config(path, second)
    assert json.loads(path.read_text(encoding="utf-8"))["reminder_list"] == "Second"
    backup = tmp_path / "config.json.bak"
    assert json.loads(backup.read_text(encoding="utf-8"))["reminder_list"] == "First"


def test_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "config.json"
    save_config(path, fresh())
    save_config(path, fresh())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json", "config.json.bak"]


def test_save_refuses_invalid_config_and_keeps_file(tmp_path):
    path = tmp_path / "config.json"
    save_config(path, fresh())
    before = path.read_text(encoding="utf-8")
    bad = fresh()
    bad["minutes"]["travel"] = -1
    with pytest.raises(ConfigError):
        save_config(path, bad)
    assert path.read_text(encoding="utf-8") == before
    assert not (tmp_path / "config.json.bak").exists()


def test_save_writes_readable_utf8(tmp_path):
    path = tmp_path / "config.json"
    save_config(path, fresh())
    text = path.read_text(encoding="utf-8")
    assert "prüfung" in text and "sınav" in text
    assert text.endswith("\n")
