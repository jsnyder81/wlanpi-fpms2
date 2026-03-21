"""FpmsStateStore — asyncio-safe single source of truth for fpms2 state."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

from wlanpi_fpms2.state.models import (
    Complication,
    ComplicationUpdate,
    FpmsState,
    HomepageData,
    NavLocation,
    PageContent,
)


class FpmsStateStore:
    """Thread-safe state container.

    All mutating methods acquire the internal lock and then call
    ``_on_change`` so the broadcaster can push an updated snapshot.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state = FpmsState()
        # Registered change listeners (async callables)
        self._listeners: list[Callable[[FpmsState], Coroutine[Any, Any, None]]] = []
        # Active action task (for cancellation on back button)
        self._action_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    def add_listener(
        self, fn: Callable[[FpmsState], Coroutine[Any, Any, None]]
    ) -> None:
        """Register an async callable that is called on every state change."""
        self._listeners.append(fn)

    async def _notify(self) -> None:
        snapshot = self.snapshot()
        for fn in self._listeners:
            asyncio.create_task(fn(snapshot))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def snapshot(self) -> FpmsState:
        """Return a deep copy of the current state (safe to share)."""
        return self._state.model_copy(deep=True)

    # ------------------------------------------------------------------
    # Navigation mutations
    # ------------------------------------------------------------------

    async def apply_nav(self, new_nav: NavLocation) -> None:
        async with self._lock:
            self._state.nav = new_nav
            self._state.last_input_at = time.time()
        await self._notify()

    async def set_loading(self, loading: bool) -> None:
        async with self._lock:
            self._state.loading = loading
        await self._notify()

    async def set_page(self, page: PageContent | None) -> None:
        async with self._lock:
            self._state.current_page = page
            self._state.loading = False
            if page is not None:
                self._state.nav.display_state = "page"
        await self._notify()

    async def set_scroll(self, index: int, max_index: int) -> None:
        async with self._lock:
            self._state.scroll_index = index
            self._state.scroll_max = max_index
        await self._notify()

    async def set_homepage(self, data: HomepageData) -> None:
        async with self._lock:
            self._state.homepage = data
        await self._notify()

    async def set_screen_sleeping(self, sleeping: bool) -> None:
        async with self._lock:
            self._state.screen_sleeping = sleeping
        await self._notify()

    async def set_orientation(self, orientation: str) -> None:
        async with self._lock:
            self._state.display_orientation = orientation  # type: ignore[assignment]
        await self._notify()

    async def set_shutdown(self, in_progress: bool) -> None:
        async with self._lock:
            self._state.shutdown_in_progress = in_progress
        await self._notify()

    # ------------------------------------------------------------------
    # Action task management
    # ------------------------------------------------------------------

    def set_action_task(self, task: asyncio.Task | None) -> None:
        """Track the currently running action task so it can be cancelled."""
        self._action_task = task

    def cancel_action(self) -> bool:
        """Cancel the running action task if any. Returns True if cancelled."""
        if self._action_task and not self._action_task.done():
            self._action_task.cancel()
            self._action_task = None
            return True
        return False

    # ------------------------------------------------------------------
    # Complications
    # ------------------------------------------------------------------

    async def upsert_complication(
        self, app_id: str, update: ComplicationUpdate
    ) -> None:
        async with self._lock:
            comp = Complication(
                app_id=app_id,
                label=update.label,
                value=update.value,
                status=update.status,
                icon=update.icon,
                updated_at=time.time(),
                ttl_seconds=update.ttl_seconds,
            )
            existing = [c for c in self._state.complications if c.app_id != app_id]
            existing.append(comp)
            self._state.complications = existing
        await self._notify()

    async def remove_complication(self, app_id: str) -> bool:
        async with self._lock:
            before = len(self._state.complications)
            self._state.complications = [
                c for c in self._state.complications if c.app_id != app_id
            ]
            removed = len(self._state.complications) < before
        if removed:
            await self._notify()
        return removed

    async def expire_complications(self) -> None:
        """Remove complications whose TTL has elapsed. Called by periodic task."""
        now = time.time()
        async with self._lock:
            before = len(self._state.complications)
            self._state.complications = [
                c
                for c in self._state.complications
                if now - c.updated_at < c.ttl_seconds
            ]
            changed = len(self._state.complications) < before
        if changed:
            await self._notify()
