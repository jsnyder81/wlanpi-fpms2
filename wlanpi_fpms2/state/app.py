"""FastAPI application factory for the fpms2 state service."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from wlanpi_fpms2.state.broadcaster import Broadcaster
from wlanpi_fpms2.state.menu_tree import MenuTree, build_menu_tree
from wlanpi_fpms2.state.models import FpmsState
from wlanpi_fpms2.state.periodic import expire_complications_loop, homepage_refresh_loop
from wlanpi_fpms2.state.router import router
from wlanpi_fpms2.state.store import FpmsStateStore

log = logging.getLogger(__name__)


def _load_action_registry() -> dict:
    """Return the action dispatch table.

    In Phase 1 this returns a mostly empty dict with a few stub actions.
    Phase 2 will populate it with real core_client-backed callables.
    """
    from wlanpi_fpms2.actions.stubs import build_stub_registry
    return build_stub_registry()


def _read_device_mode() -> str:
    """Read the current device mode from /etc/wlanpi-state."""
    try:
        with open("/etc/wlanpi-state") as f:
            return f.read().strip() or "classic"
    except OSError:
        return "classic"


def _read_timezones() -> list[dict]:
    """Load timezone list. Returns empty list if not available."""
    import json
    import os
    candidates = [
        "/opt/wlanpi-common/timezones.json",
        "/usr/share/wlanpi-fpms/timezones.json",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return []


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown."""
    # --- Startup ---
    store = FpmsStateStore()
    broadcaster = Broadcaster()
    mode = _read_device_mode()
    timezones = _read_timezones()
    menu_tree = build_menu_tree(mode=mode, timezones=timezones)
    action_registry = _load_action_registry()

    # Wire store → broadcaster
    async def _on_state_change(state: FpmsState) -> None:
        await broadcaster.send_state(state)

    store.add_listener(_on_state_change)

    # Attach to app state
    app.state.store = store
    app.state.broadcaster = broadcaster
    app.state.menu_tree = menu_tree
    app.state.action_registry = action_registry
    app.state.core_client = None  # Phase 2+

    # Launch background tasks
    tasks = [
        asyncio.create_task(broadcaster.ping_loop()),
        asyncio.create_task(expire_complications_loop(store)),
        asyncio.create_task(homepage_refresh_loop(store, app.state.core_client)),
    ]

    log.info("fpms2 state service started (mode=%s)", mode)
    yield

    # --- Shutdown ---
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("fpms2 state service stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="wlanpi-fpms2 State Service",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.include_router(router)
    return app
