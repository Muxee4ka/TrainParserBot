# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Telegram bot (aiogram 3) for searching RZD (Russian Railways) trains and subscribing to seat-availability notifications. Users search origin → destination → date → train through a single, continuously-edited "progress message"; extra messages get cleaned up. Subscriptions are polled periodically and matching seat availability triggers a Telegram notification.

`main.py` at the repo root is an unrelated standalone legacy script (a single-file polling scraper with hardcoded config/tokens) — not part of the bot app and not imported by `bot.py`. Don't wire it into the aiogram app; treat it as a separate artifact.

## Commands

Install deps:
```
python -m pip install -r requirements.txt
```

Run the bot (requires `.env` with at least `BOT_TOKEN`):
```
python bot.py
```

Run unit tests:
```
pytest
```

Run a single test file / test:
```
pytest tests/test_filters.py
pytest tests/test_filters.py::test_name -v
```

Run integration tests (make real requests to the public RZD API, skipped by default):
```
RUN_INTEGRATION_TESTS=1 pytest
```

`setup.py` is a convenience script (not `pip install`-style setup) that installs requirements, scaffolds `.env`, and runs the test suite — `python setup.py`.

CI (`.github/workflows/ci.yml`) installs deps, writes a `.env` from the `BOT_TOKEN` secret, and runs `pytest -q` with integration tests disabled.

## Architecture

- `bot.py` — entry point. Builds the aiogram `Bot`/`Dispatcher`, registers `CommandsHandler` and `SearchHandler` on separate `Router`s, and runs `MonitoringService.start_monitoring()` as a background `asyncio` task alongside polling.
- `config.py` — single `Config` dataclass populated from `.env` via `python-dotenv`, with defaults for API URLs, message/callback-data length limits, and monitoring interval. Imported everywhere as the shared `config` instance.
- `handlers/`
  - `base.py` — `BaseHandler` ABC: every handler takes a `Router`, registers its own routes in `register_handlers()`.
  - `commands.py` — `/start`, `/help`, `/subscriptions`, `/cancel`.
  - `search.py` — the bulk of the bot's logic: the step-by-step search flow (`search_step` state machine: `origin` → `destination` → `date` → `train` → `done`/`editfilters`/`await_price`), the seat-availability + filter panel, and all subscription-related callbacks. One large `SearchHandler` dispatches every `callback_query` through a big `if/elif` on `callback.data` prefix (see `handle_callback`).
- `services/`
  - `rzd_api.py` — `RZDAPIService`: talks to RZD's public `train-pricing` and `suggests` endpoints; extracts/normalizes train info, counts/filters available seats (`match_seats`, `count_seats_breakdown`), builds purchase deep-links.
  - `rzd_seatmap.py` — `SeatMapService` + `TrainSeats` + pure functions for the `CarPricing` endpoint. `SeatMapService.seats()` is the **only** network method: it returns a `TrainSeats` value object and everything else (`places`, `by_berth`, `count`, `describe`) is pure, so one payload answers every question about a train. The four older `*_for_berth` / `empty_compartments*` methods are thin wrappers kept for existing callers. Used for the "expensive" berth filters (`cabin` = fully empty compartment, `pair` = lower+upper free together in the same compartment/block) — these need per-car seat layout, not just aggregate counts, so they're kept out of the normal per-subscription polling loop.
  - `filters.py` — pure presentation logic (no aiogram/network deps) for the subscription filter panel: which car-type/berth options to show for a given train, callback-data encoding (`flt_<kind>_<value>`), and human-readable filter summaries.
  - `notification.py` — `NotificationService`: thin wrapper over the raw Telegram Bot HTTP API (not aiogram's `Bot`) using one reused `aiohttp.ClientSession`; used to send/edit/delete messages from both handlers and monitoring.
  - `monitoring.py` — `MonitoringService`: loop over active subscriptions every `MONITORING_INTERVAL` seconds. Computes a compact per-train state string (`"<train>:<matched_count>"` joined) via `_filtered_state`, diffs it against the last saved state in `subscription_states`, and only notifies when the match count actually changed and seats are currently available. For `cabin`/`pair` berth filters it calls into `rzd_seatmap` (a network call) via `asyncio.to_thread`.
- `database/`
  - `models.py` — `Subscription` and `SearchState` dataclasses (no ORM).
  - `manager.py` — `DatabaseManager`: raw `sqlite3`, one connection per call. Opens/closes a connection per method rather than holding one open. Runs ad-hoc `ALTER TABLE ... ADD COLUMN` migrations on init to add new columns to existing DBs (`search_states.messages_to_delete`, filter columns, etc.) — when adding a new persisted field, follow this pattern rather than introducing a migration framework.

### Key flows to know before touching search.py

- All user-facing search state lives in one SQLite row per user (`search_states`), keyed by `user_id`, including a JSON-encoded `station_options` map (code → name, since callback_data can't fit long station names) and a JSON blob of the selected train's `CarGroups` (`selected_train_cargroups`) so the filter panel can re-render without re-querying RZD.
- The "progress message" pattern: `search_state.progress_message_id` is the one message that gets edited in place as the user moves through steps; anything else sent along the way goes into `messages_to_delete` and is cleaned up via `_delete_user_messages`.
- The filter panel (`_render_filter_panel`) is shared between "new subscription" and "edit existing subscription" (`editing_subscription_id` set) — same rendering code, different submit button/callback (`subscribe_filtered` vs `save_filters`).
- Blocking network calls (`requests` inside `RZDAPIService`/`SeatMapService`) are always pushed off the event loop with `asyncio.to_thread`; don't call them directly from an `async def` handler body.
- Disabled-persons seats are excluded everywhere by default (`Subscription.include_disabled` / `SearchState.filter_include_disabled`, off by default). РЖД returns them as a **whole dedicated `CarGroup`** flagged `HasPlacesForDisabledPersons`, so `RZDAPIService._group_allowed()` drops the group at the aggregate layer — no `CarPricing` call needed. Never re-add an `AvailabilityIndication` check inline; go through the predicate. The invariant "flagged group is entirely disabled seats" is guarded by an integration test in `tests/test_api.py`.
- On the notification path, pass the `seats_cache` dict from `_filtered_state` into `format_availability_message` — it makes the `CarPricing` call happen once per train instead of twice.
- Every `requests` call to РЖД must pass `verify=rzd_verify()` (from `config`). `ticket.rzd.ru` runs on a НУЦ Минцифры certificate that is in neither `certifi` nor the system store, and the server omits the `Russian Trusted Sub CA` intermediate from the handshake — so the bundled `certs/russian_trusted.pem` (root + intermediate) is required or the request dies with `SSLCertVerificationError`. See `certs/README.md`.
