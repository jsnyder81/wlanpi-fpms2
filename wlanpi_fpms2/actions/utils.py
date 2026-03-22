"""Utils action handlers for fpms2."""

from __future__ import annotations

import logging

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.state.models import AlertContent, PageContent

log = logging.getLogger(__name__)


async def show_reachability(ctx: ActionContext) -> PageContent:
    """Run reachability tests and show results."""
    if ctx.core_client is None:
        return _unavailable("Reachability")
    try:
        result = await ctx.core_client.get_reachability()
        lines = result.to_lines()
        if not lines:
            lines = ["No results"]
        return PageContent(title="Reachability", lines=lines)
    except Exception as exc:
        return _error("Reachability", exc)


async def show_usb(ctx: ActionContext) -> PageContent:
    """Show connected USB devices."""
    if ctx.core_client is None:
        return _unavailable("USB Devices")
    try:
        result = await ctx.core_client.get_usb()
        lines: list[str] = []
        for item in result.interfaces:
            if isinstance(item, dict):
                for k, v in item.items():
                    lines.append(f"{k}: {v}")
                lines.append("")  # blank separator
            else:
                lines.append(str(item))
        lines = [l for l in lines if l != ""]  # trim trailing blank
        if not lines:
            lines = ["No USB devices found"]
        return PageContent(title="USB Devices", lines=lines)
    except Exception as exc:
        return _error("USB Devices", exc)


async def show_ufw(ctx: ActionContext) -> PageContent:
    """Show UFW firewall port status."""
    if ctx.core_client is None:
        return _unavailable("UFW Ports")
    try:
        result = await ctx.core_client.get_ufw()
        lines = [f"Status: {result.status}"]
        for port in result.ports:
            if isinstance(port, dict):
                lines.append(str(port.get("port") or port))
            else:
                lines.append(str(port))
        if not result.ports:
            lines.append("No open ports")
        return PageContent(title="UFW Ports", lines=lines)
    except Exception as exc:
        return _error("UFW Ports", exc)


async def show_speedtest(ctx: ActionContext) -> PageContent:
    """Run speedtest via wlanpi-core."""
    if ctx.core_client is None:
        return _unavailable("Speedtest")
    try:
        result = await ctx.core_client.run_speedtest()
        lines = result.lines or ["No speedtest output"]
        return PageContent(title="Speedtest", lines=lines)
    except Exception as exc:
        return _error("Speedtest", exc)


async def port_blinker_start(ctx: ActionContext) -> PageContent:
    """Start port blinker. Not yet available in wlanpi-core."""
    return PageContent(
        title="Port Blinker",
        lines=["Not yet available.", "wlanpi-core endpoint", "not implemented."],
    )


async def port_blinker_stop(ctx: ActionContext) -> PageContent:
    """Stop port blinker. Not yet available in wlanpi-core."""
    return PageContent(
        title="Port Blinker",
        lines=["Not yet available.", "wlanpi-core endpoint", "not implemented."],
    )


async def show_ssid_passphrase(ctx: ActionContext) -> PageContent:
    """Show hotspot SSID and passphrase from hostapd.conf."""
    if ctx.core_client is None:
        return _unavailable("SSID/Passphrase")
    try:
        result = await ctx.core_client.get_ssid_passphrase()
        return PageContent(
            title="SSID/Passphrase",
            lines=[f"SSID: {result.ssid}", f"Pass: {result.passphrase}"],
        )
    except Exception as exc:
        return _error("SSID/Passphrase", exc)


# ---------------------------------------------------------------------------
# Cloud tests (stubs until wlanpi-core endpoints exist)
# ---------------------------------------------------------------------------

_CLOUD_VENDOR_KEYS = {
    "Arista CV-CUE":    "arista",
    "Aruba Central":    "aruba",
    "ExtremeCloud IQ":  "extreme",
    "Meraki Cloud":     "meraki",
    "Mist Cloud":       "mist",
    "RUCKUS Cloud":     "ruckus",
}


def _make_cloud_test(vendor_label: str):
    vendor_key = _CLOUD_VENDOR_KEYS[vendor_label]

    async def _action(ctx: ActionContext) -> PageContent:
        if ctx.core_client is None:
            return _unavailable(vendor_label)
        try:
            result = await ctx.core_client.run_cloud_test(vendor_key)
            lines = result.lines or ["No results"]
            status = "PASS" if result.success else "FAIL"
            return PageContent(title=f"{vendor_label}: {status}", lines=lines)
        except Exception as exc:
            return _error(vendor_label, exc)

    _action.__name__ = f"test_{vendor_key}"
    return _action


test_arista  = _make_cloud_test("Arista CV-CUE")
test_aruba   = _make_cloud_test("Aruba Central")
test_extreme = _make_cloud_test("ExtremeCloud IQ")
test_meraki  = _make_cloud_test("Meraki Cloud")
test_mist    = _make_cloud_test("Mist Cloud")
test_ruckus  = _make_cloud_test("RUCKUS Cloud")


# ---------------------------------------------------------------------------
# Mode switching (stubs until wlanpi-core endpoints exist)
# ---------------------------------------------------------------------------

def _make_mode_switcher(target_mode: str):
    async def _action(ctx: ActionContext) -> PageContent:
        if ctx.core_client is None:
            return _unavailable(f"Switch to {target_mode.title()}")
        try:
            result = await ctx.core_client.switch_mode(target_mode)
            return PageContent(
                title=f"Switch to {target_mode.title()}",
                lines=[result.status, "Rebooting..."],
                alert=AlertContent(level="info", message=result.status),
            )
        except Exception as exc:
            return _error(f"Switch to {target_mode.title()}", exc)
    _action.__name__ = f"switch_to_{target_mode}"
    return _action


switch_to_hotspot = _make_mode_switcher("hotspot")
switch_to_server  = _make_mode_switcher("server")
switch_to_bridge  = _make_mode_switcher("bridge")
switch_to_classic = _make_mode_switcher("classic")


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
