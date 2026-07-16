"""GPIO button input handler.

Reads hardware button presses via gpiod (libgpiod) and POSTs the
corresponding InputEvent to the state service.

Button GPIO pin mappings match wlanpi-fpms constants.py:
  - WLAN Pi Pro : up=22, down=5, left=17, right=27, center=6
  - Waveshare   : up=6, down=19, left=5, right=26, center=13,
                  key1=21, key2=20, key3=16

The platform is auto-detected from /etc/wlanpi-model, falling back to the
``wlanpi-model -b`` CLI (matching original fpms behaviour).  The environment
variable WLANPI_BUTTON_MAP overrides with a JSON dict of {name: pin}.

Robustness: each line is requested individually so a pin held by another
consumer (e.g. a device-tree overlay) only disables that one button; busy
pins are retried periodically, and the whole loop restarts on unexpected
errors instead of dying silently.
"""

from __future__ import annotations

import json
import logging
import os
import selectors
import subprocess
import time
from datetime import timedelta

import httpx

log = logging.getLogger(__name__)

# Seconds between attempts to re-acquire busy pins / restart a failed loop
_RETRY_INTERVAL = 30.0

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


def _read_model() -> str:
    """Read the device model from /etc/wlanpi-model, else the wlanpi-model CLI."""
    try:
        return open("/etc/wlanpi-model").read().strip()
    except OSError:
        pass
    try:
        return subprocess.check_output(
            ["wlanpi-model", "-b"], timeout=10
        ).decode().strip()
    except Exception:
        return ""


def _detect_button_map() -> dict[str, int]:
    env_override = os.environ.get("WLANPI_BUTTON_MAP")
    if env_override:
        try:
            return json.loads(env_override)
        except Exception:
            log.warning("WLANPI_BUTTON_MAP is not valid JSON; ignoring")

    model = _read_model()
    # fpms1 platform string is "WLAN Pi Pro"; brief output is "Pro"
    if "pro" in model.lower():
        return _BUTTONS_PRO
    return _BUTTONS_WAVESHARE


# ---------------------------------------------------------------------------
# Input loop
# ---------------------------------------------------------------------------


async def run_gpio_input_loop(
    state_service_url: str = "http://127.0.0.1:8765",
    chip: str = "/dev/gpiochip0",
) -> None:
    """Blocking coroutine that reads GPIO edges and POSTs to /input."""
    button_map = _detect_button_map()
    input_url  = f"{state_service_url}/input"

    try:
        import gpiod  # noqa: F401
    except ImportError:
        log.error("gpiod not available — GPIO button input disabled")
        return

    # Build inverse mapping: pin → name
    pin_to_name = {pin: name for name, pin in button_map.items()}
    pins = list(pin_to_name.keys())

    log.info("GPIO input: monitoring %d buttons on %s: %s",
             len(pins), chip, button_map)

    while True:
        # Try gpiod 2.x API first, fall back to 1.x
        try:
            _run_gpiod_v2(chip, pins, pin_to_name, input_url)
        except (AttributeError, ImportError):
            log.info("gpiod v2 API not available, trying v1")
            try:
                _run_gpiod_v1(chip, pins, pin_to_name, input_url)
            except Exception as exc:
                log.error("GPIO v1 input loop failed: %s — retrying in %ds",
                          exc, _RETRY_INTERVAL)
        except Exception as exc:
            log.error("GPIO v2 input loop failed: %s — retrying in %ds",
                      exc, _RETRY_INTERVAL, exc_info=True)
        time.sleep(_RETRY_INTERVAL)


def _post_input_sync(url: str, button: str) -> None:
    """Synchronous HTTP POST (called from blocking thread)."""
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.post(url, json={"button": button})
            if r.status_code not in (200, 202):
                log.warning("POST /input %s → %s", button, r.status_code)
    except Exception as exc:
        log.warning("POST /input %s failed: %s", button, exc)


