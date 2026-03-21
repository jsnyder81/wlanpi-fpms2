"""Pure-data menu tree for fpms2.

The menu tree is a flat dict of ``MenuNode`` objects keyed by ID.
Leaf nodes have ``action_id`` set; branch nodes have ``children``.
No functions, no g_vars, no rendering dependencies.

build_menu_tree(mode, timezones) returns:
  - index:  dict[str, MenuNode]   — all nodes by ID
  - roots:  list[str]             — top-level node IDs in display order
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wlanpi_fpms2.state.models import MenuNode


@dataclass
class MenuTree:
    index: dict[str, MenuNode] = field(default_factory=dict)
    roots: list[str] = field(default_factory=list)

    def node(self, node_id: str) -> MenuNode | None:
        return self.index.get(node_id)

    def children_of(self, node_id: str) -> list[MenuNode]:
        node = self.index.get(node_id)
        if node is None:
            return []
        return [self.index[c] for c in node.children if c in self.index]

    def resolve_path(self, path: list[int]) -> MenuNode | None:
        """Resolve a navigation path (list of indices) to the pointed-to node."""
        if not path:
            return None
        current_ids = self.roots
        node: MenuNode | None = None
        for idx in path:
            if idx >= len(current_ids):
                return None
            node = self.index.get(current_ids[idx])
            if node is None:
                return None
            current_ids = node.children
        return node

    def siblings_of_path(self, path: list[int]) -> list[str]:
        """Return sibling IDs at the current path level."""
        if not path:
            return self.roots
        parent_path = path[:-1]
        if not parent_path:
            return self.roots
        current_ids = self.roots
        for idx in parent_path:
            if idx >= len(current_ids):
                return []
            node = self.index.get(current_ids[idx])
            if node is None:
                return []
            current_ids = node.children
        return current_ids


def _add(
    tree: MenuTree,
    node_id: str,
    name: str,
    children: list[str] | None = None,
    action_id: str | None = None,
    hidden_in_mode: list[str] | None = None,
    visible_in_mode: list[str] | None = None,
) -> MenuNode:
    node = MenuNode(
        id=node_id,
        name=name,
        children=children or [],
        action_id=action_id,
        hidden_in_mode=hidden_in_mode or [],
        visible_in_mode=visible_in_mode or [],
    )
    tree.index[node_id] = node
    return node


def build_menu_tree(
    mode: str = "classic",
    timezones: list[dict] | None = None,
) -> MenuTree:
    """Build the complete menu tree for the given device mode.

    Args:
        mode: Device mode ("classic", "hotspot", "server", "bridge").
        timezones: List of {"country": str, "timezones": [str, ...]} dicts.
                   Used to populate the timezone selection submenu.

    Returns:
        MenuTree with .index (all nodes) and .roots (top-level IDs).
    """
    tree = MenuTree()

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------
    _add(tree, "network.interfaces",       "Interfaces",      action_id="network.interfaces")
    _add(tree, "network.wlan_interfaces",  "WLAN Interfaces", action_id="network.wlan_interfaces")
    _add(tree, "network.eth0_ipconfig",    "Eth0 IP Config",  action_id="network.eth0_ipconfig")
    _add(tree, "network.eth0_vlan",        "Eth0 VLAN",       action_id="network.eth0_vlan")
    _add(tree, "network.lldp",             "LLDP Neighbour",  action_id="network.lldp")
    _add(tree, "network.cdp",              "CDP Neighbour",   action_id="network.cdp")
    _add(tree, "network.publicip4",        "Public IPv4",     action_id="network.publicip4")
    _add(tree, "network.publicip6",        "Public IPv6",     action_id="network.publicip6")
    _add(tree, "network", "Network", children=[
        "network.interfaces",
        "network.wlan_interfaces",
        "network.eth0_ipconfig",
        "network.eth0_vlan",
        "network.lldp",
        "network.cdp",
        "network.publicip4",
        "network.publicip6",
    ])

    # ------------------------------------------------------------------
    # Bluetooth
    # ------------------------------------------------------------------
    _add(tree, "bluetooth.status",  "Status",      action_id="bluetooth.status")
    _add(tree, "bluetooth.on",      "Turn On",     action_id="bluetooth.on")
    _add(tree, "bluetooth.off",     "Turn Off",    action_id="bluetooth.off")
    _add(tree, "bluetooth.pair",    "Pair Device", action_id="bluetooth.pair")
    _add(tree, "bluetooth", "Bluetooth", children=[
        "bluetooth.status",
        "bluetooth.on",
        "bluetooth.off",
        "bluetooth.pair",
    ])

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------
    _add(tree, "utils.reachability",       "Reachability",   action_id="utils.reachability")

    # Speedtest sub-menu
    _add(tree, "utils.speedtest.run",      "Run Test",       action_id="utils.speedtest")
    _add(tree, "utils.speedtest", "Speedtest", children=["utils.speedtest.run"])

    # Cloud tests sub-menu
    _add(tree, "utils.cloud.arista",    "Arista CV-CUE",    action_id="utils.cloud.arista")
    _add(tree, "utils.cloud.aruba",     "Aruba Central",    action_id="utils.cloud.aruba")
    _add(tree, "utils.cloud.extreme",   "ExtremeCloud IQ",  action_id="utils.cloud.extreme")
    _add(tree, "utils.cloud.meraki",    "Meraki Cloud",     action_id="utils.cloud.meraki")
    _add(tree, "utils.cloud.mist",      "Mist Cloud",       action_id="utils.cloud.mist")
    _add(tree, "utils.cloud.ruckus",    "RUCKUS Cloud",     action_id="utils.cloud.ruckus")
    _add(tree, "utils.cloud", "Cloud Tests", children=[
        "utils.cloud.arista",
        "utils.cloud.aruba",
        "utils.cloud.extreme",
        "utils.cloud.meraki",
        "utils.cloud.mist",
        "utils.cloud.ruckus",
    ])

    # Port blinker sub-menu
    _add(tree, "utils.blinker.start",   "Start", action_id="utils.port_blinker.start")
    _add(tree, "utils.blinker.stop",    "Stop",  action_id="utils.port_blinker.stop")
    _add(tree, "utils.blinker", "Port Blinker", children=[
        "utils.blinker.start",
        "utils.blinker.stop",
    ])

    # SSID/Passphrase — only visible in non-classic modes
    _add(tree, "utils.ssid_passphrase", "SSID/Passphrase",
         action_id="utils.ssid_passphrase",
         hidden_in_mode=["classic"])

    _add(tree, "utils.usb",  "USB Devices", action_id="utils.usb")
    _add(tree, "utils.ufw",  "UFW Ports",   action_id="utils.ufw")

    _add(tree, "utils", "Utils", children=[
        "utils.reachability",
        "utils.speedtest",
        "utils.cloud",
        "utils.blinker",
        "utils.ssid_passphrase",
        "utils.usb",
        "utils.ufw",
    ])

    # ------------------------------------------------------------------
    # Modes  (classic mode shows full switcher; non-classic shows "→ Classic")
    # ------------------------------------------------------------------
    if mode == "classic":
        _add(tree, "modes.hotspot.confirm",  "Confirm", action_id="modes.hotspot")
        _add(tree, "modes.hotspot",  "Hotspot", children=["modes.hotspot.confirm"])
        _add(tree, "modes.server.confirm",   "Confirm", action_id="modes.server")
        _add(tree, "modes.server",   "Server",  children=["modes.server.confirm"])
        _add(tree, "modes.bridge.confirm",   "Confirm", action_id="modes.bridge")
        _add(tree, "modes.bridge",   "Bridge",  children=["modes.bridge.confirm"])
        _add(tree, "modes", "Modes", children=[
            "modes.hotspot",
            "modes.server",
            "modes.bridge",
        ])
    else:
        _add(tree, "modes.classic.confirm", "Confirm", action_id="modes.classic")
        _add(tree, "modes.classic", "Classic Mode", children=["modes.classic.confirm"])
        _add(tree, "modes", "Mode", children=["modes.classic"])

    # ------------------------------------------------------------------
    # Apps  (hidden in non-classic modes)
    # ------------------------------------------------------------------
    _add(tree, "apps.kismet.start", "Start", action_id="apps.kismet.start")
    _add(tree, "apps.kismet.stop",  "Stop",  action_id="apps.kismet.stop")
    _add(tree, "apps.kismet", "Kismet", children=["apps.kismet.start", "apps.kismet.stop"])

    # Profiler sub-menu
    _add(tree, "apps.profiler.status",  "Status",  action_id="apps.profiler.status")
    _add(tree, "apps.profiler.stop",    "Stop",    action_id="apps.profiler.stop")
    _add(tree, "apps.profiler.start",   "Start",   action_id="apps.profiler.start")

    _add(tree, "apps.profiler.other.2_4",    "Start 2.4 GHz",   action_id="apps.profiler.start_2_4")
    _add(tree, "apps.profiler.other.5_36",   "Start 5 GHz 36",  action_id="apps.profiler.start_5_36")
    _add(tree, "apps.profiler.other.5_149",  "Start 5 GHz 149", action_id="apps.profiler.start_5_149")
    _add(tree, "apps.profiler.other.no11r",  "Start (no 11r)",  action_id="apps.profiler.start_no11r")
    _add(tree, "apps.profiler.other.no11ax", "Start (no 11ax)", action_id="apps.profiler.start_no11ax")
    _add(tree, "apps.profiler.other", "Start Other", children=[
        "apps.profiler.other.2_4",
        "apps.profiler.other.5_36",
        "apps.profiler.other.5_149",
        "apps.profiler.other.no11r",
        "apps.profiler.other.no11ax",
    ])

    _add(tree, "apps.profiler.purge_reports.confirm", "Confirm",
         action_id="apps.profiler.purge_reports")
    _add(tree, "apps.profiler.purge_reports", "Purge Reports",
         children=["apps.profiler.purge_reports.confirm"])

    _add(tree, "apps.profiler.purge_files.confirm", "Confirm",
         action_id="apps.profiler.purge_files")
    _add(tree, "apps.profiler.purge_files", "Purge Files",
         children=["apps.profiler.purge_files.confirm"])

    _add(tree, "apps.profiler", "Profiler", children=[
        "apps.profiler.status",
        "apps.profiler.stop",
        "apps.profiler.start",
        "apps.profiler.other",
        "apps.profiler.purge_reports",
        "apps.profiler.purge_files",
    ])

    # Scanner sub-menu
    _add(tree, "apps.scanner.scan",         "Scan",             action_id="apps.scanner.scan")
    _add(tree, "apps.scanner.nohidden",     "Scan (no hidden)", action_id="apps.scanner.scan_nohidden")
    _add(tree, "apps.scanner.csv",          "Scan to CSV",      action_id="apps.scanner.csv")
    _add(tree, "apps.scanner.pcap.start",   "Start",            action_id="apps.scanner.pcap_start")
    _add(tree, "apps.scanner.pcap.stop",    "Stop",             action_id="apps.scanner.pcap_stop")
    _add(tree, "apps.scanner.pcap", "Scan to PCAP", children=[
        "apps.scanner.pcap.start",
        "apps.scanner.pcap.stop",
    ])
    _add(tree, "apps.scanner", "Scanner", children=[
        "apps.scanner.scan",
        "apps.scanner.nohidden",
        "apps.scanner.csv",
        "apps.scanner.pcap",
    ])

    apps_children: list[str] = []
    if mode == "classic":
        apps_children = ["apps.kismet", "apps.profiler", "apps.scanner"]
    _add(tree, "apps", "Apps", children=apps_children,
         hidden_in_mode=["hotspot", "server", "bridge"])

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------
    _add(tree, "system.about",   "About",   action_id="system.about")
    _add(tree, "system.help",    "Help",    action_id="system.help")
    _add(tree, "system.summary", "Summary", action_id="system.summary")
    _add(tree, "system.battery", "Battery", action_id="system.battery")

    # Settings > Date & Time
    _add(tree, "system.settings.datetime.show",
         "Show Time & Zone", action_id="system.date")
    _add(tree, "system.settings.datetime.tz.auto",
         "Auto", action_id="system.timezone.auto")

    # Build timezone submenu from provided list
    tz_country_ids: list[str] = []
    for country_data in (timezones or []):
        country = country_data.get("country", "")
        tzlist = country_data.get("timezones", [])
        safe_country = country.lower().replace(" ", "_").replace("/", "_")
        country_node_id = f"system.settings.datetime.tz.manual.{safe_country}"
        tz_leaf_ids: list[str] = []
        for tz in tzlist:
            safe_tz = tz.lower().replace("/", ".").replace(" ", "_")
            leaf_id = f"{country_node_id}.{safe_tz}"
            _add(tree, leaf_id, tz, action_id="system.timezone.set",
                 # Store the TZ string in the name; router extracts it from path
                 )
            tz_leaf_ids.append(leaf_id)
        _add(tree, country_node_id, country, children=tz_leaf_ids)
        tz_country_ids.append(country_node_id)

    _add(tree, "system.settings.datetime.tz.manual",
         "Manual", children=tz_country_ids)
    _add(tree, "system.settings.datetime.tz",
         "Set Timezone", children=[
             "system.settings.datetime.tz.auto",
             "system.settings.datetime.tz.manual",
         ])
    _add(tree, "system.settings.datetime",
         "Date & Time", children=[
             "system.settings.datetime.show",
             "system.settings.datetime.tz",
         ])

    # Settings > RF Domain
    _add(tree, "system.settings.rf.show",   "Show Domain",    action_id="system.reg_domain.show")

    rf_domains = [
        ("us", "Set Domain US"),
        ("br", "Set Domain BR"),
        ("ca", "Set Domain CA"),
        ("cz", "Set Domain CZ"),
        ("de", "Set Domain DE"),
        ("fr", "Set Domain FR"),
        ("gb", "Set Domain GB"),
        ("nl", "Set Domain NL"),
        ("no", "Set Domain NO"),
    ]
    rf_domain_ids: list[str] = ["system.settings.rf.show"]
    for code, label in rf_domains:
        confirm_id = f"system.settings.rf.{code}.confirm"
        parent_id = f"system.settings.rf.{code}"
        _add(tree, confirm_id, "Confirm & Reboot", action_id=f"system.reg_domain.set_{code}")
        _add(tree, parent_id, label, children=[confirm_id])
        rf_domain_ids.append(parent_id)

    _add(tree, "system.settings.rf", "RF Domain", children=rf_domain_ids)

    _add(tree, "system.settings.rotate", "Rotate Display",
         action_id="system.rotate_display")
    _add(tree, "system.settings", "Settings", children=[
        "system.settings.datetime",
        "system.settings.rf",
        "system.settings.rotate",
    ])

    # System > Updates
    _add(tree, "system.updates.check",   "Check Updates",   action_id="system.updates.check")
    _add(tree, "system.updates.install.confirm", "Confirm", action_id="system.updates.install")
    _add(tree, "system.updates.install", "Install Updates", children=["system.updates.install.confirm"])
    _add(tree, "system.updates", "Updates", children=[
        "system.updates.check",
        "system.updates.install",
    ])

    # Reboot / Shutdown
    _add(tree, "system.reboot.confirm",   "Confirm", action_id="system.reboot")
    _add(tree, "system.reboot",   "Reboot",   children=["system.reboot.confirm"])
    _add(tree, "system.shutdown.confirm", "Confirm", action_id="system.shutdown")
    _add(tree, "system.shutdown", "Shutdown", children=["system.shutdown.confirm"])

    _add(tree, "system", "System", children=[
        "system.about",
        "system.help",
        "system.summary",
        "system.battery",
        "system.settings",
        "system.updates",
        "system.reboot",
        "system.shutdown",
    ])

    # ------------------------------------------------------------------
    # Root nodes (mode-dependent)
    # ------------------------------------------------------------------
    if mode == "classic":
        tree.roots = ["network", "bluetooth", "utils", "modes", "apps", "system"]
    else:
        # Non-classic: no Apps, Mode shows single "Classic Mode" option
        tree.roots = ["network", "bluetooth", "utils", "modes", "system"]

    return tree
