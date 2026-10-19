"""Configuration: defaults, loading with deep merge, validation and atomic saving.

The user config lives outside the repository (see paths.config_path). It only needs to hold
the values that differ from DEFAULT_CONFIG; everything else is filled in by load_config.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LANGUAGES = ("en", "tr")
DAYS = ("today", "tomorrow")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

DEFAULT_CONFIG: dict[str, Any] = {
    "language": "en",
    "timezone": "Europe/Berlin",
    "location": {"name": "Heilbronn", "latitude": 49.1427, "longitude": 9.2109},
    "reminder_list": "Prep",
    "summaries": [
        {"id": "morning", "time": "08:00", "day": "today"},
        {"id": "evening", "time": "23:00", "day": "tomorrow"},
    ],
    "minutes": {"travel": 20, "prep": 20, "breakfast": 15, "buffer": 0},
    "thresholds": {"rain_probability": 40, "wind_kmh": 40, "layer_delta_c": 8},
    # Apparent temperature bands: the first band whose max_c is >= the temperature wins.
    # The last band has max_c null (no upper limit).
    "clothing_bands": [
        {
            "id": "freezing",
            "max_c": 0,
            "text": {
                "en": "Winter coat, hat, gloves and scarf.",
                "tr": "Kalın mont, bere, eldiven ve atkı.",
            },
        },
        {
            "id": "cold",
            "max_c": 7,
            "text": {"en": "Warm jacket and a scarf.", "tr": "Kalın ceket ve atkı."},
        },
        {
            "id": "cool",
            "max_c": 13,
            "text": {"en": "Light jacket.", "tr": "İnce ceket."},
        },
        {
            "id": "mild",
            "max_c": 19,
            "text": {"en": "Long sleeves, maybe a thin layer.", "tr": "Uzun kollu, belki ince bir kat."},
        },
        {
            "id": "warm",
            "max_c": None,
            "text": {"en": "T-shirt weather.", "tr": "Tişört havası."},
        },
    ],
    "parts": {"wake": True, "weather": True, "wear": True, "bag": True},
    "calendars": {"exclude": ["TUM CHN Events"], "only": [], "default_type": {}},
    "types": [
        {
            "id": "exam",
            "group": "School",
            "enabled": True,
            "keywords": ["exam", "midterm", "klausur", "prüfung", "sınav", "vize", "final"],
            "items": {
                "en": ["student ID", "pen set", "calculator (if allowed)", "water"],
                "tr": ["öğrenci kimliği", "kalem seti", "hesap makinesi (izin varsa)", "su"],
            },
        },
        {
            "id": "lecture",
            "group": "School",
            "enabled": True,
            "keywords": [
                "lecture",
                "tutorial",
                "seminar",
                "vorlesung",
                "vo",
                "übung",
                "ue",
                "tutorium",
                "ders",
                "seminer",
            ],
            "items": {
                "en": ["notebook", "pen", "laptop + charger", "student card"],
                "tr": ["defter", "kalem", "laptop + şarj aleti", "öğrenci kartı"],
            },
        },
        {
            "id": "swimming",
            "group": "Sport",
            "enabled": True,
            "keywords": ["swim", "swimming", "pool", "schwimmen", "schwimmbad", "yüzme", "havuz"],
            "items": {
                "en": ["swimsuit", "cap", "goggles", "towel", "flip-flops", "shower stuff"],
                "tr": ["mayo", "bone", "gözlük", "havlu", "terlik", "duş malzemeleri"],
            },
        },
        {
            "id": "gym",
            "group": "Sport",
            "enabled": True,
            "keywords": ["gym", "workout", "fitness", "training", "fitnessstudio", "spor", "antrenman"],
            "items": {
                "en": ["sports bag", "sports shoes", "towel", "water bottle", "headphones"],
                "tr": ["spor çantası", "spor ayakkabısı", "havlu", "su şişesi", "kulaklık"],
            },
        },
        {
            "id": "meeting",
            "group": "Work",
            "enabled": True,
            "keywords": ["meeting", "standup", "sync", "interview", "besprechung", "toplantı", "mülakat"],
            "items": {
                "en": ["laptop + charger", "notebook", "ID/card"],
                "tr": ["laptop + şarj aleti", "defter", "kimlik/kart"],
            },
        },
        {
            "id": "meal",
            "group": "Other",
            "enabled": True,
            "keywords": [
                "lunch",
                "dinner",
                "brunch",
                "mittagessen",
                "abendessen",
                "frühstück",
                "öğle yemeği",
                "akşam yemeği",
                "kahvaltı",
                "yemek",
            ],
            "items": {
                "en": ["wallet", "phone charger"],
                "tr": ["cüzdan", "telefon şarj aleti"],
            },
        },
        {
            "id": "travel",
            "group": "Other",
            "enabled": True,
            "keywords": ["flight", "train", "trip", "travel", "flug", "zug", "reise", "uçuş", "tren", "seyahat", "yolculuk"],
            "items": {
                "en": ["ID/passport", "ticket", "charger", "powerbank"],
                "tr": ["kimlik/pasaport", "bilet", "şarj aleti", "powerbank"],
            },
        },
        {
            "id": "appointment",
            "group": "Other",
            "enabled": True,
            "keywords": ["appointment", "doctor", "dentist", "arzt", "zahnarzt", "termin", "randevu", "doktor"],
            "items": {
                "en": ["ID", "insurance card", "appointment document"],
                "tr": ["kimlik", "sigorta kartı", "randevu belgesi"],
            },
        },
    ],
    "title_items": {},
    "keep_days": 2,
}


class ConfigError(ValueError):
    """The configuration is unreadable or invalid. `errors` lists every problem found."""

    def __init__(self, errors: list[str] | str) -> None:
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override into base. Dicts merge recursively; anything else is replaced."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(path: Path) -> dict[str, Any]:
    """Read the user config and merge it over the defaults. A missing file gives the defaults.

    The result is not validated; call validate_config before using it.
    """
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        user = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(user, dict):
        raise ConfigError(f"{path} must contain a JSON object at the top level")
    return _deep_merge(DEFAULT_CONFIG, user)


# --- validation -----------------------------------------------------------------------


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _check_number(errors: list[str], name: str, value: Any, low: float, high: float | None = None):
    if not _is_number(value):
        errors.append(f"{name} must be a number")
    elif value < low or (high is not None and value > high):
        bound = f"between {low} and {high}" if high is not None else f"at least {low}"
        errors.append(f"{name} must be {bound}, got {value}")


def _check_non_empty_str(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{name} must be a non-empty string")


def _check_translated(errors: list[str], name: str, value: Any, as_list: bool) -> None:
    """A dict with one entry per supported language (text or list of strings)."""
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object with keys {list(LANGUAGES)}")
        return
    for lang in LANGUAGES:
        if lang not in value:
            errors.append(f"{name} is missing the {lang!r} entry")
        elif as_list and not _is_str_list(value[lang]):
            errors.append(f"{name}.{lang} must be a list of strings")
        elif not as_list and (not isinstance(value[lang], str) or not value[lang].strip()):
            errors.append(f"{name}.{lang} must be a non-empty string")
    for lang in value:
        if lang not in LANGUAGES:
            errors.append(f"{name} has unknown language {lang!r}")


def _section(errors: list[str], cfg: dict[str, Any], key: str, expected: set[str]) -> dict | None:
    value = cfg.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return None
    for missing in sorted(expected - value.keys()):
        errors.append(f"{key}.{missing} is missing")
    for extra in sorted(value.keys() - expected):
        errors.append(f"{key}: unknown key {extra!r}")
    return value


def _validate_summaries(errors: list[str], summaries: Any) -> None:
    if not isinstance(summaries, list) or not summaries:
        errors.append("summaries must be a non-empty list")
        return
    seen: set[str] = set()
    for i, item in enumerate(summaries):
        name = f"summaries[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{name} must be an object")
            continue
        slot_id = item.get("id")
        if not isinstance(slot_id, str) or not _ID_RE.match(slot_id):
            errors.append(f"{name}.id must be lowercase letters, digits, '-' or '_', got {slot_id!r}")
        elif slot_id in seen:
            errors.append(f"duplicate summary id {slot_id!r}")
        else:
            seen.add(slot_id)
        time = item.get("time")
        if not isinstance(time, str) or not _TIME_RE.match(time):
            errors.append(f"{name}.time must be HH:MM (00:00-23:59), got {time!r}")
        day = item.get("day")
        if day not in DAYS:
            errors.append(f"{name}.day must be one of {list(DAYS)}, got {day!r}")


def _validate_types(errors: list[str], types: Any) -> set[str]:
    ids: set[str] = set()
    if not isinstance(types, list):
        errors.append("types must be a list")
        return ids
    for i, item in enumerate(types):
        name = f"types[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{name} must be an object")
            continue
        type_id = item.get("id")
        if not isinstance(type_id, str) or not _ID_RE.match(type_id):
            errors.append(f"{name}.id must be lowercase letters, digits, '-' or '_', got {type_id!r}")
        elif type_id in ids:
            errors.append(f"duplicate type id {type_id!r}")
        else:
            ids.add(type_id)
        _check_non_empty_str(errors, f"{name}.group", item.get("group"))
        if not isinstance(item.get("enabled"), bool):
            errors.append(f"{name}.enabled must be true or false")
        if not _is_str_list(item.get("keywords")):
            errors.append(f"{name}.keywords must be a list of strings")
        _check_translated(errors, f"{name}.items", item.get("items"), as_list=True)
    return ids


def _validate_clothing(errors: list[str], bands: Any) -> None:
    if not isinstance(bands, list) or not bands:
        errors.append("clothing_bands must be a non-empty list")
        return
    ids: set[str] = set()
    limits: list[float] = []
    last = len(bands) - 1
    for i, band in enumerate(bands):
        name = f"clothing_bands[{i}]"
        if not isinstance(band, dict):
            errors.append(f"{name} must be an object")
            continue
        band_id = band.get("id")
        if not isinstance(band_id, str) or not _ID_RE.match(band_id):
            errors.append(f"{name}.id must be lowercase letters, digits, '-' or '_', got {band_id!r}")
        elif band_id in ids:
            errors.append(f"duplicate clothing band id {band_id!r}")
        else:
            ids.add(band_id)
        max_c = band.get("max_c")
        if i == last:
            if max_c is not None:
                errors.append("the last clothing band must have max_c null (no upper limit)")
        elif not _is_number(max_c):
            errors.append(f"{name}.max_c must be a number (only the last band may be null)")
        else:
            limits.append(max_c)
        _check_translated(errors, f"{name}.text", band.get("text"), as_list=False)
    if any(a >= b for a, b in zip(limits, limits[1:])):
        errors.append("clothing_bands max_c values must be in strictly ascending order")


def validate_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Check a full config and raise ConfigError listing every problem. Returns cfg."""
    errors: list[str] = []
    if not isinstance(cfg, dict):
        raise ConfigError("config must be an object")

    for extra in sorted(cfg.keys() - DEFAULT_CONFIG.keys()):
        errors.append(f"unknown key {extra!r}")
    for missing in sorted(DEFAULT_CONFIG.keys() - cfg.keys()):
        errors.append(f"{missing} is missing")

    if "language" in cfg and cfg["language"] not in LANGUAGES:
        errors.append(f"language must be one of {list(LANGUAGES)}, got {cfg['language']!r}")

    if "timezone" in cfg:
        tz = cfg["timezone"]
        try:
            if not isinstance(tz, str) or not tz:
                raise ZoneInfoNotFoundError(tz)
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            errors.append(f"timezone must be a valid IANA name such as Europe/Berlin, got {tz!r}")

    if "location" in cfg:
        loc = _section(errors, cfg, "location", {"name", "latitude", "longitude"})
        if loc is not None:
            if "name" in loc:
                _check_non_empty_str(errors, "location.name", loc["name"])
            if "latitude" in loc:
                _check_number(errors, "location.latitude", loc["latitude"], -90, 90)
            if "longitude" in loc:
                _check_number(errors, "location.longitude", loc["longitude"], -180, 180)

    if "reminder_list" in cfg:
        _check_non_empty_str(errors, "reminder_list", cfg["reminder_list"])

    if "summaries" in cfg:
        _validate_summaries(errors, cfg["summaries"])

    if "minutes" in cfg:
        minutes = _section(errors, cfg, "minutes", {"travel", "prep", "breakfast", "buffer"})
        for key, value in (minutes or {}).items():
            if key in DEFAULT_CONFIG["minutes"]:
                if not _is_int(value):
                    errors.append(f"minutes.{key} must be a whole number")
                elif value < 0:
                    errors.append(f"minutes.{key} must not be negative, got {value}")

    if "thresholds" in cfg:
        limits = {"rain_probability": (0, 100), "wind_kmh": (0, None), "layer_delta_c": (0, None)}
        thresholds = _section(errors, cfg, "thresholds", set(limits))
        for key, value in (thresholds or {}).items():
            if key in limits:
                _check_number(errors, f"thresholds.{key}", value, *limits[key])

    if "clothing_bands" in cfg:
        _validate_clothing(errors, cfg["clothing_bands"])

    if "parts" in cfg:
        parts = _section(errors, cfg, "parts", {"wake", "weather", "wear", "bag"})
        for key, value in (parts or {}).items():
            if key in DEFAULT_CONFIG["parts"] and not isinstance(value, bool):
                errors.append(f"parts.{key} must be true or false")

    type_ids: set[str] = set()
    if "types" in cfg:
        type_ids = _validate_types(errors, cfg["types"])

    if "calendars" in cfg:
        cals = _section(errors, cfg, "calendars", {"exclude", "only", "default_type"})
        if cals is not None:
            for key in ("exclude", "only"):
                if key in cals and not _is_str_list(cals[key]):
                    errors.append(f"calendars.{key} must be a list of strings")
            default_type = cals.get("default_type")
            if "default_type" in cals:
                if not isinstance(default_type, dict):
                    errors.append("calendars.default_type must be an object")
                else:
                    for calendar, type_id in default_type.items():
                        if type_id not in type_ids:
                            errors.append(
                                f"calendars.default_type[{calendar!r}] refers to unknown type {type_id!r}"
                            )

    if "title_items" in cfg:
        title_items = cfg["title_items"]
        if not isinstance(title_items, dict):
            errors.append("title_items must be an object mapping a title to a list of items")
        else:
            for title, items in title_items.items():
                if not _is_str_list(items):
                    errors.append(f"title_items[{title!r}] must be a list of strings")

    if "keep_days" in cfg and (not _is_int(cfg["keep_days"]) or cfg["keep_days"] < 0):
        errors.append(f"keep_days must be a whole number of at least 0, got {cfg['keep_days']!r}")

    if errors:
        raise ConfigError(errors)
    return cfg


# --- saving ---------------------------------------------------------------------------


def save_config(path: Path, cfg: dict[str, Any]) -> None:
    """Validate and write the config atomically. The previous file is kept as <name>.bak."""
    validate_config(cfg)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
