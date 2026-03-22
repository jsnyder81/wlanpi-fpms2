"""Scanner action handlers for fpms2."""

from __future__ import annotations

import logging

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.state.models import AlertContent, PageContent

log = logging.getLogger(__name__)

_PCAP_STUB = ["Not yet available.", "Use wlanpi-core", "streaming WebSocket API."]


def _fmt(net) -> str:
    ssid = net.ssid or "<hidden>"
    ch = f"ch{net.channel}" if net.channel else "?"
    return f"{ssid} {ch} {net.rssi}dBm"


async def scanner_scan(ctx: ActionContext) -> PageContent:
    """Scan for all WLAN networks including hidden."""
    if ctx.core_client is None:
        return _unavailable("Scanner")
    try:
        result = await ctx.core_client.scan_wlan(hidden=True)
        lines = [_fmt(n) for n in result.networks]
        if not lines:
            lines = ["No networks found"]
        return PageContent(title=f"Scan ({len(result.networks)})", lines=lines)
    except Exception as exc:
        log.warning("scanner_scan error: %s", exc)
        return PageContent(title="Scanner", lines=[f"Scan failed: {exc}"])


async def scanner_scan_nohidden(ctx: ActionContext) -> PageContent:
    """Scan for visible WLAN networks only."""
    if ctx.core_client is None:
        return _unavailable("Scanner")
    try:
        result = await ctx.core_client.scan_wlan(hidden=False)
        lines = [_fmt(n) for n in result.networks]
        if not lines:
            lines = ["No networks found"]
        return PageContent(title=f"Scan ({len(result.networks)})", lines=lines)
    except Exception as exc:
        log.warning("scanner_scan_nohidden error: %s", exc)
        return PageContent(title="Scanner", lines=[f"Scan failed: {exc}"])


async def scanner_csv(ctx: ActionContext) -> PageContent:
    """Export scan to CSV. Not yet implemented."""
    return PageContent(title="Scan to CSV", lines=_PCAP_STUB)


async def scanner_pcap_start(ctx: ActionContext) -> PageContent:
    """Start PCAP. Requires streaming WebSocket API."""
    return PageContent(title="PCAP Start", lines=_PCAP_STUB)


async def scanner_pcap_stop(ctx: ActionContext) -> PageContent:
    """Stop PCAP. Requires streaming WebSocket API."""
    return PageContent(title="PCAP Stop", lines=_PCAP_STUB)


def _unavailable(title: str) -> PageContent:
    return PageContent(
        title=title,
        lines=["wlanpi-core unavailable"],
        alert=AlertContent(level="error", message="wlanpi-core not connected"),
    )
