"""Network action handlers for fpms2.

All functions follow the signature:
    async def action_name(ctx: ActionContext) -> PageContent
"""

from __future__ import annotations

import logging

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.state.models import AlertContent, PageContent

log = logging.getLogger(__name__)


def _short_ifname(name: str) -> str:
    """Shorten interface names for the 128px display.

    e.g. "eth0" → "e0", "wlan0" → "w0", "usb0" → "u0"
    """
    import re
    if len(name) <= 3:
        return name
    match = re.search(r"(\d+)(.*)$", name)
    if match:
        num = match.group(1)
        suffix = match.group(2) or ""
        return f"{name[0]}{num}{suffix}"
    return name[:4]


async def show_interfaces(ctx: ActionContext) -> PageContent:
    """List all network interfaces with state and IPv4."""
    if ctx.core_client is None:
        return _unavailable("Interfaces")
    try:
        ifaces_by_group = await ctx.core_client.get_interfaces()
        lines = []
        for ifaces in ifaces_by_group.values():
            for iface in ifaces:
                status = "▲" if iface.operstate.upper() == "UP" else "▽"
                short = _short_ifname(iface.ifname)
                ipv4 = iface.ipv4_addresses()
                ip_str = ipv4[0].split("/")[0] if ipv4 else "-"
                lines.append(f"{status} {short}: {ip_str}")
        if not lines:
            lines = ["No interfaces found"]
        return PageContent(title="Interfaces", lines=lines)
    except Exception as exc:
        return _error("Interfaces", exc)


async def show_wlan_interfaces(ctx: ActionContext) -> PageContent:
    """List WLAN interfaces from wlanpi-core."""
    if ctx.core_client is None:
        return _unavailable("WLAN Interfaces")
    try:
        wlan = await ctx.core_client.get_wlan_interfaces()
        lines = [iface.interface for iface in wlan.interfaces]
        if not lines:
            lines = ["No WLAN interfaces"]
        return PageContent(title="WLAN Interfaces", lines=lines)
    except Exception as exc:
        return _error("WLAN Interfaces", exc)


async def show_eth0_ipconfig(ctx: ActionContext) -> PageContent:
    """Show eth0 IP configuration details."""
    if ctx.core_client is None:
        return _unavailable("Eth0 IP Config")
    try:
        ifaces_by_group = await ctx.core_client.get_interfaces(interface="eth0")
        lines: list[str] = []
        for ifaces in ifaces_by_group.values():
            for iface in ifaces:
                if iface.ifname != "eth0":
                    continue
                lines.append(f"Interface: {iface.ifname}")
                lines.append(f"State: {iface.operstate}")
                lines.append(f"MAC: {iface.address}")
                for addr in iface.addr_info:
                    if addr.family == "inet":
                        lines.append(f"IPv4: {addr.local}/{addr.prefixlen}")
                        if addr.broadcast:
                            lines.append(f"Bcast: {addr.broadcast}")
                    elif addr.family == "inet6" and getattr(addr, "scope", None) == "global":
                        lines.append(f"IPv6: {addr.local}/{addr.prefixlen}")
        if not lines:
            lines = ["eth0 not found"]
        return PageContent(title="Eth0 IP Config", lines=lines)
    except Exception as exc:
        return _error("Eth0 IP Config", exc)


async def show_eth0_vlan(ctx: ActionContext) -> PageContent:
    """Show VLAN configuration on eth0."""
    if ctx.core_client is None:
        return _unavailable("Eth0 VLAN")
    try:
        vlans_by_group = await ctx.core_client.get_vlans(interface="eth0")
        lines: list[str] = []
        for ifaces in vlans_by_group.values():
            for iface in ifaces:
                vlan_id = (
                    iface.model_extra.get("linkinfo", {})
                    .get("info_data", {})
                    .get("id", "?")
                    if hasattr(iface, "model_extra")
                    else "?"
                )
                ipv4 = iface.ipv4_addresses()
                ip_str = ipv4[0].split("/")[0] if ipv4 else "-"
                lines.append(f"VLAN {vlan_id}: {iface.ifname}")
                lines.append(f"  IP: {ip_str}")
        if not lines:
            lines = ["No VLANs configured"]
        return PageContent(title="Eth0 VLAN", lines=lines)
    except Exception as exc:
        return _error("Eth0 VLAN", exc)


async def show_lldp(ctx: ActionContext) -> PageContent:
    """Show LLDP neighbour data from wlanpi-core /network/info/."""
    if ctx.core_client is None:
        return _unavailable("LLDP Neighbour")
    try:
        info = await ctx.core_client.get_network_info()
        lldp = info.lldp_neighbour_info
        lines = _flatten_dict(lldp)
        if not lines:
            lines = ["No LLDP neighbours"]
        return PageContent(title="LLDP Neighbour", lines=lines)
    except Exception as exc:
        return _error("LLDP Neighbour", exc)


async def show_cdp(ctx: ActionContext) -> PageContent:
    """Show CDP neighbour data from wlanpi-core /network/info/."""
    if ctx.core_client is None:
        return _unavailable("CDP Neighbour")
    try:
        info = await ctx.core_client.get_network_info()
        cdp = info.cdp_neighbour_info
        lines = _flatten_dict(cdp)
        if not lines:
            lines = ["No CDP neighbours"]
        return PageContent(title="CDP Neighbour", lines=lines)
    except Exception as exc:
        return _error("CDP Neighbour", exc)


async def show_publicip4(ctx: ActionContext) -> PageContent:
    """Show public IPv4 address from wlanpi-core /network/info/."""
    if ctx.core_client is None:
        return _unavailable("Public IPv4")
    try:
        info = await ctx.core_client.get_network_info()
        pub = info.public_ip
        lines = _flatten_dict(pub)
        if not lines:
            lines = ["No public IP data"]
        return PageContent(title="Public IPv4", lines=lines)
    except Exception as exc:
        return _error("Public IPv4", exc)


async def show_publicip6(ctx: ActionContext) -> PageContent:
    """Show public IPv6 address. Stub until dedicated endpoint exists."""
    return PageContent(
        title="Public IPv6",
        lines=["Not yet available.", "Requires wlanpi-core", "gap endpoint."],
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


def _flatten_dict(d: dict, prefix: str = "", max_depth: int = 2) -> list[str]:
    """Flatten a nested dict into display lines."""
    lines: list[str] = []
    for k, v in d.items():
        key_str = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict) and max_depth > 0:
            lines.extend(_flatten_dict(v, key_str, max_depth - 1))
        else:
            lines.append(f"{k}: {v}")
    return lines
