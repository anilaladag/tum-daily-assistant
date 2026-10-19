import dataclasses
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from tum_daily_assistant.models import (
    BagGroup,
    ClassifiedEvent,
    Event,
    ExistingReminder,
    Forecast,
    HourlyForecast,
    Message,
    ReminderOp,
    WeatherSummary,
    reminder_key,
)

BERLIN = ZoneInfo("Europe/Berlin")


def dt(hour, minute=0, day=20):
    return datetime(2026, 10, day, hour, minute, tzinfo=BERLIN)


def make_event(title="Math", start=None, end=None):
    return Event(
        title=title,
        start=start or dt(9),
        end=end or dt(10, 30),
        calendar="TUMonline",
    )


def make_message(**overrides):
    first = make_event()
    last = make_event("Swimming", dt(18, 30), dt(19, 30))
    fields = dict(
        slot_id="evening",
        date=date(2026, 10, 20),
        day="tomorrow",
        alarm_at=dt(23, day=19),
        first_event=first,
        last_event=last,
        event_count=2,
        wake_with_breakfast=dt(8, 5),
        wake_without_breakfast=dt(8, 20),
        leave_by=dt(8, 40),
        weather=None,
        rain_gear="none",
        rain_reason=None,
        clothing_key=None,
        layers=False,
        bag=(BagGroup("School", ("notebook", "pen")),),
        weather_unavailable=True,
    )
    fields.update(overrides)
    return Message(**fields)


def test_event_defaults_to_timed_event():
    event = make_event()
    assert event.all_day is False
    assert event.start.tzinfo is not None


def test_event_is_frozen():
    event = make_event()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.title = "Other"


def test_event_rejects_naive_datetimes():
    with pytest.raises(ValueError, match="timezone-aware"):
        Event("Math", datetime(2026, 10, 20, 9), dt(10), "cal")


def test_event_rejects_end_before_start():
    with pytest.raises(ValueError, match="end"):
        Event("Math", dt(10), dt(9), "cal")


def test_classified_event_may_be_unmatched():
    classified = ClassifiedEvent(make_event(), None, None, ())
    assert classified.type_id is None
    assert classified.items == ()


def test_classified_event_holds_items_tuple():
    classified = ClassifiedEvent(make_event(), "lecture", "School", ("pen", "laptop"))
    assert classified.group == "School"
    assert classified.items == ("pen", "laptop")


def test_hourly_forecast_requires_aware_time():
    HourlyForecast(dt(9), 12.5, 40, 0.2, 15.0)
    with pytest.raises(ValueError, match="timezone-aware"):
        HourlyForecast(datetime(2026, 10, 20, 9), 12.5, 40, 0.2, 15.0)


def test_forecast_is_frozen_and_aware():
    hours = (HourlyForecast(dt(9), 12.5, 40, 0.2, 15.0),)
    forecast = Forecast(fetched_at=dt(7), hours=hours)
    assert forecast.hours == hours
    with pytest.raises(dataclasses.FrozenInstanceError):
        forecast.hours = ()
    with pytest.raises(ValueError, match="timezone-aware"):
        Forecast(datetime(2026, 10, 20, 7), hours)


def test_reminder_key_format():
    assert reminder_key(date(2026, 10, 20), "evening") == "tda://2026-10-20/evening"


def test_message_key_matches_reminder_key():
    assert make_message().key == "tda://2026-10-20/evening"


def test_message_defaults_for_flags():
    message = make_message(weather_unavailable=False)
    assert message.stale_forecast is False
    assert message.forecast_fetched_at is None
    assert message.calendar_stale is False
    assert message.calendar_synced_at is None


def test_message_is_frozen_but_replaceable():
    message = make_message()
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.layers = True
    stale = dataclasses.replace(message, calendar_stale=True, calendar_synced_at=dt(7))
    assert stale.calendar_stale is True
    assert message.calendar_stale is False


def test_message_rejects_naive_alarm():
    with pytest.raises(ValueError, match="timezone-aware"):
        make_message(alarm_at=datetime(2026, 10, 19, 23))


def test_message_rejects_unknown_day_and_rain_gear():
    with pytest.raises(ValueError, match="day"):
        make_message(day="yesterday")
    with pytest.raises(ValueError, match="rain_gear"):
        make_message(rain_gear="poncho")


def test_message_with_weather_summary():
    summary = WeatherSummary(
        window_start=dt(8, 40),
        window_end=dt(19, 50),
        temp_min_c=9.0,
        temp_max_c=15.0,
        rain_probability_max=70.0,
        rain_from=dt(14),
        rain_to=dt(17),
        wind_max_kmh=22.0,
        precip_mm_total=3.4,
    )
    message = make_message(
        weather=summary,
        weather_unavailable=False,
        rain_gear="umbrella",
        rain_reason="rain_likely",
        clothing_key="mild",
        layers=False,
    )
    assert message.weather.rain_from == dt(14)
    assert message.rain_gear == "umbrella"


def test_existing_reminder_fields():
    existing = ExistingReminder(
        key="tda://2026-10-20/evening",
        title="t",
        notes="n",
        alarm_at=dt(23, day=19),
        completed=False,
    )
    assert existing.completed is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        existing.title = "x"


def test_reminder_op_create_update_delete():
    create = ReminderOp("create", "tda://2026-10-20/evening", "t", "n", dt(23, day=19))
    update = ReminderOp("update", "tda://2026-10-20/evening", "t2", "n2", dt(23, day=19))
    delete = ReminderOp("delete", "tda://2026-10-20/evening")
    assert (create.kind, update.kind, delete.kind) == ("create", "update", "delete")
    assert delete.title is None and delete.alarm_at is None


def test_reminder_op_validation():
    with pytest.raises(ValueError, match="kind"):
        ReminderOp("rename", "tda://2026-10-20/evening")
    with pytest.raises(ValueError, match="title"):
        ReminderOp("create", "tda://2026-10-20/evening")
    with pytest.raises(ValueError, match="timezone-aware"):
        ReminderOp("create", "k", "t", "n", datetime(2026, 10, 19, 23))


def test_aware_datetimes_in_other_zones_are_accepted():
    utc = datetime(2026, 10, 20, 7, tzinfo=timezone.utc)
    assert Event("x", utc, utc + timedelta(hours=1), "cal").start == utc
