"""System action handlers for fpms2."""

from __future__ import annotations

import logging

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.state.models import AlertContent, PageContent

log = logging.getLogger(__name__)


async def show_about(ctx: ActionContext) -> PageContent:
    """Show device info: model, hostname, firmware version, mode."""
    if ctx.core_client is None:
        return _unavailable("About")
    try:
        info = await ctx.core_client.get_device_info()
        lines = [
            f"Hostname: {info.hostname}",
            f"Model: {info.model}",
            f"FW: {info.software_version}",
            f"Mode: {info.mode}",
        ]
        return PageContent(title="About", lines=lines)
    except Exception as exc:
        return _error("About", exc)


async def show_summary(ctx: ActionContext) -> PageContent:
    """Show system stats: IP, CPU, memory, disk, temp, uptime."""
    if ctx.core_client is None:
        return _unavailable("Summary")
    try:
        stats = await ctx.core_client.get_device_stats()
        lines = [
            stats.ip,
            stats.cpu,
            stats.ram,
            stats.disk,
            f"Temp: {stats.cpu_temp}",
            f"Up: {stats.uptime}",
        ]
        return PageContent(title="Summary", lines=[l for l in lines if l])
    except Exception as exc:
        return _error("Summary", exc)


async def show_battery(ctx: ActionContext) -> PageContent:
    """Show battery status. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="Battery",
        lines=[
            "Not yet available.",
            "Requires wlanpi-core",
            "battery endpoint.",
        ],
    )


async def show_date(ctx: ActionContext) -> PageContent:
    """Show current date/time and timezone. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="Date & Time",
        lines=[
            "Not yet available.",
            "Requires wlanpi-core",
            "timezone endpoint.",
        ],
    )


async def set_timezone_auto(ctx: ActionContext) -> PageContent:
    """Auto-detect and set timezone. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="Set Timezone",
        lines=["Not yet available."],
    )


async def set_timezone(ctx: ActionContext) -> PageContent:
    """Set timezone from selection. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="Set Timezone",
        lines=["Not yet available."],
    )


async def show_reg_domain(ctx: ActionContext) -> PageContent:
    """Show current RF regulatory domain. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="RF Domain",
        lines=["Not yet available.", "Requires wlanpi-core", "reg-domain endpoint."],
    )


def _make_set_reg_domain(code: str):
    async def _action(ctx: ActionContext) -> PageContent:
        return PageContent(
            title=f"Set Domain {code.upper()}",
            lines=["Not yet available.", "Requires wlanpi-core", "reg-domain endpoint."],
        )
    _action.__name__ = f"set_reg_domain_{code}"
    return _action

set_reg_domain_us = _make_set_reg_domain("us")
set_reg_domain_br = _make_set_reg_domain("br")
set_reg_domain_ca = _make_set_reg_domain("ca")
set_reg_domain_cz = _make_set_reg_domain("cz")
set_reg_domain_de = _make_set_reg_domain("de")
set_reg_domain_fr = _make_set_reg_domain("fr")
set_reg_domain_gb = _make_set_reg_domain("gb")
set_reg_domain_nl = _make_set_reg_domain("nl")
set_reg_domain_no = _make_set_reg_domain("no")


async def rotate_display(ctx: ActionContext) -> PageContent:
    """Toggle display orientation."""
    current = ctx.store.snapshot().display_orientation
    new_orientation = "flipped" if current == "normal" else "normal"
    await ctx.store.set_orientation(new_orientation)
    return PageContent(
        title="Rotate Display",
        lines=[f"Display: {new_orientation}"],
    )


async def check_updates(ctx: ActionContext) -> PageContent:
    """Check for available updates. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="Check Updates",
        lines=["Not yet available.", "Requires wlanpi-core", "updates endpoint."],
    )


async def install_updates(ctx: ActionContext) -> PageContent:
    """Install available updates. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="Install Updates",
        lines=["Not yet available.", "Requires wlanpi-core", "updates endpoint."],
    )


async def reboot(ctx: ActionContext) -> PageContent:
    """Reboot the device. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="Rebooting...",
        lines=["Not yet available.", "Requires wlanpi-core", "reboot endpoint."],
        alert=AlertContent(level="info", message="Rebooting..."),
    )


async def shutdown(ctx: ActionContext) -> PageContent:
    """Shutdown the device. Requires wlanpi-core gap endpoint."""
    return PageContent(
        title="Shutting Down...",
        lines=["Not yet available.", "Requires wlanpi-core", "shutdown endpoint."],
        alert=AlertContent(level="info", message="Shutting down..."),
    )


async def show_help(ctx: ActionContext) -> PageContent:
    """Show help information."""
    return PageContent(
        title="Help",
        lines=[
            "wlanpi-fpms2",
            "Docs: wlanpi.com",
            "GitHub: wlan-pi",
            "Discord: wlanpi.io",
        ],
    )


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
