"""Typed Pydantic models for wlanpi-core REST API responses."""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

class DeviceInfo(BaseModel):
    model: str = ""
    name: str = ""
    hostname: str = ""
    software_version: str = ""
    mode: str = "classic"


class DeviceStats(BaseModel):
    ip: str = ""
    cpu: str = ""
    ram: str = ""
    disk: str = ""
    cpu_temp: str = ""
    uptime: str = ""


class ServiceStatus(BaseModel):
    name: str
    active: bool


class TimezoneInfo(BaseModel):
    timezone: str = "UTC"
    city: str = ""


class TimezoneList(BaseModel):
    timezones: list[str] = Field(default_factory=list)


class RegDomainInfo(BaseModel):
    reg_domain: str = ""
    lines: list[str] = Field(default_factory=list)


class UpdatePackage(BaseModel):
    package: str = ""
    version: str = ""


class UpdatesInfo(BaseModel):
    updates: list[UpdatePackage] = Field(default_factory=list)
    count: int = 0


class BatteryInfo(BaseModel):
    present: bool = False
    status: str = ""
    charge_pct: Optional[int] = None
    voltage_v: Optional[float] = None
    cycle_count: Optional[int] = None


class DateTimeInfo(BaseModel):
    date_str: str = ""
    time_str: str = ""
    timezone: str = ""
    city: str = ""
    tz_abbrev: str = ""


class ModeSwitch(BaseModel):
    mode: str = ""
    status: str = ""


class SsidPassphrase(BaseModel):
    ssid: str = ""
    passphrase: str = ""


class ClientCount(BaseModel):
    count: int = 0
    clients: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Bluetooth
# ---------------------------------------------------------------------------

class BluetoothStatus(BaseModel):
    name: str = ""
    alias: str = ""
    addr: str = ""
    power: str = ""
    paired_devices: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

class ReachabilityTest(BaseModel):
    ping_google: str = Field("", alias="Ping Google")
    browse_google: str = Field("", alias="Browse Google")
    ping_gateway: str = Field("", alias="Ping Gateway")
    dns_server_1_resolution: str | None = Field(None, alias="DNS Server 1 Resolution")
    dns_server_2_resolution: str | None = Field(None, alias="DNS Server 2 Resolution")
    dns_server_3_resolution: str | None = Field(None, alias="DNS Server 3 Resolution")
    arping_gateway: str = Field("", alias="Arping Gateway")

    model_config = {"populate_by_name": True}

    def to_lines(self) -> list[str]:
        fields = [
            ("Ping Google",   self.ping_google),
            ("Browse Google", self.browse_google),
            ("Ping Gateway",  self.ping_gateway),
            ("DNS 1",         self.dns_server_1_resolution or ""),
            ("DNS 2",         self.dns_server_2_resolution or ""),
            ("DNS 3",         self.dns_server_3_resolution or ""),
            ("Arping GW",     self.arping_gateway),
        ]
        return [f"{label}: {val}" for label, val in fields if val]


class UsbDevice(BaseModel):
    model_config = {"extra": "allow"}


class UsbInfo(BaseModel):
    interfaces: list[Any] = Field(default_factory=list)


class UfwInfo(BaseModel):
    status: str = ""
    ports: list[Any] = Field(default_factory=list)


class PublicIpInfo(BaseModel):
    lines: list[str] = Field(default_factory=list)


class SpeedtestResult(BaseModel):
    lines: list[str] = Field(default_factory=list)


class CloudTestResult(BaseModel):
    vendor: str = ""
    lines: list[str] = Field(default_factory=list)
    success: bool = False


class ScanNetwork(BaseModel):
    ssid: str = ""
    bssid: str = ""
    channel: Optional[int] = None
    rssi: int = 0
    hidden: bool = False


class ScanResults(BaseModel):
    networks: list[ScanNetwork] = Field(default_factory=list)


class ProfilerPurge(BaseModel):
    success: bool = False
    message: str = ""


class ProfilerStatus(BaseModel):
    running: bool = False
    ssid: str | None = None
    passphrase: str | None = None


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

class IPInterfaceAddress(BaseModel):
    family: str = ""
    local: str | None = None
    prefixlen: int | None = None
    broadcast: str | None = None
    scope: Union[str, int] = "global"

    model_config = {"extra": "allow"}


class IPInterface(BaseModel):
    ifindex: int = 0
    ifname: str = ""
    flags: list[str] = Field(default_factory=list)
    mtu: int = 0
    operstate: str = ""
    link_type: str = ""
    address: str = ""
    addr_info: list[IPInterfaceAddress] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    def ipv4_addresses(self) -> list[str]:
        return [
            f"{a.local}/{a.prefixlen}"
            for a in self.addr_info
            if a.family == "inet" and a.local
        ]

    def ipv6_addresses(self) -> list[str]:
        return [
            f"{a.local}/{a.prefixlen}"
            for a in self.addr_info
            if a.family == "inet6" and a.local and a.scope == "global"
        ]


class WlanInterface(BaseModel):
    interface: str = ""


class WlanInterfaces(BaseModel):
    interfaces: list[WlanInterface] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Network Info (from /network/info/)
# ---------------------------------------------------------------------------

class NetworkInfo(BaseModel):
    interfaces: dict = Field(default_factory=dict)
    wlan_interfaces: dict = Field(default_factory=dict)
    eth0_ipconfig_info: dict = Field(default_factory=dict)
    vlan_info: dict = Field(default_factory=dict)
    lldp_neighbour_info: dict = Field(default_factory=dict)
    cdp_neighbour_info: dict = Field(default_factory=dict)
    public_ip: dict = Field(default_factory=dict)
