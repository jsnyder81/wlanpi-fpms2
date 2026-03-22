"""Screen thin client.

Connects to the wlanpi-fpms2 state service WebSocket, receives FpmsState
updates, renders each state to a PIL.Image via renderer.py, and sends the
image to the OLED display.

Also spawns a background thread to read GPIO button events and POST them
to the state service /input endpoint.

Entry point: ``wlanpi-fpms2-screen`` (defined in pyproject.toml).

Usage::

    # Auto-detect display driver (reads /etc/wlanpi-model):
    wlanpi-fpms2-screen

    # Force a specific driver:
    WLANPI_SCREEN_DRIVER=st7735 wlanpi-fpms2-screen

Environment variables:
  WLANPI_STATE_URL    Base URL of state service (default: http://127.0.0.1:8765)
  WLANPI_SCREEN_DRIVER  "luma" | "st7735" (default: auto-detect)
  WLANPI_BUTTON_MAP   JSON dict overriding GPIO pin mapping
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time
from typing import TYPE_CHECKING

import httpx

from wlanpi_fpms2.state.menu_tree import MenuTree, build_menu_tree
from wlanpi_fpms2.state.models import FpmsState

log = logging.getLogger(__name__)

_DEFAULT_STATE_URL = "http://127.0.0.1:8765"
_RECONNECT_DELAY   = 2.0   # seconds to wait before reconnecting
_SLEEP_TIMEOUT     = 300   # seconds of inactivity before display sleeps


# ---------------------------------------------------------------------------
# Driver factory
# ---------------------------------------------------------------------------


def _create_screen():
    """Return an initialised AbstractScreen based on platform or env override."""
    driver_env = os.environ.get("WLANPI_SCREEN_DRIVER", "").lower()

    if driver_env == "st7735":
        from wlanpi_fpms2.interfaces.screen.drivers.st7735 import ST7735
        drv = ST7735()
    elif driver_env == "luma":
        from wlanpi_fpms2.interfaces.screen.drivers.luma import Luma
        drv = Luma()
    else:
        # Auto-detect from /etc/wlanpi-model
        try:
            platform = open("/etc/wlanpi-model").read().strip()
        except Exception:
            platform = ""

        if platform == "WLANPi Pro":
            from wlanpi_fpms2.interfaces.screen.drivers.luma import Luma
            drv = Luma()
        else:
            from wlanpi_fpms2.interfaces.screen.drivers.st7735 import ST7735
            drv = ST7735()

    drv.init()
    log.info("Display driver initialised: %s", type(drv).__name__)
    return drv


# ---------------------------------------------------------------------------
# Menu tree fetcher
# ---------------------------------------------------------------------------


def _fetch_menu_tree(base_url: str) -> MenuTree:
    """Fetch current state + menu nodes from state service and build a MenuTree."""
    try:
        with httpx.Client(timeout=5.0) as client:
            state_resp = client.get(f"{base_url}/state")
            state_resp.raise_for_status()
            state_data = state_resp.json()
            mode = (state_data.get("homepage") or {}).get("mode", "classic")

            menu_resp = client.get(f"{base_url}/menu")
            menu_resp.raise_for_status()
            nodes_data = menu_resp.json()

        # Build a local MenuTree from the fetched nodes.
        # The server returns the flat node index; we can reconstruct roots from it.
        from wlanpi_fpms2.state.models import MenuNode
        index: dict[str, MenuNode] = {}
        for n in nodes_data:
            node = MenuNode.model_validate(n)
            index[node.id] = node

        # Roots = nodes not referenced as children of any other node
        all_child_ids: set[str] = set()
        for node in index.values():
            all_child_ids.update(node.children)
        root_ids = [nid for nid in index if nid not in all_child_ids]

        # Preserve the order that build_menu_tree() would produce by using a
        # locally-built tree for roots, then merging the server's index on top.
        local_tree = build_menu_tree(mode=mode)
        # Replace local index with server's to stay in sync (server may have
        # dynamic children such as timezone subtrees)
        for nid, node in index.items():
            local_tree.index[nid] = node

        log.info("Menu tree loaded: %d nodes, mode=%s", len(local_tree.index), mode)
        return local_tree

    except Exception as exc:
        log.warning("Could not fetch menu tree: %s — using local build_menu_tree()", exc)
        return build_menu_tree()


# ---------------------------------------------------------------------------
# Main WebSocket loop
# ---------------------------------------------------------------------------


async def _ws_loop(screen, state_url: str) -> None:
    from websockets.asyncio.client import connect
    from wlanpi_fpms2.interfaces.screen import renderer

    ws_url = state_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    tree   = _fetch_menu_tree(state_url)

    log.info("Connecting to %s", ws_url)

    while True:
        try:
            async with connect(ws_url, ping_interval=20, ping_timeout=30) as ws:
                log.info("WebSocket connected")
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                        # WS messages may be state snapshots or pings
                        if data.get("type") == "ping":
                            continue
                        if data.get("type") == "state":
                            payload = data.get("state", data)
                        else:
                            payload = data

                        state = FpmsState.model_validate(payload)

                        # Rebuild tree if mode changed
                        current_mode = (state.homepage.mode
                                        if state.homepage else "classic")
                        if current_mode != tree.mode:
                            tree = build_menu_tree(mode=current_mode)

                        image = renderer.render(state, tree)
                        screen.drawImage(image)

                    except Exception as exc:
                        log.exception("Error processing WS message: %s", exc)

        except Exception as exc:
            log.warning("WebSocket disconnected: %s — reconnecting in %.0fs",
                        exc, _RECONNECT_DELAY)
            await asyncio.sleep(_RECONNECT_DELAY)
            # Refresh menu tree on reconnect
            tree = _fetch_menu_tree(state_url)


# ---------------------------------------------------------------------------
# GPIO thread
# ---------------------------------------------------------------------------


def _start_gpio_thread(state_url: str) -> None:
    """Start the GPIO input loop in a daemon thread."""
    from wlanpi_fpms2.interfaces.screen.gpio_input import run_gpio_input_loop

    def _target():
        try:
            asyncio.run(run_gpio_input_loop(state_service_url=state_url))
        except Exception as exc:
            log.error("GPIO input thread exited unexpectedly: %s", exc, exc_info=True)

    t = threading.Thread(target=_target, name="gpio-input", daemon=True)
    t.start()
    log.info("GPIO input thread started")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    state_url = os.environ.get("WLANPI_STATE_URL", _DEFAULT_STATE_URL)

    # Wait for state service to be ready (systemd ordering should handle this,
    # but add a quick retry loop just in case)
    for attempt in range(10):
        try:
            with httpx.Client(timeout=2.0) as c:
                c.get(f"{state_url}/health").raise_for_status()
            break
        except Exception:
            if attempt < 9:
                log.info("State service not ready, retrying in 2s…")
                time.sleep(2)
            else:
                log.error("State service unreachable after 10 attempts — exiting")
                sys.exit(1)

    screen = _create_screen()

    # Start GPIO input in background thread
    _start_gpio_thread(state_url)

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.new_event_loop()

    def _shutdown(*_):
        log.info("Shutting down screen client")
        screen.sleep()
        loop.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown)

    try:
        loop.run_until_complete(_ws_loop(screen, state_url))
    finally:
        screen.sleep()
        loop.close()


if __name__ == "__main__":
    main()
