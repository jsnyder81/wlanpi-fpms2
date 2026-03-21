"""Background periodic tasks for the fpms2 state service.

Tasks:
- expire_complications: remove stale complications every 5 seconds
- homepage_refresh: refresh homepage data every 5 seconds (Phase 2+)
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


async def expire_complications_loop(store: "FpmsStateStore") -> None:  # type: ignore[name-defined]
    """Periodically remove complications whose TTL has elapsed."""
    while True:
        try:
            await asyncio.sleep(5)
            await store.expire_complications()
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Error in expire_complications_loop")


async def homepage_refresh_loop(store: "FpmsStateStore", core_client=None) -> None:  # type: ignore[name-defined]
    """Periodically refresh homepage data from wlanpi-core.

    Implemented fully in Phase 2 when core_client is available.
    """
    while True:
        try:
            await asyncio.sleep(5)
            if core_client is None:
                continue
            # Phase 2+: fetch and update homepage data
            # from wlanpi_fpms2.actions.homepage import fetch_homepage_data
            # data = await fetch_homepage_data(core_client)
            # await store.set_homepage(data)
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Error in homepage_refresh_loop")
