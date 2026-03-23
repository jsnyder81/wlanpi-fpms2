"""Background periodic tasks for the fpms2 state service.

Tasks:
- expire_complications: remove stale complications every 5 seconds
- homepage_refresh: refresh homepage data from wlanpi-core every 5 seconds
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wlanpi_fpms2.core_client.client import CoreApiClient
    from wlanpi_fpms2.state.store import FpmsStateStore

log = logging.getLogger(__name__)

_REFRESH_INTERVAL = 5.0    # seconds between homepage polls
_REACHABILITY_TTL = 60.0   # seconds to cache reachability result


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

            # Device stats (IP address)
            try:
                stats = await core_client.get_device_stats()
                primary_ip = stats.ip
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

            # Profiler status
            try:
                svc = await core_client.get_service_status("wlanpi-profiler")
                profiler_active = svc.active
            except Exception:
                profiler_active = False

            # Reachability (cached — only re-run after TTL expires)
            if now - _last_reachability_at > _REACHABILITY_TTL:
                try:
                    reach = await core_client.get_reachability()
                    _last_reachability = reach.browse_google.upper() == "OK"
                    _last_reachability_at = now
                except Exception:
                    _last_reachability = None

            time_str = datetime.datetime.now().strftime("%H:%M")

            homepage = HomepageData(
                mode=mode,
                hostname=hostname,
                primary_ip=primary_ip,
                wlan_interfaces=wlan_interfaces,
                bluetooth_on=bluetooth_on,
                profiler_active=profiler_active,
                reachable=_last_reachability,
                time_str=time_str,
            )

            await store.set_homepage(homepage)

        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Error in homepage_refresh_loop")
