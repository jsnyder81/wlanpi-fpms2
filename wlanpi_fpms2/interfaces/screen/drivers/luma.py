"""Luma-based display driver supporting SSD1351, ST7735, and ST7789.

Ported from wlanpi-fpms/fpms/modules/screen/luma.py — logic unchanged,
only imports adapted for the new package layout.

Display type is read from /etc/wlanpi-model at runtime.
"""

from __future__ import annotations

import logging
import sys

from PIL import Image

from wlanpi_fpms2.interfaces.screen.drivers.screen import AbstractScreen

log = logging.getLogger(__name__)

# Display type constants (mirror wlanpi-fpms convention)
DISPLAY_TYPE_SSD1351 = "ssd1351"
DISPLAY_TYPE_ST7735  = "st7735"
DISPLAY_TYPE_ST7789  = "st7789"

# Platform constants
PLATFORM_PRO = "WLANPi Pro"


def _get_platform() -> str:
    try:
        with open("/etc/wlanpi-model") as f:
            return f.read().strip()
    except Exception:
        return ""


def _get_display_type(platform: str) -> str:
    if platform == PLATFORM_PRO:
        return DISPLAY_TYPE_SSD1351
    return DISPLAY_TYPE_ST7735


def _build_luma_args(display_type: str) -> list[str]:
    args: list[str] = ["-d", display_type]
    if display_type == DISPLAY_TYPE_SSD1351:
        args += ["--interface", "spi", "--width", "128", "--height", "128", "--bgr"]
    elif display_type == DISPLAY_TYPE_ST7735:
        args += [
            "--interface", "gpio_cs_spi",
            "--spi-bus-speed", "2000000",
            "--width", "128", "--height", "128",
            "--gpio-data-command", "25",
            "--gpio-reset", "27",
            "--gpio-backlight", "24",
            "--gpio-chip-select", "8",
            "--backlight-active", "high",
            "--h-offset", "1", "--v-offset", "2",
            "--bgr",
        ]
    elif display_type == DISPLAY_TYPE_ST7789:
        args += [
            "--interface", "gpio_cs_spi",
            "--spi-bus-speed", "52000000",
            "--width", "240", "--height", "240",
            "--gpio-data-command", "25",
            "--gpio-reset", "27",
            "--gpio-backlight", "24",
            "--gpio-chip-select", "8",
            "--backlight-active", "high",
            "--bgr",
        ]
    return args


class Luma(AbstractScreen):
    def init(self) -> bool:
        from luma.core import cmdline

        platform = _get_platform()
        display_type = _get_display_type(platform)
        actual_args = _build_luma_args(display_type)

        parser = cmdline.create_parser(description="wlanpi-fpms2 luma display")
        args = parser.parse_args(actual_args)
        self.device = cmdline.create_device(args)

        if platform == PLATFORM_PRO:
            self.device.contrast(128)

        self._display_width  = self.device.width
        self._display_height = self.device.height
        self._platform = platform
        return True

    def drawImage(self, image: Image.Image) -> None:
        img = image.convert(self.device.mode)
        if img.size != (self._display_width, self._display_height):
            img = img.resize((self._display_width, self._display_height), Image.LANCZOS)
        self.device.display(img)

    def clear(self) -> None:
        self.device.clear()

    def sleep(self) -> None:
        self.device.clear()
        if self._platform != PLATFORM_PRO:
            self.device.backlight(False)

    def wakeup(self) -> None:
        if self._platform != PLATFORM_PRO:
            self.device.backlight(True)
