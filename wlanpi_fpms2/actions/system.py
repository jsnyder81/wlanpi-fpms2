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
    """Show battery status."""
    if ctx.core_client is None:
        return _unavailable("Battery")
    try:
        bat = await ctx.core_client.get_battery()
        if not bat.present:
            return PageContent(title="Battery", lines=["No battery installed"])
        lines = [f"Status: {bat.status.capitalize()}" if bat.status else ""]
        if bat.charge_pct is not None:
            lines.append(f"Charge: {bat.charge_pct}%")
        if bat.voltage_v is not None:
            lines.append(f"Voltage: {bat.voltage_v}V")
        if bat.cycle_count is not None:
            lines.append(f"Cycles: {bat.cycle_count}")
        return PageContent(title="Battery", lines=[l for l in lines if l])
    except Exception as exc:
        return _error("Battery", exc)


async def show_date(ctx: ActionContext) -> PageContent:
    """Show current date/time and timezone."""
    if ctx.core_client is None:
        return _unavailable("Date & Time")
    try:
        dt = await ctx.core_client.get_datetime()
        lines = [
            dt.date_str,
            dt.time_str,
            dt.city if dt.city else dt.timezone,
            f"TZ: {dt.tz_abbrev}" if dt.tz_abbrev else dt.timezone,
        ]
        return PageContent(title="Date & Time", lines=[l for l in lines if l])
    except Exception as exc:
        return _error("Date & Time", exc)


async def set_timezone_auto(ctx: ActionContext) -> PageContent:
    """Auto-detect and set timezone via tzupdate."""
    if ctx.core_client is None:
        return _unavailable("Set Timezone")
    try:
        tz_info = await ctx.core_client.set_timezone_auto()
        return PageContent(
            title="Set Timezone",
            lines=[
                "Auto-detect complete.",
                f"Timezone: {tz_info.timezone}",
                f"City: {tz_info.city}",
            ],
        )
    except Exception as exc:
        return _error("Set Timezone", exc)


async def set_timezone(ctx: ActionContext) -> PageContent:
    """Show current timezone (manual selection handled via menu)."""
    if ctx.core_client is None:
        return _unavailable("Timezone")
    try:
        tz_info = await ctx.core_client.get_timezone()
        return PageContent(
            title="Timezone",
            lines=[
                f"Current: {tz_info.timezone}",
                f"City: {tz_info.city}",
            ],
        )
    except Exception as exc:
        return _error("Timezone", exc)


async def show_reg_domain(ctx: ActionContext) -> PageContent:
    """Show current RF regulatory domain."""
    if ctx.core_client is None:
        return _unavailable("RF Domain")
    try:
        rd = await ctx.core_client.get_reg_domain()
        lines = [f"Domain: {rd.reg_domain}"] + rd.lines[1:]  # skip duplicate first line
        return PageContent(title="RF Domain", lines=lines if lines else [rd.reg_domain])
    except Exception as exc:
        return _error("RF Domain", exc)


def _make_set_reg_domain(code: str):
    async def _action(ctx: ActionContext) -> PageContent:
        if ctx.core_client is None:
            return _unavailable(f"Set Domain {code.upper()}")
        try:
            await ctx.core_client.set_reg_domain(code.upper())
            await ctx.store.set_shutdown(True, shutdown_type="reboot")
            return PageContent(
                title=f"Domain: {code.upper()}",
                lines=[
                    f"Domain set to {code.upper()}.",
                    "Rebooting device...",
                ],
                alert=AlertContent(level="info", message="Rebooting..."),
            )
        except Exception as exc:
            return _error(f"Set Domain {code.upper()}", exc)
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
    """Check for available wlanpi-* package updates."""
    if ctx.core_client is None:
        return _unavailable("Check Updates")
    try:
        info = await ctx.core_client.get_updates()
        if info.count == 0:
            lines = ["System up to date"]
        else:
            lines = [f"{u.package}: {u.version}" for u in info.updates]
        return PageContent(title=f"Updates ({info.count})", lines=lines)
    except Exception as exc:
        return _error("Check Updates", exc)


async def install_updates(ctx: ActionContext) -> PageContent:
    """Install available wlanpi-* package updates."""
    if ctx.core_client is None:
        return _unavailable("Install Updates")
    try:
        await ctx.core_client.install_updates()
        return PageContent(
            title="Install Updates",
            lines=["Updates installed.", "Reboot recommended."],
            alert=AlertContent(level="info", message="Updates installed"),
        )
    except Exception as exc:
        return _error("Install Updates", exc)


async def reboot(ctx: ActionContext) -> PageContent:
    """Reboot the device via wlanpi-core."""
    if ctx.core_client is None:
        return _unavailable("Reboot")
    try:
        await ctx.core_client.reboot()
        await ctx.store.set_shutdown(True, shutdown_type="reboot")
        return PageContent(
            title="Rebooting...",
            lines=["Device will reboot", "in a few seconds."],
            alert=AlertContent(level="info", message="Rebooting..."),
        )
    except Exception as exc:
        return _error("Reboot", exc)


async def shutdown(ctx: ActionContext) -> PageContent:
    """Shutdown the device via wlanpi-core."""
    if ctx.core_client is None:
        return _unavailable("Shutdown")
    try:
        await ctx.core_client.shutdown()
        await ctx.store.set_shutdown(True, shutdown_type="shutdown")
        return PageContent(
            title="Shutting Down...",
            lines=["Device will shut down", "in a few seconds."],
            alert=AlertContent(level="info", message="Shutting down..."),
        )
    except Exception as exc:
        return _error("Shutdown", exc)


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
