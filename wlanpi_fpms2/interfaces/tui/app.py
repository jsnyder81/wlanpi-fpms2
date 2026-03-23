"""Textual TUI for wlanpi-fpms2.

Connects to the state service WebSocket, receives FpmsState updates,
and renders navigation/content via Textual widgets.

Keyboard bindings:
  ↑ / ↓      → up / down (navigate menu / scroll page)
  ←           → left (back)
  → / Enter   → right / center (select)
  F1-F3       → key1 / key2 / key3
  q           → quit

Entry point: wlanpi-fpms2-tui (defined in pyproject.toml)

Environment variables:
  WLANPI_STATE_URL   Base URL of state service (default: http://127.0.0.1:8765)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ContentSwitcher, Footer, LoadingIndicator, Static

from wlanpi_fpms2.state.menu_tree import MenuTree, build_menu_tree
from wlanpi_fpms2.state.models import FpmsState

log = logging.getLogger(__name__)

_DEFAULT_STATE_URL = "http://127.0.0.1:8765"
_RECONNECT_DELAY = 2.0


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class StatusBar(Widget):
    """Single-line header: hostname | IP | mode | time | loading indicator."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        layout: horizontal;
    }
    StatusBar Static {
        width: 1fr;
    }
    StatusBar #status-right {
        text-align: right;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("wlanpi-fpms2", id="status-left")
        yield Static("", id="status-right")

    def update_from_state(self, state: FpmsState) -> None:
        hp = state.homepage
        left_parts: list[str] = []
        right_parts: list[str] = []

        if hp:
            left_parts.append(hp.hostname or "wlanpi")
            if hp.primary_ip:
                left_parts.append(hp.primary_ip)
            if hp.mode and hp.mode != "classic":
                left_parts.append(f"[{hp.mode.upper()}]")
            if hp.bluetooth_on:
                left_parts.append("BT")
            if hp.profiler_active:
                left_parts.append("Profiler")
            if hp.wlan_interfaces:
                left_parts.append(f"WiFi×{len(hp.wlan_interfaces)}")
            if hp.mode == "hotspot" and hp.client_count is not None:
                left_parts.append(f"Clients:{hp.client_count}")
            if hp.battery and hp.battery.present:
                batt = hp.battery
                charge = f"{batt.level_pct}%" if batt.level_pct is not None else "?"
                icon = "⚡" if batt.charging else "🔋"
                right_parts.append(f"{icon}{charge}")
            if hp.cpu_temp is not None and hp.cpu_temp >= 70:
                right_parts.append(f"🌡{hp.cpu_temp:.0f}°C")
            if hp.time_str:
                right_parts.append(hp.time_str)

        if state.loading:
            right_parts.append("[blink]Loading...[/blink]")

        self.query_one("#status-left", Static).update("  |  ".join(left_parts))
        self.query_one("#status-right", Static).update("  ".join(right_parts))


