"""Profiler action handlers for fpms2."""

from __future__ import annotations

import logging

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.actions.utils import _make_wifi_qr
from wlanpi_fpms2.state.models import AlertContent, PageContent

log = logging.getLogger(__name__)

_PROFILER_SERVICE = "wlanpi-profiler"


async def profiler_status(ctx: ActionContext) -> PageContent:
    """Show profiler service status, with QR code when running."""
    if ctx.core_client is None:
        return _unavailable("Profiler Status")
    try:
        status = await ctx.core_client.get_profiler_status()
        state_str = "Running" if status.running else "Stopped"
        lines = [f"Profiler: {state_str}"]
        raw_image_b64 = None
        if status.running and status.ssid:
            lines += [f"SSID: {status.ssid}", f"Pass: {status.passphrase or ''}"]
            raw_image_b64 = _make_wifi_qr(status.ssid, status.passphrase or "")
        return PageContent(
            title="Profiler Status",
            lines=lines,
            raw_image_b64=raw_image_b64,
        )
    except Exception as exc:
        return _error("Profiler Status", exc)


async def profiler_stop(ctx: ActionContext) -> PageContent:
    """Stop the profiler service."""
    if ctx.core_client is None:
        return _unavailable("Profiler Stop")
    try:
        await ctx.core_client.stop_service(_PROFILER_SERVICE)
        return PageContent(
            title="Profiler Stop",
            lines=["Profiler stopped."],
            alert=AlertContent(level="info", message="Profiler stopped"),
        )
    except Exception as exc:
        return _error("Profiler Stop", exc)


def _make_profiler_start(label: str, service_name: str = _PROFILER_SERVICE):
    async def _action(ctx: ActionContext) -> PageContent:
        if ctx.core_client is None:
            return _unavailable(f"Profiler {label}")
        try:
            await ctx.core_client.start_service(service_name)
            return PageContent(
                title=f"Profiler {label}",
                lines=[f"Profiler started", f"({label})"],
                alert=AlertContent(level="info", message=f"Profiler started ({label})"),
            )
        except Exception as exc:
            return _error(f"Profiler {label}", exc)
    _action.__name__ = f"profiler_start_{label.lower().replace(' ', '_')}"
    return _action


profiler_start        = _make_profiler_start("Start")
profiler_start_2_4    = _make_profiler_start("2.4 GHz")
profiler_start_5_36   = _make_profiler_start("5 GHz 36")
profiler_start_5_149  = _make_profiler_start("5 GHz 149")
profiler_start_no11r  = _make_profiler_start("no 11r")
profiler_start_no11ax = _make_profiler_start("no 11ax")


async def profiler_purge_reports(ctx: ActionContext) -> PageContent:
    """Purge profiler report files."""
    if ctx.core_client is None:
        return _unavailable("Purge Reports")
    try:
        result = await ctx.core_client.profiler_purge_reports()
        return PageContent(
            title="Purge Reports",
            lines=[result.message if result.success else "Purge failed"],
            alert=AlertContent(
                level="info" if result.success else "error",
                message=result.message,
            ),
        )
    except Exception as exc:
        return _error("Purge Reports", exc)


async def profiler_purge_files(ctx: ActionContext) -> PageContent:
    """Purge all profiler files."""
    if ctx.core_client is None:
        return _unavailable("Purge Files")
    try:
        result = await ctx.core_client.profiler_purge_files()
        return PageContent(
            title="Purge Files",
            lines=[result.message if result.success else "Purge failed"],
            alert=AlertContent(
                level="info" if result.success else "error",
                message=result.message,
            ),
        )
    except Exception as exc:
        return _error("Purge Files", exc)


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
