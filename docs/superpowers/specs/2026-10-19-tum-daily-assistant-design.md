# tum-daily-assistant: Design

## Goal

A local macOS assistant that leaves a short morning and evening reminder in iCloud Reminders.
The reminder answers two questions: "what do I need to take?" and "when do I need to get up
and leave?". Events come from calendar subscriptions that already exist on the Mac (TUMonline
and others), so nobody adds events by hand. Personal data never leaves the machine. Friends
can run the same code on their own Macs and configure it without editing JSON.

## Decisions

| Topic | Decision |
|---|---|
| Runtime | Local Python on the user's Mac. launchd runs it every 30 minutes and on wake. No cloud. |
| Calendar | EventKit (`pyobjc-framework-EventKit`). Default: all calendars and subscriptions, with include/exclude lists in the config. All-day events are ignored. Recurring events arrive already expanded. |
| Delivery | iCloud Reminders: a dedicated list (default "Prep") with absolute alarms. The iPhone fires them on time even while the Mac sleeps. |
| Timing | Fixed-time summaries only, as a configurable list. Default: 08:00 for today, 23:00 for tomorrow. No event-relative messages. |
| Type | Inferred from the event title. Order: title-specific list, keyword (EN/DE/TR, word boundary), optional calendar-to-type fallback, otherwise silence. No special syntax is required in event titles. |
| Bag | No item limit. Items are grouped (School, Sport, ...), deduplicated and in chronological order. |
| Wake and leave | wake = first start - travel - prep - buffer (- breakfast). Both times (with and without breakfast) are always shown. `buffer` defaults to 0. |
| Language | Default English, `language: "tr"` optional. |
| Config | JSON at `~/Library/Application Support/tum-daily-assistant/config.json`, outside the repository. The repository ships `config.example.json`. |
| Settings UI | Local web form (`python -m tum_daily_assistant settings`), standard library only. |
| State | None. The reminder list itself is the state. |

## Message format

One reminder per date and summary slot. The reminder title is the first line, the notes are
the remaining lines.

### Title first

Notifications on the iPhone and Mac truncate the title at roughly 60 to 80 characters. The
first ~60 characters of the title must therefore carry the key information on their own;
the notes carry everything else. Example title:

```
Up 08:05/08:20 · Math 09:00 → Swim 18:30 · Umbrella
```

Title content, in priority order: wake times (with and without breakfast) or the leave time,
the first and last event with their start times, and the rain gear if any. If the title would
exceed the budget, event names are shortened first, never the wake or leave time.

### Notes

```
Wake: 08:05 with breakfast, 08:20 without. Leave by 08:40.
Weather: 9 to 15 °C, 70% rain 14-17. Take an umbrella.
Wear: Layers, light jacket.
Bag (School): calculator, formula sheet, laptop + charger, student card
Bag (Sport): swimsuit, cap, goggles, towel, flip-flops
```

The notes of a "today" summary lead with the leave time instead of the wake times.

### Rules

- **Weather window:** from (first start - travel) to (last end + travel), using hourly values.
- **Umbrella:** any hour in the window with precipitation probability at or above the
  threshold (default 40%). If wind in those hours exceeds the wind threshold (default 40
  km/h), suggest a raincoat instead. One sentence gives the reason.
- **Clothing:** apparent-temperature bands from the config
  (up to 0 / 1-7 / 8-13 / 14-19 / 20 and above). If max minus min exceeds the layer delta
  (default 8 degrees C), add "layers".
- **No events:** no reminder.
- **No weather data:** the weather line says "Weather unavailable".
- **Old forecast:** if the forecast is more than 6 hours older than the alarm, its fetch time
  is shown (for example "forecast 18:30").
- **Parts:** the wake, weather, wear and bag lines can each be switched off with `parts`.
- **Bag:** items come from the event type, title-specific items first. Groups are
  deduplicated and ordered by the first event that needs them.

## Configuration

`config.json` holds only the values that differ from the defaults; they are deep-merged over
`DEFAULT_CONFIG`, and lists are replaced rather than merged. `config.example.json` in the
repository root is identical to the defaults and a test keeps them in sync.

| Key | Meaning |
|---|---|
| `language` | `en` or `tr` |
| `timezone`, `location` | IANA timezone; place name with latitude/longitude for the forecast |
| `reminder_list` | Name of the Reminders list, default `Prep` |
| `summaries` | List of `{id, time "HH:MM", day "today"/"tomorrow"}`; ids are unique |
| `minutes` | `travel`, `prep`, `breakfast`, `buffer` (whole numbers, not negative) |
| `thresholds` | `rain_probability` (0-100), `wind_kmh`, `layer_delta_c` |
| `clothing_bands` | Ascending `max_c` bands with EN/TR text; the last band has `max_c: null` |
| `parts` | Booleans: `wake`, `weather`, `wear`, `bag` |
| `calendars` | `exclude` and `only` name lists; `default_type` maps a calendar name to a type id |
| `types` | Ordered list of `{id, group, enabled, keywords, items: {en, tr}}`; first match wins |
| `title_items` | Extra items for a specific event title |
| `keep_days` | How long old reminders are kept before cleanup |