class _PinAcquirer:
    """Tracks which pins are acquired; retries busy ones periodically.

    ``acquire(pin)`` must request the line and register it for event polling,
    returning True on success.  Failures are logged once per pin (not on
    every retry) so a permanently-held pin doesn't spam the journal.
    """

    def __init__(self, pins: list[int], pin_to_name: dict[int, str], acquire) -> None:
        self._acquire = acquire
        self._pin_to_name = pin_to_name
        self._pending: list[int] = []
        self._warned: set[int] = set()
        self._next_retry = time.monotonic() + _RETRY_INTERVAL
        for pin in pins:
            self._try(pin)
        self.active = len(pins) - len(self._pending)

    def _try(self, pin: int) -> bool:
        try:
            self._acquire(pin)
            if pin in self._warned:
                log.info("GPIO pin %d (%s) acquired on retry",
                         pin, self._pin_to_name[pin])
                self._warned.discard(pin)
            return True
        except OSError as exc:
            if pin not in self._warned:
                log.warning(
                    "GPIO pin %d (%s) unavailable: %s — button disabled, "
                    "will retry every %ds",
                    pin, self._pin_to_name[pin], exc, _RETRY_INTERVAL)
                self._warned.add(pin)
            self._pending.append(pin)
            return False

    def retry_pending(self) -> None:
        if not self._pending or time.monotonic() < self._next_retry:
            return
        pending, self._pending = self._pending, []
        for pin in pending:
            if self._try(pin):
                self.active += 1
        self._next_retry = time.monotonic() + _RETRY_INTERVAL


def _run_gpiod_v2(
    chip: str,
    pins: list[int],
    pin_to_name: dict[int, str],
    input_url: str,
) -> None:
    """gpiod >= 2.0 API.  One request per pin so a busy line only loses
    that button instead of failing the whole batch."""
    import gpiod
    from gpiod.line import Direction, Edge, Bias

    line_settings = gpiod.LineSettings(
        direction=Direction.INPUT,
        edge_detection=Edge.FALLING,
        bias=Bias.PULL_UP,
        debounce_period=timedelta(microseconds=10),
    )

    sel = selectors.DefaultSelector()

    def acquire(pin: int) -> None:
        req = gpiod.request_lines(chip, config={pin: line_settings},
                                  consumer="wlanpi-fpms2")
        sel.register(req.fd, selectors.EVENT_READ, req)

    try:
        acquirer = _PinAcquirer(pins, pin_to_name, acquire)
        log.info("GPIO input loop running (gpiod v2) on %s: %d/%d buttons active",
                 chip, acquirer.active, len(pins))

        while True:
            for key, _ in sel.select(timeout=1.0):
                req = key.data
                for event in req.read_edge_events():
                    name = pin_to_name.get(event.line_offset)
                    if name:
                        log.debug("Button press: %s (pin %d)",
                                  name, event.line_offset)
                        _post_input_sync(input_url, name)
            acquirer.retry_pending()
    finally:
        for key in list(sel.get_map().values()):
            try:
                key.data.release()
            except Exception:
                pass
        sel.close()


def _run_gpiod_v1(
    chip: str,
    pins: list[int],
    pin_to_name: dict[int, str],
    input_url: str,
) -> None:
    """gpiod 1.x API (legacy) — same per-pin acquisition strategy."""
    import gpiod

    chip_obj = gpiod.Chip(chip)
    sel = selectors.DefaultSelector()

    def acquire(pin: int) -> None:
        line = chip_obj.get_line(pin)
        line.request(
            consumer="wlanpi-fpms2",
            type=gpiod.LINE_REQ_EV_FALLING_EDGE,
            flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP,
        )
        sel.register(line.event_get_fd(), selectors.EVENT_READ, line)

    try:
        acquirer = _PinAcquirer(pins, pin_to_name, acquire)
        log.info("GPIO input loop running (gpiod v1) on %s: %d/%d buttons active",
                 chip, acquirer.active, len(pins))

        while True:
            for key, _ in sel.select(timeout=1.0):
                line = key.data
                event = line.event_read()
                name = pin_to_name.get(event.source.offset())
                if name:
                    log.debug("Button press: %s", name)
                    _post_input_sync(input_url, name)
            acquirer.retry_pending()
    finally:
        for key in list(sel.get_map().values()):
            try:
                key.data.release()
            except Exception:
                pass
        sel.close()
        chip_obj.close()
