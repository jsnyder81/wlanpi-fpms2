# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

wlanpi-fpms2 is the WLANPi Front Panel Menu System 2 — a rewrite of wlanpi-fpms with a decoupled state/display architecture. A central FastAPI "state service" owns all menu/navigation state; thin clients (OLED screen, Textual TUI, Cockpit web plugin) subscribe to state over WebSocket and post button inputs back. Device data comes from the wlanpi-core REST API.

## Commands

```bash
# Setup (dev extras include pytest, pytest-asyncio, respx)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
pip install -e .[screen]   # SPI/GPIO extras — only needed on a WLANPi device

# Tests (pytest, asyncio_mode=auto — async tests need no decorator)
pytest
pytest tests/test_navigator.py                    # one file
pytest tests/test_navigator.py::test_name         # one test

# Run the state service (HTTP + WS on 127.0.0.1:8765)
python -m wlanpi_fpms2            # or: wlanpi-fpms2  [--host] [--port] [--log-level]

# Clients
wlanpi-fpms2-tui                  # Textual TUI over SSH; arrows navigate, q quits
wlanpi-fpms2-screen               # OLED + GPIO client — device only, runs as root

# Build the Debian package (requires podman; uses dh-virtualenv via Dockerfile.build)
./build-package-native.sh
```

The root-level `test_endpoints.py`, `test_fpms2_menu.py`, and `test_endpoints.sh` are ad-hoc integration scripts run manually on a WLANPi against live services — they are not part of the pytest suite (pytest only collects `tests/`).

Full on-device dev setup (dev copy of wlanpi-core, systemd units, Cockpit symlink) is in `DEVELOPMENT.md`; from-source deployment is in `docs/deployment.md`.

## Architecture

Input/state flow: button press → `POST /input` → `nav/navigator.handle_input()` computes the new nav location and an optional `action_id` → router dispatches the action from the registry → action calls wlanpi-core, writes a `PageContent` into the store → store change is broadcast as a full `FpmsState` snapshot to every WebSocket client, which each render it independently.

- **`wlanpi_fpms2/state/`** — the state service.
  - `store.py`: `FpmsStateStore`, the asyncio-safe single source of truth. Every mutation triggers broadcast via a change callback. Persists display orientation to `/etc/wlanpi-fpms.conf`.
  - `router.py`: HTTP/WS endpoints — `GET /health`, `GET /state`, `GET /menu`, `POST /input`, `WS /ws`, plus `/complications` CRUD for external apps to show status on the homepage. Handles the `loading` flag: inputs are blocked while an action runs, except `left`, which cancels it.
  - `menu_tree.py`: pure-data menu tree (`MenuNode` dict keyed by ID + root list). Built per device mode (read from `/etc/wlanpi-state`). Nav paths are lists of child indices resolved against this tree.
  - `models.py`: all pydantic models (`FpmsState`, `NavLocation`, `PageContent`, `InputEvent`, WS message types).
  - `periodic.py`: background loops — homepage data refresh from wlanpi-core (5 s), complication expiry, profiler notifications.
  - `app.py`: app factory; wires store, broadcaster, menu tree, action registry, core client, and periodic tasks together via lifespan.

- **`wlanpi_fpms2/nav/navigator.py`** — pure, side-effect-free navigation logic: `(state, event, tree) → NavResult`. The router applies the result to the store.

- **`wlanpi_fpms2/actions/`** — `registry.py` maps `action_id` strings (matching menu-tree leaf nodes, e.g. `"network.lldp"`) to async handlers grouped by module (`network`, `system`, `bluetooth`, `utils`, `apps/`). Each handler receives an `ActionContext` (store + core client) and produces `PageContent`. `stubs.py` holds placeholders for wlanpi-core endpoints that don't exist yet.

- **`wlanpi_fpms2/core_client/`** — async httpx client for the wlanpi-core REST API. All requests are HMAC-signed (`hmac_auth.py`) with the shared secret at `/home/wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin`; if the secret is unreadable the service runs degraded without a core client. Response models in `models.py`.

- **`wlanpi_fpms2/interfaces/screen/`** — OLED thin client: WS subscriber + `renderer.py` (stateless `FpmsState + MenuTree → PIL.Image`, ported from original fpms) + display drivers (`luma` or `st7735`, auto-detected from `/etc/wlanpi-model`). `gpio_input.py` runs in a thread and POSTs button events to `/input`.

- **`wlanpi_fpms2/interfaces/tui/`** — Textual client with the same WS-subscribe/POST-input pattern. All clients stay in sync because each just renders the broadcast state.

- **`cockpit/`** — static Cockpit plugin (no build step); polls the state service through the Cockpit bridge. Both Cockpit and browsers cache its JS aggressively — after edits, `sudo systemctl restart cockpit` and hard-refresh (see DEVELOPMENT.md Part 5).

- **`debian/`** — dh-virtualenv packaging; ships systemd units `wlanpi-fpms2.service` (state service, user wlanpi) and `wlanpi-fpms2-screen.service` (screen client, root).

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WLANPI_CORE_BASE_URL` | `http://localhost:31415/api/v1` | wlanpi-core API base URL (dev core runs on `:8000`) |
| `WLANPI_CORE_SECRET_PATH` | `~wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin` | HMAC shared secret |
| `WLANPI_STATE_URL` | `http://127.0.0.1:8765` | State service URL used by screen/TUI clients |
| `WLANPI_SCREEN_DRIVER` | auto-detect | Force `luma` or `st7735` display driver |
| `WLANPI_BUTTON_MAP` | built-in | JSON dict overriding GPIO pin mapping |

## Conventions

- Rendering and navigation are deliberately pure/stateless (`renderer.py`, `navigator.py`, `menu_tree.py`) — keep side effects in the store, router, and actions. No `g_vars`-style shared mutable dicts (that's what fpms1 did).
- Python ≥ 3.9 must be supported (`from __future__ import annotations` for new-style hints; `eval_type_backport` is a runtime dep for pydantic).
