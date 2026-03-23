"""Tests for action handlers using a mock CoreApiClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from wlanpi_fpms2.actions.base import ActionContext
from wlanpi_fpms2.actions import network, system, bluetooth, utils
from wlanpi_fpms2.core_client.models import (
    BluetoothStatus,
    DeviceInfo,
    DeviceStats,
    IPInterface,
    IPInterfaceAddress,
    ReachabilityTest,
    ServiceStatus,
    UfwInfo,
    UsbInfo,
    WlanInterface,
    WlanInterfaces,
)
from wlanpi_fpms2.state.models import FpmsState
from wlanpi_fpms2.state.store import FpmsStateStore


def _make_ctx(core=None):
    store = FpmsStateStore()
    return ActionContext(store=store, core_client=core)


def _mock_core():
    m = AsyncMock()
    m.get_device_info = AsyncMock(return_value=DeviceInfo(
        model="WLANPi Pro",
        name="wlanpi",
        hostname="wlanpi.local",
        software_version="3.2.0",
        mode="classic",
    ))
    m.get_device_stats = AsyncMock(return_value=DeviceStats(
        ip="192.168.1.1",
        cpu="CPU Load: 0.15",
        ram="Mem: 256/512MB 50.00%",
        disk="Disk: 4/16GB 25%",
        cpu_temp="45.0",
        uptime="2h 15m",
    ))
    m.get_bluetooth_status = AsyncMock(return_value=BluetoothStatus(
        name="WLANPi",
        alias="WLANPi",
        addr="AA:BB:CC:DD:EE:FF",
        power="on",
        paired_devices=[],
    ))
    m.set_bluetooth_power = AsyncMock(return_value={"status": "success", "action": "on"})
    m.get_interfaces = AsyncMock(return_value={
        "interfaces": [
            IPInterface(
                ifindex=2,
                ifname="eth0",
                operstate="UP",
                link_type="ether",
                address="aa:bb:cc:dd:ee:ff",
                addr_info=[IPInterfaceAddress(family="inet", local="192.168.1.1", prefixlen=24)],
            ),
            IPInterface(
                ifindex=3,
                ifname="wlan0",
                operstate="UP",
                link_type="ether",
                address="11:22:33:44:55:66",
                addr_info=[IPInterfaceAddress(family="inet", local="192.168.1.100", prefixlen=24)],
            ),
        ]
    })
    m.get_wlan_interfaces = AsyncMock(return_value=WlanInterfaces(
        interfaces=[WlanInterface(interface="wlan0")]
    ))
    m.get_reachability = AsyncMock(return_value=ReachabilityTest.model_validate({
        "Ping Google": "ok",
        "Browse Google": "ok",
        "Ping Gateway": "ok",
        "Arping Gateway": "ok",
    }))
    m.get_usb = AsyncMock(return_value=UsbInfo(interfaces=[{"name": "USB WiFi Adapter"}]))
    m.get_ufw = AsyncMock(return_value=UfwInfo(status="active", ports=["22/tcp", "80/tcp"]))
    m.get_service_status = AsyncMock(return_value=ServiceStatus(name="wlanpi-profiler", active=True))
    m.start_service = AsyncMock(return_value={"name": "kismet", "active": True})
    m.stop_service = AsyncMock(return_value={"name": "kismet", "active": False})
    return m


# ---------------------------------------------------------------------------
# Network actions
# ---------------------------------------------------------------------------

class TestNetworkActions:
    async def test_show_interfaces_returns_lines(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await network.show_interfaces(ctx)
        assert page.title == "Interfaces"
        assert len(page.lines) >= 1
        assert any("eth0" in l or "e0" in l for l in page.lines)

    async def test_show_interfaces_no_core(self):
        ctx = _make_ctx(None)
        page = await network.show_interfaces(ctx)
        assert page.alert is not None
        assert page.alert.level == "error"

    async def test_show_wlan_interfaces(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await network.show_wlan_interfaces(ctx)
        assert page.title == "WLAN Interfaces"
        assert any("wlan0" in l for l in page.lines)

    async def test_show_eth0_ipconfig(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await network.show_eth0_ipconfig(ctx)
        assert page.title == "Eth0 IP Config"
        assert any("192.168.1.1" in l for l in page.lines)

    async def test_show_interfaces_api_error(self):
        core = _mock_core()
        core.get_interfaces = AsyncMock(side_effect=Exception("connection refused"))
        ctx = _make_ctx(core)
        page = await network.show_interfaces(ctx)
        assert page.alert is not None


# ---------------------------------------------------------------------------
# System actions
# ---------------------------------------------------------------------------

class TestSystemActions:
    async def test_show_about(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await system.show_about(ctx)
        assert page.title == "About"
        assert any("WLANPi Pro" in l for l in page.lines)
        assert any("3.2.0" in l for l in page.lines)

    async def test_show_summary(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await system.show_summary(ctx)
        assert page.title == "Summary"
        assert any("192.168.1.1" in l for l in page.lines)

    async def test_rotate_display_toggles(self):
        ctx = _make_ctx(None)
        # Default orientation is normal
        page = await system.rotate_display(ctx)
        assert "flipped" in page.lines[0]
        # Rotate again
        page = await system.rotate_display(ctx)
        assert "normal" in page.lines[0]

    async def test_show_help_always_works(self):
        ctx = _make_ctx(None)
        page = await system.show_help(ctx)
        assert page.title == "Help"


# ---------------------------------------------------------------------------
# Bluetooth actions
# ---------------------------------------------------------------------------

class TestBluetoothActions:
    async def test_bluetooth_status(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await bluetooth.bluetooth_status(ctx)
        assert page.title == "BT Status"
        assert any("on" in l.lower() for l in page.lines)

    async def test_bluetooth_on(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await bluetooth.bluetooth_on(ctx)
        assert "ON" in " ".join(page.lines).upper()
        core.set_bluetooth_power.assert_awaited_once_with(on=True)

    async def test_bluetooth_off(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await bluetooth.bluetooth_off(ctx)
        assert "OFF" in " ".join(page.lines).upper()
        core.set_bluetooth_power.assert_awaited_once_with(on=False)

    async def test_bluetooth_pair(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await bluetooth.bluetooth_pair(ctx)
        assert "pair" in page.title.lower() or "pair" in " ".join(page.lines).lower()
        core.start_service.assert_awaited_once_with("bt-timedpair")


# ---------------------------------------------------------------------------
# Utils actions
# ---------------------------------------------------------------------------

class TestUtilsActions:
    async def test_show_reachability(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await utils.show_reachability(ctx)
        assert page.title == "Reachability"
        assert len(page.lines) >= 1

    async def test_show_usb(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await utils.show_usb(ctx)
        assert page.title == "USB Devices"

    async def test_show_ufw(self):
        core = _mock_core()
        ctx = _make_ctx(core)
        page = await utils.show_ufw(ctx)
        assert page.title == "UFW Ports"
        assert any("active" in l.lower() for l in page.lines)

    async def test_stubs_return_page_content(self):
        ctx = _make_ctx(None)
        for fn in [
            utils.show_speedtest,
            utils.port_blinker_start,
            utils.port_blinker_stop,
            utils.show_ssid_passphrase,
            utils.test_arista,
            utils.test_meraki,
        ]:
            page = await fn(ctx)
            assert page.title
            assert page.lines
