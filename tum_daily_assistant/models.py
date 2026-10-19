"""Cross-module data structures. Everything is frozen and uses timezone-aware datetimes.

The models carry structured data only. Rendered text lives in the render module, so the
same Message can be turned into English, Turkish or any future layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime

DAYS = ("today", "tomorrow")
RAIN_GEARS = ("none", "umbrella", "raincoat")
OP_KINDS = ("create", "update", "delete")


def _require_aware(value: datetime | None, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} must be timezone-aware")


def reminder_key(day: date_type, slot_id: str) -> str:
    """Stable identity of a reminder, stored in its URL field."""
    return f"tda://{day.isoformat()}/{slot_id}"


@dataclass(frozen=True)
class Event:
    """A calendar event as read from the calendar source."""

    title: str
    start: datetime  # timezone-aware
    end: datetime  # timezone-aware, not before start
    calendar: str  # name of the calendar the event belongs to
    all_day: bool = False  # all-day events are normally filtered out before this point

    def __post_init__(self) -> None:
        _require_aware(self.start, "start")
        _require_aware(self.end, "end")
        if self.end < self.start:
            raise ValueError("end must not be before start")


@dataclass(frozen=True)
class ClassifiedEvent:
    """An event plus the result of classification. type_id is None when nothing matched."""

    event: Event
    type_id: str | None  # id of the matched type, e.g. "lecture"
    group: str | None  # bag group of the type, e.g. "School"
    items: tuple[str, ...]  # items to pack, title-specific items first


@dataclass(frozen=True)
class HourlyForecast:
    """One hour of weather data."""

    time: datetime  # start of the hour, timezone-aware
    apparent_temp_c: float
    precip_probability: float  # percent, 0-100
    precip_mm: float
    wind_kmh: float

    def __post_init__(self) -> None:
        _require_aware(self.time, "time")


@dataclass(frozen=True)
class Forecast:
    """A forecast with the moment it was fetched."""

    fetched_at: datetime  # timezone-aware
    hours: tuple[HourlyForecast, ...]

    def __post_init__(self) -> None:
        _require_aware(self.fetched_at, "fetched_at")


@dataclass(frozen=True)
class WeatherSummary:
    """Weather aggregated over the day window [first start - travel, last end + travel]."""

    window_start: datetime
    window_end: datetime
    temp_min_c: float  # apparent temperature
    temp_max_c: float
    rain_probability_max: float  # percent
    rain_from: datetime | None  # first / last hour at or above the rain threshold
    rain_to: datetime | None
    wind_max_kmh: float
    precip_mm_total: float

    def __post_init__(self) -> None:
        _require_aware(self.window_start, "window_start")
        _require_aware(self.window_end, "window_end")
        _require_aware(self.rain_from, "rain_from")
        _require_aware(self.rain_to, "rain_to")


@dataclass(frozen=True)
class BagGroup:
    """Deduplicated items of one bag group, in chronological order."""

    name: str  # e.g. "School"
    items: tuple[str, ...]


@dataclass(frozen=True)
class Message:
    """Structured content of one reminder (one date x summary slot). No rendered text."""

    slot_id: str  # id of the summary slot, e.g. "evening"
    date: date_type  # the day the message is about
    day: str  # "today" or "tomorrow": relation of date to the alarm
    alarm_at: datetime  # when the reminder fires, timezone-aware
    first_event: Event
    last_event: Event
    event_count: int
    wake_with_breakfast: datetime
    wake_without_breakfast: datetime
    leave_by: datetime
    weather: WeatherSummary | None  # None when no weather data is available
    rain_gear: str  # "none", "umbrella" or "raincoat"
    rain_reason: str | None  # short reason key, e.g. "rain_likely" or "rain_and_wind"
    clothing_key: str | None  # id of the clothing band; the text lives in config
    layers: bool  # True when the temperature range suggests layers
    bag: tuple[BagGroup, ...]
    weather_unavailable: bool = False
    stale_forecast: bool = False  # forecast is much older than the alarm
    forecast_fetched_at: datetime | None = None  # shown when stale_forecast is set
    calendar_stale: bool = False  # the calendar could not be refreshed
    calendar_synced_at: datetime | None = None  # last successful calendar read

    def __post_init__(self) -> None:
        if self.day not in DAYS:
            raise ValueError(f"day must be one of {DAYS}, got {self.day!r}")
        if self.rain_gear not in RAIN_GEARS:
            raise ValueError(f"rain_gear must be one of {RAIN_GEARS}, got {self.rain_gear!r}")
        for name in (
            "alarm_at",
            "wake_with_breakfast",
            "wake_without_breakfast",
            "leave_by",
            "forecast_fetched_at",
            "calendar_synced_at",
        ):
            _require_aware(getattr(self, name), name)

    @property
    def key(self) -> str:
        return reminder_key(self.date, self.slot_id)


@dataclass(frozen=True)
class ExistingReminder:
    """A reminder already present in the reminder list."""

    key: str  # URL field, "tda://<date>/<slot-id>"
    title: str
    notes: str
    alarm_at: datetime | None
    completed: bool

    def __post_init__(self) -> None:
        _require_aware(self.alarm_at, "alarm_at")


@dataclass(frozen=True)
class ReminderOp:
    """A change to apply to the reminder list. Delete only needs the key."""

    kind: str  # "create", "update" or "delete"
    key: str
    title: str | None = None
    notes: str | None = None
    alarm_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind not in OP_KINDS:
            raise ValueError(f"kind must be one of {OP_KINDS}, got {self.kind!r}")
        if self.kind != "delete" and self.title is None:
            raise ValueError("title is required for create and update")
        _require_aware(self.alarm_at, "alarm_at")
