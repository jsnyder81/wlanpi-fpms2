"""Tests for GPIO input button-map detection and per-pin acquisition."""

import builtins
import subprocess

import pytest

from wlanpi_fpms2.interfaces.screen import gpio_input
from wlanpi_fpms2.interfaces.screen.gpio_input import (
    _BUTTONS_PRO,
    _BUTTONS_WAVESHARE,
    _PinAcquirer,
    _detect_button_map,
    _read_model,
)


# ---------------------------------------------------------------------------
# Button map detection
# ---------------------------------------------------------------------------

class TestDetectButtonMap:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("WLANPI_BUTTON_MAP", '{"up": 1, "down": 2}')
        assert _detect_button_map() == {"up": 1, "down": 2}

    def test_env_override_invalid_json_ignored(self, monkeypatch):
        monkeypatch.setenv("WLANPI_BUTTON_MAP", "not-json")
        monkeypatch.setattr(gpio_input, "_read_model", lambda: "WLAN Pi M4+")
        assert _detect_button_map() == _BUTTONS_WAVESHARE

    @pytest.mark.parametrize("model", ["WLAN Pi Pro", "Pro", "WLANPi Pro"])
    def test_pro_model_selects_pro_map(self, monkeypatch, model):
        monkeypatch.delenv("WLANPI_BUTTON_MAP", raising=False)
        monkeypatch.setattr(gpio_input, "_read_model", lambda: model)
        assert _detect_button_map() == _BUTTONS_PRO

    @pytest.mark.parametrize("model", ["WLAN Pi M4+", "WLAN Pi M4", "R4", ""])
    def test_other_models_select_waveshare_map(self, monkeypatch, model):
        monkeypatch.delenv("WLANPI_BUTTON_MAP", raising=False)
        monkeypatch.setattr(gpio_input, "_read_model", lambda: model)
        assert _detect_button_map() == _BUTTONS_WAVESHARE


class TestReadModel:
    def test_reads_etc_wlanpi_model(self, monkeypatch, tmp_path):
        model_file = tmp_path / "wlanpi-model"
        model_file.write_text("WLAN Pi M4+\n")
        real_open = builtins.open
        monkeypatch.setattr(
            builtins, "open",
            lambda path, *a, **kw: real_open(
                model_file if path == "/etc/wlanpi-model" else path, *a, **kw),
        )
        assert _read_model() == "WLAN Pi M4+"

    def test_falls_back_to_cli(self, monkeypatch):
        def raise_oserror(path, *a, **kw):
            raise OSError("missing")
        monkeypatch.setattr(builtins, "open", raise_oserror)
        monkeypatch.setattr(
            subprocess, "check_output", lambda *a, **kw: b"M4+\n")
        assert _read_model() == "M4+"

    def test_returns_empty_when_all_fail(self, monkeypatch):
        def raise_oserror(path, *a, **kw):
            raise OSError("missing")
        def raise_cli(*a, **kw):
            raise FileNotFoundError("wlanpi-model not installed")
        monkeypatch.setattr(builtins, "open", raise_oserror)
        monkeypatch.setattr(subprocess, "check_output", raise_cli)
        assert _read_model() == ""


# ---------------------------------------------------------------------------
# Per-pin acquisition with retry
# ---------------------------------------------------------------------------

class TestPinAcquirer:
    PINS = [5, 6, 26]
    NAMES = {5: "left", 6: "up", 26: "right"}

    def test_busy_pin_skipped_others_acquired(self):
        acquired = []

        def acquire(pin):
            if pin == 26:
                raise OSError(16, "Device or resource busy")
            acquired.append(pin)

        acq = _PinAcquirer(self.PINS, self.NAMES, acquire)
        assert acquired == [5, 6]
        assert acq.active == 2
        assert acq._pending == [26]

    def test_all_pins_acquired(self):
        acq = _PinAcquirer(self.PINS, self.NAMES, lambda pin: None)
        assert acq.active == 3
        assert acq._pending == []

    def test_retry_acquires_freed_pin(self, monkeypatch):
        busy = {26}

        def acquire(pin):
            if pin in busy:
                raise OSError(16, "Device or resource busy")

        acq = _PinAcquirer(self.PINS, self.NAMES, acquire)
        assert acq.active == 2

        # Not yet due: nothing happens
        acq.retry_pending()
        assert acq.active == 2

        # Pin freed and retry interval elapsed
        busy.clear()
        monkeypatch.setattr(
            gpio_input.time, "monotonic",
            lambda: acq._next_retry + 1)
        acq.retry_pending()
        assert acq.active == 3
        assert acq._pending == []

    def test_retry_keeps_still_busy_pin_pending(self, monkeypatch):
        def acquire(pin):
            if pin == 26:
                raise OSError(16, "Device or resource busy")

        acq = _PinAcquirer(self.PINS, self.NAMES, acquire)
        monkeypatch.setattr(
            gpio_input.time, "monotonic",
            lambda: acq._next_retry + 1)
        acq.retry_pending()
        assert acq.active == 2
        assert acq._pending == [26]
