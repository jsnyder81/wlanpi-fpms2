"""WebSocket broadcaster — pushes FpmsState snapshots to all connected clients."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from wlanpi_fpms2.state.models import FpmsState, WsPingMessage, WsStateMessage

log = logging.getLogger(__name__)

_PING_INTERVAL = 15.0  # seconds


class Broadcaster:
    """Maintains a set of active WebSocket connections and broadcasts state."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def send_state(self, state: FpmsState) -> None:
        """Push a full state snapshot to all connected clients."""
        msg = WsStateMessage(state=state).model_dump_json()
        await self._broadcast_text(msg)

    async def _broadcast_text(self, text: str) -> None:
        dead: list[WebSocket] = []
        async with self._lock:
            active = list(self._connections)
        for ws in active:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(text)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)

    async def ping_loop(self) -> None:
        """Background coroutine: send keepalive pings to all clients."""
        ping_msg = WsPingMessage().model_dump_json()
        while True:
            await asyncio.sleep(_PING_INTERVAL)
            await self._broadcast_text(ping_msg)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
