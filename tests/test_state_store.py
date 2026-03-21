"""Tests for FpmsStateStore."""

import asyncio
import pytest
from wlanpi_fpms2.state.store import FpmsStateStore
from wlanpi_fpms2.state.models import (
    AlertContent,
    ComplicationUpdate,
    HomepageData,
    NavLocation,
    PageContent,
)


@pytest.fixture
def store():
    return FpmsStateStore()


class TestInitialState:
    def test_initial_display_state_is_home(self, store):
        state = store.snapshot()
        assert state.nav.display_state == "home"

    def test_initial_loading_is_false(self, store):
        assert store.snapshot().loading is False

    def test_initial_complications_empty(self, store):
        assert store.snapshot().complications == []


class TestNavigation:
    async def test_apply_nav_updates_state(self, store):
        new_nav = NavLocation(path=[1, 2], display_state="menu")
        await store.apply_nav(new_nav)
        state = store.snapshot()
        assert state.nav.path == [1, 2]
        assert state.nav.display_state == "menu"

    async def test_set_loading(self, store):
        await store.set_loading(True)
        assert store.snapshot().loading is True
        await store.set_loading(False)
        assert store.snapshot().loading is False


class TestPageContent:
    async def test_set_page_clears_loading(self, store):
        await store.set_loading(True)
        page = PageContent(title="Test", lines=["line1"])
        await store.set_page(page)
        state = store.snapshot()
        assert state.loading is False
        assert state.current_page is not None
        assert state.current_page.title == "Test"

    async def test_set_page_updates_display_state(self, store):
        page = PageContent(title="T", lines=[])
        await store.set_page(page)
        assert store.snapshot().nav.display_state == "page"

    async def test_set_page_none_clears_page(self, store):
        await store.set_page(PageContent(title="T", lines=[]))
        await store.set_page(None)
        assert store.snapshot().current_page is None


class TestComplications:
    async def test_upsert_adds_complication(self, store):
        await store.upsert_complication(
            "io.test.gps",
            ComplicationUpdate(label="GPS", value="8 sats", status="ok", ttl_seconds=30),
        )
        state = store.snapshot()
        assert len(state.complications) == 1
        assert state.complications[0].app_id == "io.test.gps"
        assert state.complications[0].value == "8 sats"

    async def test_upsert_updates_existing(self, store):
        await store.upsert_complication(
            "io.test.gps",
            ComplicationUpdate(label="GPS", value="8 sats", status="ok"),
        )
        await store.upsert_complication(
            "io.test.gps",
            ComplicationUpdate(label="GPS", value="NO FIX", status="error"),
        )
        state = store.snapshot()
        assert len(state.complications) == 1
        assert state.complications[0].value == "NO FIX"
        assert state.complications[0].status == "error"

    async def test_remove_complication(self, store):
        await store.upsert_complication(
            "io.test.gps",
            ComplicationUpdate(label="GPS", value="8 sats", status="ok"),
        )
        removed = await store.remove_complication("io.test.gps")
        assert removed is True
        assert store.snapshot().complications == []

    async def test_remove_nonexistent_returns_false(self, store):
        removed = await store.remove_complication("io.test.nonexistent")
        assert removed is False

    async def test_expire_removes_stale_complications(self, store):
        import time
        await store.upsert_complication(
            "io.test.stale",
            ComplicationUpdate(label="X", value="y", status="ok", ttl_seconds=1),
        )
        # Manually age the complication
        comp = store._state.complications[0]
        store._state.complications[0] = comp.model_copy(
            update={"updated_at": time.time() - 2}
        )
        await store.expire_complications()
        assert store.snapshot().complications == []


class TestListeners:
    async def test_listener_called_on_change(self, store):
        calls = []

        async def listener(state):
            calls.append(state)

        store.add_listener(listener)
        await store.set_loading(True)
        # Give the task a chance to run
        await asyncio.sleep(0)
        assert len(calls) >= 1
