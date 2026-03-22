"""Bluetooth action handlers for fpms2."""

from __future__ import annotations

import logging

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.state.models import AlertContent, PageContent

log = logging.getLogger(__name__)


async def bluetooth_status(ctx: ActionContext) -> PageContent:
    """Show Bluetooth adapter status."""
    if ctx.core_client is None:
        return _unavailable("BT Status")
    try:
        status = await ctx.core_client.get_bluetooth_status()
        lines = [
            f"Name: {status.name}",
            f"Addr: {status.addr}",
            f"Power: {status.power}",
        ]
        if status.paired_devices:
            lines.append(f"Paired: {len(status.paired_devices)}")
            for dev in status.paired_devices[:3]:  # cap at 3 for screen space
                name = dev.get("Name") or dev.get("name") or dev.get("addr", "?")
                lines.append(f"  {name}")
        return PageContent(title="BT Status", lines=lines)
    except Exception as exc:
        return _error("BT Status", exc)


async def bluetooth_on(ctx: ActionContext) -> PageContent:
    """Turn Bluetooth on."""
    if ctx.core_client is None:
        return _unavailable("BT Power")
    try:
        await ctx.core_client.set_bluetooth_power(on=True)
        return PageContent(
            title="BT Power",
            lines=["Bluetooth: ON"],
            alert=AlertContent(level="info", message="Bluetooth turned on"),
        )
    except Exception as exc:
        return _error("BT Power", exc)


async def bluetooth_off(ctx: ActionContext) -> PageContent:
    """Turn Bluetooth off."""
    if ctx.core_client is None:
        return _unavailable("BT Power")
    try:
        await ctx.core_client.set_bluetooth_power(on=False)
        return PageContent(
            title="BT Power",
            lines=["Bluetooth: OFF"],
            alert=AlertContent(level="info", message="Bluetooth turned off"),
        )
    except Exception as exc:
        return _error("BT Power", exc)


async def bluetooth_pair(ctx: ActionContext) -> PageContent:
    """Start Bluetooth pairing mode via bt-timedpair service."""
    if ctx.core_client is None:
        return _unavailable("BT Pair")
    try:
        await ctx.core_client.start_service("bt-timedpair")
        return PageContent(
            title="BT Pair",
            lines=[
                "Pairing mode active.",
                "Pair your device now.",
                "(120 second window)",
            ],
            alert=AlertContent(level="info", message="Pairing mode started"),
        )
    except Exception as exc:
        return _error("BT Pair", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unavailable(title: str) -> PageContent:
    return PageContent(
        title=title,
        lines=["wlanpi-core unavailable"],
        alert=AlertContent(level="error", message="wlanpi-core not connected"),
    )


def _error(title: str, exc: Exception) -> PageContent:
    log.warning("%s action error: %s", title, exc)
    return PageContent(
        title=title,
        lines=[f"Error: {exc}"],
        alert=AlertContent(level="error", message=str(exc)),
    )
