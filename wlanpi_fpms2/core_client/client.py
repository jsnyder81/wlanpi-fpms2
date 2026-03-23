"""CoreApiClient — async httpx client for the wlanpi-core REST API.

All requests are signed with HMAC so no explicit JWT is needed when
calling from localhost.

Usage:
    async with CoreApiClient() as client:
        info = await client.get_device_info()
        stats = await client.get_device_stats()
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from wlanpi_fpms2.core_client.hmac_auth import HmacAuth
from wlanpi_fpms2.core_client.models import (
    BatteryInfo,
    BluetoothStatus,
    CloudTestResult,
    DateTimeInfo,
    DeviceInfo,
    DeviceStats,
    IPInterface,
    ModeSwitch,
    NetworkInfo,
    ProfilerPurge,
    ProfilerStatus,
    PublicIpInfo,
    ReachabilityTest,
    RegDomainInfo,
    ScanResults,
    ServiceStatus,
    SpeedtestResult,
    SsidPassphrase,
    TimezoneInfo,
    TimezoneList,
    UfwInfo,
    UpdatesInfo,
    UsbInfo,
    WlanInterfaces,
)

log = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost/api/v1"
_DEFAULT_TIMEOUT = 30.0


class CoreApiClient:
    """Async HTTP client for wlanpi-core.

    Can be used as an async context manager or instantiated and closed manually.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        secret: bytes | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            auth=HmacAuth(secret=secret),
            timeout=timeout,
        )

    async def __aenter__(self) -> "CoreApiClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> Any:
        try:
            r = await self._client.get(path, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            log.warning("wlanpi-core GET %s → %s", path, exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            log.warning("wlanpi-core GET %s → network error: %s", path, exc)
            raise

    async def _post(self, path: str, params: dict | None = None, json: Any = None) -> Any:
        try:
            r = await self._client.post(path, params=params, json=json)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            log.warning("wlanpi-core POST %s → %s", path, exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            log.warning("wlanpi-core POST %s → network error: %s", path, exc)
            raise

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    async def get_device_info(self) -> DeviceInfo:
        data = await self._get("/system/device/info")
        return DeviceInfo.model_validate(data)

    async def get_device_stats(self) -> DeviceStats:
        data = await self._get("/system/device/stats")
        return DeviceStats.model_validate(data)

    async def get_service_status(self, name: str) -> ServiceStatus:
        data = await self._get("/system/service/status", params={"name": name})
        return ServiceStatus.model_validate(data)

    async def start_service(self, name: str) -> dict:
        return await self._post("/system/service/start", params={"name": name})

    async def stop_service(self, name: str) -> dict:
        return await self._post("/system/service/stop", params={"name": name})

    # ------------------------------------------------------------------
    # Bluetooth
    # ------------------------------------------------------------------

    async def get_bluetooth_status(self) -> BluetoothStatus:
        data = await self._get("/bluetooth/status")
        return BluetoothStatus.model_validate(data)

    async def set_bluetooth_power(self, on: bool) -> dict:
        action = "on" if on else "off"
        return await self._post(f"/bluetooth/power/{action}")

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    async def get_interfaces(self, interface: str | None = None) -> dict[str, list[IPInterface]]:
        path = f"/network/interfaces/{interface}" if interface else "/network/interfaces"
        data = await self._get(path)
        return {
            key: [IPInterface.model_validate(iface) for iface in ifaces]
            for key, ifaces in data.items()
        }

    async def get_vlans(self, interface: str = "eth0") -> dict[str, list[IPInterface]]:
        data = await self._get(f"/network/ethernet/{interface}/vlan")
        return {
            key: [IPInterface.model_validate(iface) for iface in ifaces]
            for key, ifaces in data.items()
        }

    async def get_wlan_interfaces(self) -> WlanInterfaces:
        data = await self._get("/network/wlan/getInterfaces")
        return WlanInterfaces.model_validate(data)

    async def get_network_info(self) -> NetworkInfo:
        data = await self._get("/network/info/")
        return NetworkInfo.model_validate(data)

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    async def get_reachability(self) -> ReachabilityTest:
        data = await self._get("/utils/reachability")
        return ReachabilityTest.model_validate(data)

    async def get_usb(self) -> UsbInfo:
        data = await self._get("/utils/usb")
        return UsbInfo.model_validate(data)

    async def get_ufw(self) -> UfwInfo:
        data = await self._get("/utils/ufw")
        return UfwInfo.model_validate(data)

    async def reboot(self) -> dict:
        return await self._post("/system/reboot")

    async def shutdown(self) -> dict:
        return await self._post("/system/shutdown")

    # ------------------------------------------------------------------
    # Timezone
    # ------------------------------------------------------------------

    async def get_timezone(self) -> TimezoneInfo:
        data = await self._get("/system/timezone")
        return TimezoneInfo.model_validate(data)

    async def list_timezones(self) -> TimezoneList:
        data = await self._get("/system/timezone/list")
        return TimezoneList.model_validate(data)

    async def set_timezone(self, timezone: str) -> TimezoneInfo:
        data = await self._post("/system/timezone/set", json={"timezone": timezone})
        return TimezoneInfo.model_validate(data)

    async def set_timezone_auto(self) -> TimezoneInfo:
        data = await self._post("/system/timezone/auto")
        return TimezoneInfo.model_validate(data)

    # ------------------------------------------------------------------
    # Regulatory Domain
    # ------------------------------------------------------------------

    async def get_reg_domain(self) -> RegDomainInfo:
        data = await self._get("/system/reg-domain")
        return RegDomainInfo.model_validate(data)

    async def set_reg_domain(self, country: str) -> RegDomainInfo:
        data = await self._post("/system/reg-domain/set", json={"country": country})
        return RegDomainInfo.model_validate(data)

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    async def get_updates(self) -> UpdatesInfo:
        data = await self._get("/system/updates")
        return UpdatesInfo.model_validate(data)

    async def install_updates(self) -> dict:
        return await self._post("/system/updates/install")

    # ------------------------------------------------------------------
    # Battery
    # ------------------------------------------------------------------

    async def get_battery(self) -> BatteryInfo:
        data = await self._get("/system/battery")
        return BatteryInfo.model_validate(data)

    # ------------------------------------------------------------------
    # Date / Time
    # ------------------------------------------------------------------

    async def get_datetime(self) -> DateTimeInfo:
        data = await self._get("/system/datetime")
        return DateTimeInfo.model_validate(data)

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    async def switch_mode(self, mode: str) -> ModeSwitch:
        data = await self._post("/system/mode/switch", json={"mode": mode})
        return ModeSwitch.model_validate(data)

    # ------------------------------------------------------------------
    # SSID / Passphrase
    # ------------------------------------------------------------------

    async def get_ssid_passphrase(self) -> SsidPassphrase:
        data = await self._get("/system/ssid-passphrase")
        return SsidPassphrase.model_validate(data)

    # ------------------------------------------------------------------
    # Public IPv6
    # ------------------------------------------------------------------

    async def get_public_ipv6(self) -> PublicIpInfo:
        data = await self._get("/network/info/publicip6")
        return PublicIpInfo.model_validate(data)

    # ------------------------------------------------------------------
    # Speedtest
    # ------------------------------------------------------------------

    async def run_speedtest(self) -> SpeedtestResult:
        data = await self._get("/utils/speedtest")
        return SpeedtestResult.model_validate(data)

    # ------------------------------------------------------------------
    # Cloud tests
    # ------------------------------------------------------------------

    async def run_cloud_test(self, vendor: str) -> CloudTestResult:
        data = await self._get(f"/utils/cloud-test/{vendor}")
        return CloudTestResult.model_validate(data)

    # ------------------------------------------------------------------
    # WLAN scanner
    # ------------------------------------------------------------------

    async def scan_wlan(self, iface: str = "wlan0", hidden: bool = True) -> ScanResults:
        data = await self._get("/utils/wlan/scan", params={"iface": iface, "hidden": str(hidden).lower()})
        return ScanResults.model_validate(data)

    # ------------------------------------------------------------------
    # Profiler
    # ------------------------------------------------------------------

    async def get_profiler_status(self) -> ProfilerStatus:
        data = await self._get("/profiler/status")
        return ProfilerStatus.model_validate(data)

    async def profiler_purge_reports(self) -> ProfilerPurge:
        data = await self._post("/profiler/purge/reports")
        return ProfilerPurge.model_validate(data)

    async def profiler_purge_files(self) -> ProfilerPurge:
        data = await self._post("/profiler/purge/files")
        return ProfilerPurge.model_validate(data)