Default types, in priority order: exam, lecture, swimming, gym, meeting, meal, travel,
appointment. Matching uses case folding, accent normalization (including Turkish i/dotless
i) and word boundaries.

Validation reports every problem at once (bad `HH:MM` times, negative minutes, unknown
language, latitude/longitude range, duplicate ids, unknown summary day, thresholds out of
range, and so on). Saving validates first, writes atomically (temporary file and rename) and
keeps the previous file as `config.json.bak`.

## Architecture

```
tum_daily_assistant/
  __init__.py        __version__
  __main__.py        CLI: run | discover | preview | settings  (+ --dry-run, --version)
  paths.py           Application Support and Logs paths (TDA_HOME override for tests)
  config.py          defaults, merge, validate, atomic write
  models.py          Event, ClassifiedEvent, HourlyForecast, Message, ExistingReminder, ReminderOp
  classify.py        PURE: title + calendar -> type, group, items
  compose.py         PURE: (day events, forecast, config, slot) -> Message
  render.py          PURE: EN/TR templates -> (title, notes)
  reconcile.py       PURE: desired messages + existing reminders + now -> ops
  weather.py         Open-Meteo (urllib) + weather.json cache (up to 12 h)
  eventkit_store.py  EKEventStore and permission requests (calendars, reminders)
  calendar_source.py EventKit -> list[Event] (today + tomorrow, filtered)
  reminders.py       list/create/update/delete reminders keyed by URL "tda://<date>/<slot-id>"
  settings_server.py local settings form
```

Pure modules never import EventKit, so the test suite runs on Linux CI. EventKit modules
import their dependencies lazily.

### Run flow

1. Load and validate the config.
2. Read the calendar.
3. Fetch the forecast, falling back to the cache.
4. Build a message for every future (date x slot).
5. Reconcile against the reminder list:
   - new message: create
   - changed content: update
   - message no longer exists (event cancelled): delete
   - completed reminders and past alarms: leave untouched
   - older than `keep_days`: delete

The identity of a reminder is its URL field, `tda://<date>/<slot-id>`. There is no state
file.

## Failure handling

- **Invalid config:** change nothing and show a macOS notification.
- **Calendar read fails:** prefix future reminder titles with "calendar not refreshed since
  HH:MM". Wrong times from stale data are never shown silently.
- **Weather fails:** use the cache, otherwise write "Weather unavailable".

Logs go to `~/Library/Logs/tum-daily-assistant.log` and contain counts and errors only,
never event titles.

## Privacy and sharing

- The only outbound request goes to Open-Meteo and carries coordinates only.
- The repository holds no secrets: no keys or tokens are needed, and config, cache and logs
  live outside the repository.
- `.gitignore` covers `.venv/`, `config.json`, `*.log` and `.env*`.
- The settings server listens on 127.0.0.1 only, on a random port; the URL carries a random
  token that is checked on every POST; the `Host` header is checked against DNS rebinding;
  input is validated before saving.

## Install

`./install.sh`:

1. Checks for Python 3.11 or newer.
2. Creates `.venv` and installs `requirements.txt`.
3. Copies `config.example.json` if no config exists yet.
4. Renders `launchd/agent.plist.template` into
   `~/Library/LaunchAgents/io.github.anilaladag.tum-daily-assistant.plist`
   (`StartInterval` 1800, `RunAtLoad`).
5. Loads the agent with `launchctl bootstrap gui/$UID`.
6. Runs `discover`, which triggers the calendar and reminders permission prompts.

`./uninstall.sh` removes the agent.

## Known platform behavior

- A reminder with an alarm also shows up as a grey box in the Calendar app. Users can untick
  the Reminders list in Calendar to hide those boxes.
- The alarm time behaves like a due date: once it has passed, the reminder is shown in red
  in the Today view until it is completed.

## Git workflow and versioning

- `master` holds releases only; `develop` is the main development branch.
- Work happens on `feature/<name>` and `bugfix/<name>` branches from `develop` and returns
  via pull request with green CI. `release/X.Y.Z` carries the version and changelog bump;
  `hotfix/<name>` branches from `master`.
- Commits are short, single-line Conventional Commits. SemVer follows them: `feat` is a
  minor, `fix` a patch, `feat!` a major.
- `__version__` in `tum_daily_assistant/__init__.py` is the single source of the version.
  `CHANGELOG.md` follows Keep a Changelog.
- CI runs `pytest` on Ubuntu for every push and pull request.
- Roadmap: 0.1.0 works end to end on the author's Mac; 0.2.0 adds the settings UI and README
  so friends can install it; 1.0.0 follows after a period of smooth use.

## Non-goals (v1)

- "One hour before" messages and event-relative timing.
- Gap suggestions (home or library between events).
- Items parsed from event notes.
- Travel time derived from event locations.
- A menu bar app.
