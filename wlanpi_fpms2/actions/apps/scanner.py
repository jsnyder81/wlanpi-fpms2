"""Scanner action handlers for fpms2."""

from __future__ import annotations

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.state.models import PageContent

_STUB_MSG = ["Not yet available.", "Requires wlanpi-core", "scan endpoint."]


async def scanner_scan(ctx: ActionContext) -> PageContent:
    return PageContent(title="Scanner", lines=_STUB_MSG)


async def scanner_scan_nohidden(ctx: ActionContext) -> PageContent:
    return PageContent(title="Scan (no hidden)", lines=_STUB_MSG)


async def scanner_csv(ctx: ActionContext) -> PageContent:
    return PageContent(title="Scan to CSV", lines=_STUB_MSG)


async def scanner_pcap_start(ctx: ActionContext) -> PageContent:
    return PageContent(title="PCAP Start", lines=_STUB_MSG)


async def scanner_pcap_stop(ctx: ActionContext) -> PageContent:
    return PageContent(title="PCAP Stop", lines=_STUB_MSG)
