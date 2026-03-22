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
from datetime import timedelta
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
# Async gpiod listener
# ---------------------------------------------------------------------------


async def run_gpio_input_loop(
    state_service_url: str = "http://127.0.0.1:8765",
    chip: str = "/dev/gpiochip0",
) -> None:
    """Blocking coroutine that reads GPIO edges and POSTs to /input."""
    button_map = _detect_button_map()
    input_url  = f"{state_service_url}/input"

    try:
        import gpiod
    except ImportError:
        log.error("gpiod not available — GPIO button input disabled")
        return

    # Build inverse mapping: pin → name
    pin_to_name = {pin: name for name, pin in button_map.items()}
    pins = list(pin_to_name.keys())

    log.info("GPIO input: monitoring %d buttons on %s: %s",
             len(pins), chip, button_map)

    # Try gpiod 2.x API first, fall back to 1.x
    try:
        _run_gpiod_v2(chip, pins, pin_to_name, input_url)
    except (AttributeError, ImportError):
        log.info("gpiod v2 API not available, trying v1")
        try:
            _run_gpiod_v1(chip, pins, pin_to_name, input_url)
        except Exception as exc:
            log.error("GPIO v1 input loop failed: %s", exc)
    except Exception as exc:
        log.error("GPIO v2 input loop failed: %s", exc, exc_info=True)


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
    input_url: str,
) -> None:
    """gpiod >= 2.0 API — matches original wlanpi-fpms button loop."""
    import gpiod
    from gpiod.line import Direction, Edge, Bias

    line_settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.FALLING,
        bias=Bias.PULL_UP,
        debounce_period=timedelta(microseconds=10),
    )
    request_config = {pin: line_settings for pin in pins}

    with gpiod.request_lines(chip, config=request_config,
                              consumer="wlanpi-fpms2") as req:
        log.info("GPIO input loop running (gpiod v2) on %s", chip)
        while True:
            # wait_edge_events blocks up to 1 s, then read whatever arrived
            if req.wait_edge_events(timedelta(seconds=1)):
                for event in req.read_edge_events():
                    name = pin_to_name.get(event.line_offset)
                    if name:
                        log.debug("Button press: %s (pin %d)",
                                  name, event.line_offset)
                        _post_input_sync(input_url, name)


def _run_gpiod_v1(
    chip: str,
    pins: list[int],
    pin_to_name: dict[int, str],
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

    log.info("GPIO input loop running (gpiod v1) on %s", chip)
    while True:
        if lines.event_wait(sec=1):
            for event in lines.event_read_multiple():
                name = pin_to_name.get(event.source.offset())
                if name:
                    log.debug("Button press: %s", name)
                    _post_input_sync(input_url, name)
