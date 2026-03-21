"""Stub action registry for Phase 1.

All actions return a placeholder PageContent so the state service is
fully functional for navigation without requiring wlanpi-core.
Phase 2 replaces these stubs with real implementations.
"""

from __future__ import annotations

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.state.models import PageContent

_STUB_ACTIONS = [
    "network.interfaces",
    "network.wlan_interfaces",
    "network.eth0_ipconfig",
    "network.eth0_vlan",
    "network.lldp",
    "network.cdp",
    "network.publicip4",
    "network.publicip6",
    "bluetooth.status",
    "bluetooth.on",
    "bluetooth.off",
    "bluetooth.pair",
    "utils.reachability",
    "utils.speedtest",
    "utils.cloud.arista",
    "utils.cloud.aruba",
    "utils.cloud.extreme",
    "utils.cloud.meraki",
    "utils.cloud.mist",
    "utils.cloud.ruckus",
    "utils.port_blinker.start",
    "utils.port_blinker.stop",
    "utils.ssid_passphrase",
    "utils.usb",
    "utils.ufw",
    "modes.hotspot",
    "modes.server",
    "modes.bridge",
    "modes.classic",
    "apps.kismet.start",
    "apps.kismet.stop",
    "apps.profiler.status",
    "apps.profiler.stop",
    "apps.profiler.start",
    "apps.profiler.start_2_4",
    "apps.profiler.start_5_36",
    "apps.profiler.start_5_149",
    "apps.profiler.start_no11r",
    "apps.profiler.start_no11ax",
    "apps.profiler.purge_reports",
    "apps.profiler.purge_files",
    "apps.scanner.scan",
    "apps.scanner.scan_nohidden",
    "apps.scanner.csv",
    "apps.scanner.pcap_start",
    "apps.scanner.pcap_stop",
    "system.about",
    "system.help",
    "system.summary",
    "system.battery",
    "system.date",
    "system.timezone.auto",
    "system.timezone.set",
    "system.reg_domain.show",
    "system.reg_domain.set_us",
    "system.reg_domain.set_br",
    "system.reg_domain.set_ca",
    "system.reg_domain.set_cz",
    "system.reg_domain.set_de",
    "system.reg_domain.set_fr",
    "system.reg_domain.set_gb",
    "system.reg_domain.set_nl",
    "system.reg_domain.set_no",
    "system.rotate_display",
    "system.updates.check",
    "system.updates.install",
    "system.reboot",
    "system.shutdown",
]


def _make_stub(action_id: str):
    async def _stub(ctx: ActionContext) -> PageContent:
        return PageContent(
            title=action_id.split(".")[-1].replace("_", " ").title(),
            lines=[
                f"[stub] {action_id}",
                "",
                "Not yet implemented.",
                "wlanpi-core integration",
                "coming in Phase 2.",
            ],
        )
    _stub.__name__ = f"stub_{action_id.replace('.', '_')}"
    return _stub


def build_stub_registry() -> dict:
    return {aid: _make_stub(aid) for aid in _STUB_ACTIONS}