class HomepagePanel(Widget):
    """Home screen panel showing device summary."""

    DEFAULT_CSS = """
    HomepagePanel {
        height: 100%;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Connecting to state service...", id="home-content")

    def update_from_state(self, state: FpmsState) -> None:
        hp = state.homepage
        if hp is None:
            self.query_one("#home-content", Static).update("Connecting...")
            return

        reachable_str = (
            "[green]Yes[/green]" if hp.reachable
            else "[red]No[/red]" if hp.reachable is not None
            else "[dim]Unknown[/dim]"
        )

        # Battery
        if hp.battery and hp.battery.present:
            charge = f"{hp.battery.level_pct}%" if hp.battery.level_pct is not None else "?"
            batt_status = "Charging" if hp.battery.charging else charge
            batt_str = f"[green]{batt_status}[/green]" if hp.battery.charging else charge
        else:
            batt_str = "[dim]N/A[/dim]"

        # Temperature
        if hp.cpu_temp is not None:
            if hp.cpu_temp >= 80:
                temp_str = f"[red]{hp.cpu_temp:.0f}°C[/red]"
            elif hp.cpu_temp >= 70:
                temp_str = f"[yellow]{hp.cpu_temp:.0f}°C[/yellow]"
            else:
                temp_str = f"{hp.cpu_temp:.0f}°C"
        else:
            temp_str = "[dim]N/A[/dim]"

        # WiFi adapters
        if hp.wlan_interfaces:
            wifi_names = ", ".join(w.name for w in hp.wlan_interfaces)
            wifi_str = f"[green]{wifi_names}[/green]"
        else:
            wifi_str = "[red]None[/red]"

        lines = [
            "[bold]WLANPi FPMS2[/bold]",
            "",
            f"  Hostname:   {hp.hostname}",
            f"  IP:         {hp.primary_ip or 'N/A'}",
            f"  Mode:       {hp.mode.title()}",
            f"  WiFi:       {wifi_str}",
            f"  Bluetooth:  {'[green]On[/green]' if hp.bluetooth_on else '[dim]Off[/dim]'}",
            f"  Battery:    {batt_str}",
            f"  Temp:       {temp_str}",
            f"  Profiler:   {'[green]Active[/green]' if hp.profiler_active else '[dim]Stopped[/dim]'}",
            f"  Reachable:  {reachable_str}",
        ]

        # Secondary IPs
        if hp.secondary_ips:
            lines.append("")
            for sec in hp.secondary_ips:
                lines.append(f"  {sec['name']:10s} {sec['ip']}")

        # Client count (hotspot mode)
        if hp.client_count is not None:
            lines.append(f"  Clients:    {hp.client_count}")

        lines.append("")
        lines.append("[dim]Press → or Enter to open menu[/dim]")

        for alert in hp.alerts:
            lines.append(f"[red]! {alert}[/red]")

        self.query_one("#home-content", Static).update("\n".join(lines))


class MenuPanel(Widget):
    """Menu navigation panel showing current level items with breadcrumb."""

    DEFAULT_CSS = """
    MenuPanel {
        height: 100%;
        padding: 1 2;
    }
    #menu-breadcrumb {
        height: 1;
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="menu-breadcrumb")
        yield Static("", id="menu-items")

    def update_from_state(self, state: FpmsState, tree: MenuTree | None) -> None:
        if tree is None:
            self.query_one("#menu-items", Static).update("[dim]Loading menu...[/dim]")
            return

        path = state.nav.path
        current_idx = path[-1] if path else 0

        # Breadcrumb: ancestors of current level
        crumb_parts: list[str] = []
        for depth in range(len(path) - 1):
            node = tree.resolve_path(path[: depth + 1])
            if node:
                crumb_parts.append(node.name)
        crumb = " › ".join(crumb_parts) if crumb_parts else "Main Menu"
        self.query_one("#menu-breadcrumb", Static).update(f"[dim]{crumb}[/dim]")

        # Siblings at current level
        siblings = tree.siblings_of_path(path)
        lines: list[str] = []
        for i, sid in enumerate(siblings):
            node = tree.index.get(sid)
            if node is None:
                continue
            arrow = "▸ " if node.children else "  "
            if i == current_idx:
                lines.append(f"[bold reverse] {arrow}{node.name} [/bold reverse]")
            else:
                lines.append(f"   {arrow}{node.name}")

        self.query_one("#menu-items", Static).update(
            "\n".join(lines) if lines else "[dim]Empty[/dim]"
        )


