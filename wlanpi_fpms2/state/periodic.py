"""Background periodic tasks for the fpms2 state service.

Tasks:
- expire_complications: remove stale complications every 5 seconds
- homepage_refresh: refresh homepage data from wlanpi-core every 5 seconds
- profiler_notification: watch for newly profiled devices every 2 seconds
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wlanpi_fpms2.core_client.client import CoreApiClient
    from wlanpi_fpms2.state.store import FpmsStateStore

log = logging.getLogger(__name__)

_REFRESH_INTERVAL = 5.0    # seconds between homepage polls
_REACHABILITY_TTL = 60.0   # seconds to cache reachability result
_PROFILER_LAST_PROFILE = "/var/run/wlanpi-profiler.last_profile"


async def expire_complications_loop(store: "FpmsStateStore") -> None:
    """Periodically remove complications whose TTL has elapsed."""
    while True:
        try:
            await asyncio.sleep(5)
            await store.expire_complications()
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Error in expire_complications_loop")


async def homepage_refresh_loop(
    store: "FpmsStateStore",
    core_client: "CoreApiClient | None",
    app: object | None = None,
) -> None:
    """Periodically refresh homepage data from wlanpi-core.

    When the device mode changes (e.g. classic → hotspot), the server-side
    menu tree is rebuilt so navigation indices stay correct.
    """
    _last_reachability_at: float = 0.0
    _last_reachability: bool | None = None

    while True:
        try:
            await asyncio.sleep(_REFRESH_INTERVAL)

            if core_client is None:
                continue

            now = time.time()

            from wlanpi_fpms2.state.models import HomepageData, WlanInterface as WlanIfaceModel

            # Device info (mode, hostname)
            try:
                info = await core_client.get_device_info()
                mode = info.mode
                hostname = info.hostname
            except Exception:
                mode = "classic"
                hostname = ""

            # Rebuild the server-side menu tree if mode has changed.
            # This fixes index mismatches between the server tree (built at
            # startup from /etc/wlanpi-state) and the actual device mode.
            if app is not None:
                current_tree = getattr(app.state, "menu_tree", None)
                if current_tree is not None and current_tree.mode != mode:
                    from wlanpi_fpms2.state.menu_tree import build_menu_tree
                    timezones = getattr(app.state, "timezones", [])
                    app.state.menu_tree = build_menu_tree(mode=mode, timezones=timezones)
                    log.info(
                        "Menu tree rebuilt: mode changed %s → %s",
                        current_tree.mode, mode,
                    )

            # Device stats (IP address, CPU temp)
            cpu_temp: float | None = None
            try:
                stats = await core_client.get_device_stats()
                primary_ip = stats.ip
                # cpu_temp comes as a string like "45.0" from wlanpi-core
                if stats.cpu_temp:
                    try:
                        cpu_temp = float(stats.cpu_temp.rstrip("°C "))
                    except (ValueError, AttributeError):
                        pass
            except Exception:
                primary_ip = ""

            # WLAN interfaces
            try:
                wlan_resp = await core_client.get_wlan_interfaces()
                wlan_interfaces = [
                    WlanIfaceModel(name=w.interface) for w in wlan_resp.interfaces
                ]
            except Exception:
                wlan_interfaces = []

            # Bluetooth power state
            try:
                bt = await core_client.get_bluetooth_status()
                bluetooth_on = bt.power.lower() in ("on", "yes", "true", "powered")
            except Exception:
                bluetooth_on = False

            # Profiler status (also grab SSID/passphrase for home QR)
            profiler_active = False
            profiler_ssid: str | None = None
            profiler_passphrase: str | None = None
            try:
                prof_status = await core_client.get_profiler_status()
                profiler_active = prof_status.running
                if prof_status.running and prof_status.ssid:
                    profiler_ssid = prof_status.ssid
                    profiler_passphrase = prof_status.passphrase
            except Exception:
                pass

            # Battery
            battery = None
            try:
                from wlanpi_fpms2.state.models import BatteryData
                bat = await core_client.get_battery()
                battery = BatteryData(
                    present=bat.present,
                    charging=bat.status.lower() == "charging" if bat.status else False,
                    level_pct=bat.charge_pct,
                    voltage_mv=int(bat.voltage_v * 1000) if bat.voltage_v else None,
                )
            except Exception:
                pass

            # Hotspot SSID/passphrase (for home QR in non-classic modes)
            hotspot_ssid: str | None = None
            hotspot_passphrase: str | None = None
            if mode != "classic":
                try:
                    creds = await core_client.get_ssid_passphrase()
                    hotspot_ssid = creds.ssid
                    hotspot_passphrase = creds.passphrase
                except Exception:
                    pass

            # Network interfaces (secondary IPs + eth0 carrier)
            secondary_ips: list[dict] = []
            eth_carrier = False
            try:
                ifaces = await core_client.get_interfaces()
                for group in ifaces.values():
                    for iface in group:
                        if iface.name == "eth0":
                            eth_carrier = iface.state == "UP"
                        elif iface.name in ("eth1", "usb0", "usb1", "pan0") and iface.ipv4:
                            secondary_ips.append(
                                {"name": iface.name, "ip": iface.ipv4}
                            )
            except Exception:
                pass

            # Reachability (cached — only re-run after TTL expires)
            if now - _last_reachability_at > _REACHABILITY_TTL:
                try:
                    reach = await core_client.get_reachability()
                    _last_reachability = reach.browse_google.upper() == "OK"
                    _last_reachability_at = now
                except Exception:
                    _last_reachability = None

            time_str = datetime.datetime.now().strftime("%H:%M")

            # Alerts
            alerts: list[str] = []
            if not wlan_interfaces:
                alerts.append("NO WI-FI ADAPTER")
            if profiler_active:
                alerts.append("PROFILER ACTIVE")

            homepage = HomepageData(
                mode=mode,
                hostname=hostname,
                primary_ip=primary_ip,
                primary_interface="wlan0" if mode == "hotspot" else "eth0",
                eth_carrier=eth_carrier,
                secondary_ips=secondary_ips,
                wlan_interfaces=wlan_interfaces,
                bluetooth_on=bluetooth_on,
                profiler_active=profiler_active,
                battery=battery,
                cpu_temp=cpu_temp,
                reachable=_last_reachability,
                time_str=time_str,
                alerts=alerts,
                profiler_ssid=profiler_ssid,
                profiler_passphrase=profiler_passphrase,
                hotspot_ssid=hotspot_ssid,
                hotspot_passphrase=hotspot_passphrase,
            )

            # Wake screen if eth0 carrier changed
            prev_homepage = store.snapshot().homepage
            if prev_homepage.eth_carrier != eth_carrier:
                await store.wake_screen()

            await store.set_homepage(homepage)

        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Error in homepage_refresh_loop")


async def profiler_notification_loop(store: "FpmsStateStore") -> None:
    """Watch for newly profiled devices and show a popup notification."""
    from wlanpi_fpms2.state.models import AlertContent, PageContent

    last_mtime: float | None = None

    while True:
        try:
            await asyncio.sleep(2)

            try:
                st = os.stat(_PROFILER_LAST_PROFILE)
                mtime = st.st_mtime
            except FileNotFoundError:
                last_mtime = None
                continue

            if last_mtime is None:
                last_mtime = mtime
                continue

            if mtime != last_mtime:
                last_mtime = mtime
                try:
                    with open(_PROFILER_LAST_PROFILE) as f:
                        mac = f.read().strip()
                except Exception:
                    mac = "unknown"

                log.info("New device profiled: %s", mac)
                page = PageContent(
                    title="Device Profiled",
                    lines=[mac],
                    alert=AlertContent(
                        level="popup",
                        message=f"Profiled: {mac}",
                        dismiss_after_ms=5000,
                    ),
                )
                await store.set_alert_overlay(page)

        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Error in profiler_notification_loop")
