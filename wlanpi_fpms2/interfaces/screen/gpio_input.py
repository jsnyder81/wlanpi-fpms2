"""GPIO button input handler.

Reads hardware button presses via gpiod (libgpiod) and POSTs the
corresponding InputEvent to the state service.

Button GPIO pin mappings match wlanpi-fpms constants.py:
  - WLANPi Pro : up=22, down=5, left=17, right=27, center=6
  - Waveshare  : up=6, down=19, left=5, right=26, center=13,
                 key1=21, key2=20, key3=16

The platform is auto-detected from /etc/wlanpi-model.  The environment
variable WLANPI_BUTTON_MAP overrides with a JSON dict of {name: pin}.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Button pin maps
# ---------------------------------------------------------------------------

_BUTTONS_PRO: dict[str, int] = {
    "up":     22,
    "down":    5,
    "left":   17,
    "right":  27,
    "center":  6,
}

_BUTTONS_WAVESHARE: dict[str, int] = {
    "up":     6,
    "down":  19,
    "left":   5,
    "right": 26,
    "center": 13,
    "key1":  21,
    "key2":  20,
    "key3":  16,
}


def _detect_button_map() -> dict[str, int]:
    env_override = os.environ.get("WLANPI_BUTTON_MAP")
    if env_override:
        try:
            return json.loads(env_override)
        except Exception:
            log.warning("WLANPI_BUTTON_MAP is not valid JSON; ignoring")

    try:
        platform = open("/etc/wlanpi-model").read().strip()
        if platform == "WLANPi Pro":
            return _BUTTONS_PRO
    except Exception:
        pass
    return _BUTTONS_WAVESHARE


# ---------------------------------------------------------------------------
# Debounce helper
# ---------------------------------------------------------------------------

_DEBOUNCE_MS = 150  # ignore presses within 150ms of the previous one


class _Debouncer:
    def __init__(self, window_ms: int = _DEBOUNCE_MS) -> None:
        self._window = window_ms / 1000.0
        self._last: dict[str, float] = {}

    def accept(self, name: str) -> bool:
        now = time.monotonic()
        last = self._last.get(name, 0.0)
        if now - last < self._window:
            return False
        self._last[name] = now
        return True


# ---------------------------------------------------------------------------
# Async gpiod listener
# ---------------------------------------------------------------------------


async def run_gpio_input_loop(
    state_service_url: str = "http://127.0.0.1:8765",
    chip: str = "gpiochip0",
) -> None:
    """Blocking coroutine that reads GPIO edges and POSTs to /input.

    Must be run in a thread that has a running event loop, or wrapped in
    asyncio.to_thread so the blocking gpiod call doesn't block the loop.
    """
    button_map = _detect_button_map()
    debouncer  = _Debouncer()
    input_url  = f"{state_service_url}/input"

    try:
        import gpiod
    except ImportError:
        log.error("gpiod not available — GPIO button input disabled")
        return

    # Build inverse mapping: pin → name
    pin_to_name = {pin: name for name, pin in button_map.items()}
    pins = list(pin_to_name.keys())

    log.info("GPIO input: monitoring %d buttons on %s", len(pins), chip)

    # gpiod 2.x API
    try:
        _run_gpiod_v2(chip, pins, pin_to_name, debouncer, input_url)
    except AttributeError:
        # Fall back to gpiod 1.x API
        _run_gpiod_v1(chip, pins, pin_to_name, debouncer, input_url)


def _post_input_sync(url: str, button: str) -> None:
    """Synchronous HTTP POST (called from blocking thread)."""
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.post(url, json={"button": button})
            if r.status_code not in (200, 202):
                log.warning("POST /input %s → %s", button, r.status_code)
    except Exception as exc:
        log.warning("POST /input %s failed: %s", button, exc)


def _run_gpiod_v2(
    chip: str,
    pins: list[int],
    pin_to_name: dict[int, str],
    debouncer: _Debouncer,
    input_url: str,
) -> None:
    """gpiod >= 2.0 API."""
    import gpiod
    from gpiod.line import Direction, Edge, Bias

    line_settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.FALLING,
        bias=Bias.PULL_UP,
    )
    request_config = {pin: line_settings for pin in pins}

    with gpiod.request_lines(chip, consumer="wlanpi-fpms2", config=request_config) as req:
        log.info("GPIO input loop running (gpiod v2)")
        while True:
            for event in req.read_edge_events():
                name = pin_to_name.get(event.line_offset)
                if name and debouncer.accept(name):
                    log.debug("Button press: %s (pin %d)", name, event.line_offset)
                    _post_input_sync(input_url, name)


def _run_gpiod_v1(
    chip: str,
    pins: list[int],
    pin_to_name: dict[int, str],
    debouncer: _Debouncer,
    input_url: str,
) -> None:
    """gpiod 1.x API (legacy)."""
    import gpiod

    chip_obj = gpiod.Chip(chip)
    lines = chip_obj.get_lines(pins)
    lines.request(
        consumer="wlanpi-fpms2",
        type=gpiod.LINE_REQ_EV_FALLING_EDGE,
        flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP,
    )

    log.info("GPIO input loop running (gpiod v1)")
    while True:
        if lines.event_wait(sec=1):
            for event in lines.event_read_multiple():
                name = pin_to_name.get(event.source.offset())
                if name and debouncer.accept(name):
                    log.debug("Button press: %s", name)
                    _post_input_sync(input_url, name)
