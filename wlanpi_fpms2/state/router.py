"""FastAPI router for the fpms2 state service.

Endpoints:
  GET  /health
  GET  /state
  GET  /menu
  POST /input
  WS   /ws
  POST /complications/{app_id}
  DELETE /complications/{app_id}
  GET  /complications
"""

from __future__ import annotations

import asyncio
import logging
from importlib.metadata import version, PackageNotFoundError
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from wlanpi_fpms2.state.models import (
    ComplicationUpdate,
    FpmsState,
    InputEvent,
    MenuNode,
    NavigateRequest,
)
from wlanpi_fpms2.nav.navigator import NavResult, handle_input, navigate_to_node

if TYPE_CHECKING:
    from wlanpi_fpms2.state.store import FpmsStateStore
    from wlanpi_fpms2.state.broadcaster import Broadcaster
    from wlanpi_fpms2.state.menu_tree import MenuTree

log = logging.getLogger(__name__)

try:
    _VERSION = version("wlanpi-fpms2")
except PackageNotFoundError:
    _VERSION = "dev"

router = APIRouter()


def _get_store(request: Request) -> "FpmsStateStore":
    return request.app.state.store  # type: ignore[return-value]


def _get_broadcaster(request: Request) -> "Broadcaster":
    return request.app.state.broadcaster  # type: ignore[return-value]


def _get_tree(request: Request) -> "MenuTree":
    return request.app.state.menu_tree  # type: ignore[return-value]


def _get_action_registry(request: Request) -> dict:
    return request.app.state.action_registry  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": _VERSION}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@router.get("/state", response_model=FpmsState)
async def get_state(request: Request) -> FpmsState:
    return _get_store(request).snapshot()


# ---------------------------------------------------------------------------
# Menu tree
# ---------------------------------------------------------------------------

@router.get("/menu", response_model=list[MenuNode])
async def get_menu(request: Request) -> list[MenuNode]:
    tree = _get_tree(request)
    # Return only nodes reachable from tree.roots — this excludes orphaned
    # nodes such as apps.kismet/profiler/scanner in non-classic modes, which
    # exist in the index but are not referenced from any root path.
    visited: list[str] = []
    queue = list(tree.roots)
    seen: set[str] = set()
    while queue:
        nid = queue.pop(0)
        if nid in seen or nid not in tree.index:
            continue
        seen.add(nid)
        visited.append(nid)
        queue.extend(tree.index[nid].children)
    return [tree.index[nid] for nid in visited]


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------

_FLIP_BUTTON_MAP = {
    "up": "down", "down": "up",
    "left": "right", "right": "left",
    "key1": "key3", "key3": "key1",
}


@router.post("/input", status_code=202)
async def post_input(event: InputEvent, request: Request) -> dict:
    store = _get_store(request)
    tree = _get_tree(request)
    registry = _get_action_registry(request)
    state = store.snapshot()

    if state.shutdown_in_progress:
        return {"status": "shutdown_in_progress"}

    # Remap buttons when display is flipped
    if state.display_orientation == "flipped":
        remapped = _FLIP_BUTTON_MAP.get(event.button)
        if remapped:
            event = InputEvent(button=remapped)  # type: ignore[arg-type]

    # Compute new navigation
    result: NavResult = handle_input(state, event, tree)

    # If "left" was pressed while loading → cancel running action
    if event.button == "left" and state.loading:
        store.cancel_action()
        result.nav.display_state = "menu"
        result.action_id = None
        # Reset scroll
        await store.set_scroll(0, 0)

    # Handle special sentinel action IDs
    if result.action_id == "__toggle_home_alt__":
        await store.toggle_home_alternate()
        return {"status": "ok"}

    # Apply navigation
    await store.apply_nav(result.nav)

    # Handle scroll in page mode
    if result.scroll_delta != 0:
        new_idx = max(0, min(state.scroll_max, state.scroll_index + result.scroll_delta))
        await store.set_scroll(new_idx, state.scroll_max)

    # Dispatch action if a leaf was selected
    if result.action_id:
        action_fn = registry.get(result.action_id)
        if action_fn is None:
            log.warning("No action registered for %s", result.action_id)
            await store.set_page(None)
        else:
            await store.set_loading(True)
            task = asyncio.create_task(
                _run_action(action_fn, result.action_id, store, request)
            )
            store.set_action_task(task)

    return {"status": "ok"}


async def _run_action(
    action_fn: Any,
    action_id: str,
    store: "FpmsStateStore",
    request: Request,
) -> None:
    from wlanpi_fpms2.actions.base import ActionContext
    try:
        ctx = ActionContext(
            store=store,
            core_client=getattr(request.app.state, "core_client", None),
        )
        page = await action_fn(ctx)
        await store.set_page(page)
    except asyncio.CancelledError:
        log.info("Action %s cancelled", action_id)
        await store.set_loading(False)
    except Exception as exc:
        log.exception("Action %s failed: %s", action_id, exc)
        from wlanpi_fpms2.state.models import AlertContent, PageContent
        await store.set_page(PageContent(
            title="Error",
            lines=[str(exc)],
            alert=AlertContent(level="error", message=str(exc)),
        ))


# ---------------------------------------------------------------------------
# Direct navigation
# ---------------------------------------------------------------------------

@router.post("/navigate", status_code=202)
async def post_navigate(nav_req: NavigateRequest, request: Request) -> dict:
    """Jump directly to a menu node by ID.

    Branch node: enters its submenu.
    Leaf node:   navigates to it and dispatches its action.
    """
    store = _get_store(request)
    tree = _get_tree(request)
    registry = _get_action_registry(request)
    state = store.snapshot()

    if state.shutdown_in_progress:
        return {"status": "shutdown_in_progress"}
    if state.loading:
        return {"status": "loading"}

    result: NavResult = navigate_to_node(state, nav_req.node_id, tree)

    await store.apply_nav(result.nav)
    await store.set_scroll(0, 0)

    if result.action_id:
        action_fn = registry.get(result.action_id)
        if action_fn is None:
            log.warning("No action registered for %s", result.action_id)
            await store.set_page(None)
        else:
            await store.set_loading(True)
            task = asyncio.create_task(
                _run_action(action_fn, result.action_id, store, request)
            )
            store.set_action_task(task)

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Complications
# ---------------------------------------------------------------------------

@router.get("/complications")
async def list_complications(request: Request) -> list:
    store = _get_store(request)
    return store.snapshot().complications


@router.post("/complications/{app_id}", status_code=200)
async def upsert_complication(
    app_id: str, update: ComplicationUpdate, request: Request
) -> dict:
    store = _get_store(request)
    await store.upsert_complication(app_id, update)
    return {"status": "ok", "app_id": app_id}


@router.delete("/complications/{app_id}", status_code=204)
async def delete_complication(app_id: str, request: Request) -> None:
    store = _get_store(request)
    removed = await store.remove_complication(app_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"No complication '{app_id}'")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    broadcaster = _get_broadcaster(ws)
    store = _get_store(ws)

    await broadcaster.connect(ws)
    try:
        # Send current state immediately on connect
        await ws.send_text(
            __import__("wlanpi_fpms2.state.models", fromlist=["WsStateMessage"])
            .WsStateMessage(state=store.snapshot())
            .model_dump_json()
        )
        # Hold the connection open (we only send, never receive)
        while True:
            await ws.receive_text()  # blocks; raises on disconnect
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(ws)
