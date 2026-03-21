"""Pydantic data models for the fpms2 state service."""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Menu tree
# ---------------------------------------------------------------------------

class MenuNode(BaseModel):
    """A node in the FPMS menu tree.

    Leaf nodes have action_id set and no children.
    Branch nodes have children and no action_id.
    """
    id: str
    name: str
    children: list[str] = Field(default_factory=list)
    action_id: str | None = None
    hidden_in_mode: list[str] = Field(default_factory=list)
    visible_in_mode: list[str] = Field(default_factory=list)  # empty = all modes


# ---------------------------------------------------------------------------
# Page content (what an action returns)
# ---------------------------------------------------------------------------

class AlertContent(BaseModel):
    level: Literal["info", "error", "popup"]
    message: str
    dismiss_after_ms: int | None = None


class PageContent(BaseModel):
    title: str
    lines: list[str] = Field(default_factory=list)
    page_index: int = 0
    page_count: int = 1
    alert: AlertContent | None = None
    raw_image_b64: str | None = None  # base64 PNG for QR codes etc.


# ---------------------------------------------------------------------------
# Navigation location
# ---------------------------------------------------------------------------

DisplayState = Literal["home", "menu", "page", "alert"]


class NavLocation(BaseModel):
    path: list[int] = Field(default_factory=lambda: [0])
    display_state: DisplayState = "home"


# ---------------------------------------------------------------------------
# Homepage data (refreshed by periodic background task)
# ---------------------------------------------------------------------------

class BatteryData(BaseModel):
    present: bool
    charging: bool
    level_pct: int | None = None
    voltage_mv: int | None = None


class WlanInterface(BaseModel):
    name: str
    mac: str | None = None
    ssid: str | None = None
    channel: int | None = None
    phy: str | None = None


class HomepageData(BaseModel):
    mode: str = "classic"
    hostname: str = ""
    primary_ip: str = ""
    primary_interface: str = "eth0"
    eth_carrier: bool = False
    secondary_ips: list[dict] = Field(default_factory=list)
    reachable: bool | None = None
    wlan_interfaces: list[WlanInterface] = Field(default_factory=list)
    profiler_active: bool = False
    bluetooth_on: bool = False
    battery: BatteryData | None = None
    time_str: str = ""  # "HH:MM"
    alerts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Complications
# ---------------------------------------------------------------------------

ComplicationStatus = Literal["ok", "warning", "error", "unknown"]


class Complication(BaseModel):
    app_id: str
    label: str  # ≤8 chars for screen display
    value: str  # current value: "8 sats", "locked", "NO FIX"
    status: ComplicationStatus = "unknown"
    icon: str | None = None  # base64 PNG (16×16px) or single unicode char
    updated_at: float = Field(default_factory=time.time)
    ttl_seconds: int = 30


class ComplicationUpdate(BaseModel):
    """Body for POST /complications/{app_id}. app_id comes from path."""
    label: str
    value: str
    status: ComplicationStatus = "unknown"
    icon: str | None = None
    ttl_seconds: int = 30


# ---------------------------------------------------------------------------
# FPMS global state (broadcast to all clients)
# ---------------------------------------------------------------------------

class FpmsState(BaseModel):
    nav: NavLocation = Field(default_factory=NavLocation)
    current_page: PageContent | None = None
    homepage: HomepageData = Field(default_factory=HomepageData)
    loading: bool = False
    shutdown_in_progress: bool = False
    screen_sleeping: bool = False
    display_orientation: Literal["normal", "flipped"] = "normal"
    scroll_index: int = 0
    scroll_max: int = 0
    complications: list[Complication] = Field(default_factory=list)
    last_input_at: float = Field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Input events
# ---------------------------------------------------------------------------

ButtonName = Literal["up", "down", "left", "right", "center", "key1", "key2", "key3"]


class InputEvent(BaseModel):
    button: ButtonName


# ---------------------------------------------------------------------------
# WebSocket messages (server → client)
# ---------------------------------------------------------------------------

class WsStateMessage(BaseModel):
    type: Literal["state"] = "state"
    state: FpmsState


class WsPingMessage(BaseModel):
    type: Literal["ping"] = "ping"


class WsErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    error: str
