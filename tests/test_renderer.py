"""Tests for the stateless PIL renderer.

All tests run on macOS/Linux without hardware — they verify that render()
returns a 128×128 RGB PIL Image for every display state without crashing.
"""

from __future__ import annotations

import pytest
from PIL import Image

from wlanpi_fpms2.interfaces.screen.renderer import render
from wlanpi_fpms2.state.menu_tree import build_menu_tree
from wlanpi_fpms2.state.models import (
    AlertContent,
    Complication,
    FpmsState,
    HomepageData,
    NavLocation,
    PageContent,
    WlanInterface,
)
from wlanpi_fpms2.state.store import FpmsStateStore


def _tree():
    return build_menu_tree(mode="classic")


def _make_state(**overrides) -> FpmsState:
    store = FpmsStateStore()
    state = store.snapshot()
    return state.model_copy(update=overrides)


def _make_homepage(**kw) -> HomepageData:
    defaults = dict(
        mode="classic",
        hostname="wlanpi",
        primary_ip="192.168.1.1",
        wlan_interfaces=[WlanInterface(name="wlan0")],
        bluetooth_on=False,
        profiler_active=False,
        reachable=True,
        time_str="12:34",
    )
    defaults.update(kw)
    return HomepageData(**defaults)


# ---------------------------------------------------------------------------


class TestRenderReturnsCorrectSize:
    def test_home_state_size(self):
        state = _make_state(homepage=_make_homepage())
        img = render(state, _tree())
        assert isinstance(img, Image.Image)
        assert img.size == (128, 128)
        assert img.mode == "RGB"

    def test_menu_state_size(self):
        state = _make_state(nav=NavLocation(path=[0], display_state="menu"))
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_page_state_size(self):
        page = PageContent(title="Test", lines=["line1", "line2"])
        state = _make_state(
            nav=NavLocation(path=[0], display_state="page"),
            current_page=page,
        )
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_alert_state_size(self):
        page = PageContent(
            title="Error",
            lines=[],
            alert=AlertContent(level="error", message="Something went wrong"),
        )
        state = _make_state(
            nav=NavLocation(path=[0], display_state="page"),
            current_page=page,
        )
        img = render(state, _tree())
        assert img.size == (128, 128)


class TestRenderSleepState:
    def test_sleeping_returns_black_image(self):
        state = _make_state(screen_sleeping=True, homepage=_make_homepage())
        img = render(state, _tree())
        # All pixels should be black
        pixels = list(img.getpixel((x, y)) for y in range(128) for x in range(128))
        assert all(p == (0, 0, 0) for p in pixels)


class TestRenderHomeVariants:
    def test_no_homepage_data_does_not_crash(self):
        state = _make_state(homepage=None)
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_unreachable_globe(self):
        hp = _make_homepage(reachable=False)
        state = _make_state(homepage=hp)
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_bluetooth_on_indicator(self):
        hp = _make_homepage(bluetooth_on=True)
        state = _make_state(homepage=hp)
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_complications_strip_renders(self):
        hp = _make_homepage()
        comp = Complication(
            app_id="io.test.gps",
            label="GPS",
            value="8 sats",
            status="ok",
            updated_at=0,
        )
        state = _make_state(homepage=hp, complications=[comp])
        img = render(state, _tree())
        assert img.size == (128, 128)


class TestRenderMenu:
    def test_top_level_menu(self):
        state = _make_state(nav=NavLocation(path=[0], display_state="menu"))
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_submenu(self):
        # Navigate into "network" (path [0]) → first child
        state = _make_state(nav=NavLocation(path=[0, 0], display_state="menu"))
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_loading_overlay_on_menu(self):
        state = _make_state(
            nav=NavLocation(path=[0], display_state="menu"),
            loading=True,
        )
        img = render(state, _tree())
        assert img.size == (128, 128)


class TestRenderPage:
    def test_many_lines_truncated(self):
        lines = [f"Line {i}" for i in range(20)]
        page = PageContent(title="Long Page", lines=lines)
        state = _make_state(
            nav=NavLocation(path=[0], display_state="page"),
            current_page=page,
        )
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_scroll_offset(self):
        lines = [f"Line {i}" for i in range(20)]
        page = PageContent(title="Scrolled", lines=lines)
        state = _make_state(
            nav=NavLocation(path=[0], display_state="page"),
            current_page=page,
            scroll_index=5,
        )
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_info_alert(self):
        page = PageContent(
            title="Info",
            lines=[],
            alert=AlertContent(level="info", message="For your information"),
        )
        state = _make_state(
            nav=NavLocation(path=[0], display_state="page"),
            current_page=page,
        )
        img = render(state, _tree())
        assert img.size == (128, 128)


class TestRenderOrientation:
    def test_flipped_orientation(self):
        state = _make_state(
            homepage=_make_homepage(),
            display_orientation="flipped",
        )
        img = render(state, _tree())
        assert img.size == (128, 128)

    def test_normal_and_flipped_differ(self):
        hp = _make_homepage(primary_ip="10.0.0.1")
        normal = render(_make_state(homepage=hp, display_orientation="normal"), _tree())
        flipped = render(_make_state(homepage=hp, display_orientation="flipped"), _tree())
        # The two images should not be identical (sample a few pixels)
        assert normal.getpixel((64, 10)) != flipped.getpixel((64, 10)) or \
               normal.getpixel((64, 64)) != flipped.getpixel((64, 64))
