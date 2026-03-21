"""Base types for fpms2 actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from wlanpi_fpms2.state.models import PageContent

if TYPE_CHECKING:
    from wlanpi_fpms2.state.store import FpmsStateStore


@dataclass
class ActionContext:
    """Passed to every action handler."""
    store: "FpmsStateStore"
    core_client: object | None = None  # CoreApiClient (Phase 2+)
