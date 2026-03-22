"""Kismet action handlers for fpms2."""

from __future__ import annotations

import logging

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.state.models import AlertContent, PageContent

log = logging.getLogger(__name__)

_KISMET_SERVICE = "kismet"


async def kismet_start(ctx: ActionContext) -> PageContent:
    """Start Kismet service."""
    if ctx.core_client is None:
        return _unavailable("Kismet Start")
    try:
        await ctx.core_client.start_service(_KISMET_SERVICE)
        return PageContent(
            title="Kismet Start",
            lines=["Kismet started.", "Access via browser:", "http://<ip>:2501"],
            alert=AlertContent(level="info", message="Kismet started"),
        )
    except Exception as exc:
        return _error("Kismet Start", exc)


async def kismet_stop(ctx: ActionContext) -> PageContent:
    """Stop Kismet service."""
    if ctx.core_client is None:
        return _unavailable("Kismet Stop")
    try:
        await ctx.core_client.stop_service(_KISMET_SERVICE)
        return PageContent(
            title="Kismet Stop",
            lines=["Kismet stopped."],
            alert=AlertContent(level="info", message="Kismet stopped"),
        )
    except Exception as exc:
        return _error("Kismet Stop", exc)


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