class PagePanel(Widget):
    """Action result panel: title, scrollable content lines, loading overlay."""

    DEFAULT_CSS = """
    PagePanel {
        height: 100%;
        layout: vertical;
    }
    #page-title {
        height: 1;
        background: $surface;
        padding: 0 2;
        border-bottom: solid $primary;
    }
    #page-scroll {
        height: 1fr;
        padding: 1 2;
    }
    #page-loading {
        height: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="page-title")
        with ScrollableContainer(id="page-scroll"):
            yield Static("", id="page-content")
        yield LoadingIndicator(id="page-loading")

    def on_mount(self) -> None:
        self.query_one("#page-loading").display = False

    def update_from_state(self, state: FpmsState) -> None:
        loading = self.query_one("#page-loading")
        scroll = self.query_one("#page-scroll")

        if state.loading:
            loading.display = True
            scroll.display = False
            self.query_one("#page-title", Static).update("[dim]Loading...[/dim]")
            return

        loading.display = False
        scroll.display = True

        page = state.current_page
        if page is None:
            self.query_one("#page-title", Static).update("")
            self.query_one("#page-content", Static).update("")
            return

        title = f"[bold]{page.title}[/bold]"
        if page.page_count > 1:
            title += f"  [dim]page {page.page_index + 1}/{page.page_count}[/dim]"
        self.query_one("#page-title", Static).update(title)

        content = list(page.lines)
        if page.raw_image_b64:
            content.append("")
            content.append("[dim]QR code available on OLED display and Cockpit[/dim]")
        if page.alert:
            color = {"error": "red", "warning": "yellow", "info": "cyan"}.get(
                page.alert.level, "white"
            )
            content.append("")
            content.append(f"[{color}]{page.alert.message}[/{color}]")

        self.query_one("#page-content", Static).update("\n".join(content))

        # Hint for paged content
        if state.scroll_max > 0:
            hint = f"[dim]↑↓ scroll  ({state.scroll_index + 1}/{state.scroll_max + 1})[/dim]"
            self.query_one("#page-content", Static).update(
                "\n".join(content) + "\n\n" + hint
            )


class ComplicationsBar(Widget):
    """Single-line strip showing active complications. Hidden when empty."""

    DEFAULT_CSS = """
    ComplicationsBar {
        height: 1;
        background: $surface;
        padding: 0 1;
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="complications-text")

    def update_from_state(self, state: FpmsState) -> None:
        if not state.complications:
            self.display = False
            return

        self.display = True
        parts: list[str] = []
        for comp in state.complications:
            color = {"ok": "green", "warning": "yellow", "error": "red"}.get(
                comp.status, "white"
            )
            icon = f"{comp.icon} " if comp.icon and len(comp.icon) == 1 else ""
            parts.append(f"[{color}]{icon}{comp.label}: {comp.value}[/{color}]")

        self.query_one("#complications-text", Static).update("  │  ".join(parts))


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class FpmsTui(App):
    """Textual TUI client for wlanpi-fpms2 state service."""

    TITLE = "WLANPi FPMS2"

    CSS = """
    Screen {
        layout: vertical;
    }
    ContentSwitcher {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("up",    "nav_up",     "Up",     show=False),
        Binding("down",  "nav_down",   "Down",   show=False),
        Binding("left",  "nav_back",   "← Back", show=True),
        Binding("right", "nav_select", "→ Enter", show=True),
        Binding("enter", "nav_center", "Select", show=False),
        Binding("f1",    "nav_key1",   "F1",     show=False),
        Binding("f2",    "nav_key2",   "F2",     show=False),
        Binding("f3",    "nav_key3",   "F3",     show=False),
        Binding("q",     "quit",       "Quit",   show=True),
    ]

    fpms_state: reactive[FpmsState | None] = reactive(None)
    _menu_tree: MenuTree | None = None
    _base_url: str = _DEFAULT_STATE_URL

    def compose(self) -> ComposeResult:
        yield StatusBar()
        with ContentSwitcher(initial="home"):
            yield HomepagePanel(id="home")
            yield MenuPanel(id="menu")
            yield PagePanel(id="page")
        yield ComplicationsBar()
        yield Footer()

    def on_mount(self) -> None:
        self._base_url = os.environ.get("WLANPI_STATE_URL", _DEFAULT_STATE_URL)
        self.ws_listener()

    def watch_fpms_state(self, state: FpmsState | None) -> None:
        if state is None:
            return

        # Switch the visible panel
        switcher = self.query_one(ContentSwitcher)
        display = state.nav.display_state
        if display == "home":
            switcher.current = "home"
        elif display == "menu":
            switcher.current = "menu"
        else:
            switcher.current = "page"

        # Update each panel
        try:
            self.query_one(StatusBar).update_from_state(state)
            self.query_one(HomepagePanel).update_from_state(state)
            self.query_one(MenuPanel).update_from_state(state, self._menu_tree)
            self.query_one(PagePanel).update_from_state(state)
            self.query_one(ComplicationsBar).update_from_state(state)
        except Exception:
            log.exception("Error updating TUI from state")

    # ------------------------------------------------------------------
    # WebSocket worker
    # ------------------------------------------------------------------

    @work(exclusive=True)
    async def ws_listener(self) -> None:
        """Connect to the state service WebSocket and receive state updates."""
        from websockets.asyncio.client import connect

        ws_url = (
            self._base_url
            .replace("http://", "ws://")
            .replace("https://", "wss://")
            + "/ws"
        )

        # Wait for state service readiness
        async with httpx.AsyncClient(timeout=5.0) as client:
            for _ in range(30):
                try:
                    r = await client.get(f"{self._base_url}/health")
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)

        self._menu_tree = await self._fetch_menu_tree()

        # Reconnect loop
        while True:
            try:
                async with connect(ws_url, ping_interval=20, ping_timeout=30) as ws:
                    log.info("WebSocket connected to %s", ws_url)
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                            if data.get("type") == "ping":
                                continue
                            payload = (
                                data.get("state", data)
                                if data.get("type") == "state"
                                else data
                            )
                            state = FpmsState.model_validate(payload)

                            # Rebuild menu tree if device mode changed
                            current_mode = (
                                state.homepage.mode if state.homepage else "classic"
                            )
                            if self._menu_tree and current_mode != self._menu_tree.mode:
                                self._menu_tree = await self._fetch_menu_tree()

                            self.fpms_state = state

                        except Exception:
                            log.exception("Error processing WebSocket message")

            except Exception as exc:
                log.warning(
                    "WebSocket disconnected: %s — reconnecting in %.0fs",
                    exc,
                    _RECONNECT_DELAY,
                )
                await asyncio.sleep(_RECONNECT_DELAY)
                self._menu_tree = await self._fetch_menu_tree()

    async def _fetch_menu_tree(self) -> MenuTree:
        """Fetch current menu tree from the state service."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                state_r = await client.get(f"{self._base_url}/state")
                state_r.raise_for_status()
                mode = (state_r.json().get("homepage") or {}).get("mode", "classic")

                menu_r = await client.get(f"{self._base_url}/menu")
                menu_r.raise_for_status()
                nodes_data = menu_r.json()

            from wlanpi_fpms2.state.models import MenuNode

            index: dict[str, MenuNode] = {}
            for n in nodes_data:
                node = MenuNode.model_validate(n)
                index[node.id] = node

            local_tree = build_menu_tree(mode=mode)
            for nid, node in index.items():
                local_tree.index[nid] = node
            return local_tree

        except Exception as exc:
            log.warning("Could not fetch menu tree: %s — using local fallback", exc)
            return build_menu_tree()

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    async def _send_button(self, button: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    f"{self._base_url}/input", json={"button": button}
                )
        except Exception:
            log.warning("Failed to send button '%s'", button)

    async def action_nav_up(self) -> None:
        await self._send_button("up")

    async def action_nav_down(self) -> None:
        await self._send_button("down")

    async def action_nav_back(self) -> None:
        await self._send_button("left")

    async def action_nav_select(self) -> None:
        await self._send_button("right")

    async def action_nav_center(self) -> None:
        await self._send_button("center")

    async def action_nav_key1(self) -> None:
        await self._send_button("key1")

    async def action_nav_key2(self) -> None:
        await self._send_button("key2")

    async def action_nav_key3(self) -> None:
        await self._send_button("key3")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    app = FpmsTui()
    app.run()


if __name__ == "__main__":
    main()
