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
    """Return the action dispatch table (Phase 2: real implementations)."""
    from wlanpi_fpms2.actions.registry import build_action_registry
    return build_action_registry()


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


def _create_core_client():
    """Create a CoreApiClient if the shared secret is readable, else return None."""
    import os
    from wlanpi_fpms2.core_client.client import CoreApiClient
    from wlanpi_fpms2.core_client.hmac_auth import _DEFAULT_SECRET_PATH

    secret_env = os.environ.get("WLANPI_CORE_SECRET_PATH")
    secret_path = _DEFAULT_SECRET_PATH if not secret_env else __import__("pathlib").Path(secret_env)

    if not secret_path.exists():
        log.warning("wlanpi-core secret not found at %s — running without core_client", secret_path)
        return None
    try:
        secret = secret_path.read_bytes()
        base_url = os.environ.get("WLANPI_CORE_BASE_URL", "http://localhost/api/v1")
        return CoreApiClient(base_url=base_url, secret=secret)
    except Exception as exc:
        log.warning("Could not create CoreApiClient: %s — running without core_client", exc)
        return None


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

    # Create wlanpi-core API client (graceful degradation if not available)
    core_client = _create_core_client()

    # Attach to app state
    app.state.store = store
    app.state.broadcaster = broadcaster
    app.state.menu_tree = menu_tree
    app.state.timezones = timezones
    app.state.action_registry = action_registry
    app.state.core_client = core_client

    # Launch background tasks
    tasks = [
        asyncio.create_task(broadcaster.ping_loop()),
        asyncio.create_task(expire_complications_loop(store)),
        asyncio.create_task(homepage_refresh_loop(store, core_client, app)),
    ]

    log.info("fpms2 state service started (mode=%s, core_client=%s)",
             mode, "connected" if core_client else "unavailable")
    yield

    # --- Shutdown ---
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if core_client:
        await core_client.close()
    log.info("fpms2 state service stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="wlanpi-fpms2 State Service",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.include_router(router)
    return app
