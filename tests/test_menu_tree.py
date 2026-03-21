"""Tests for the pure-data menu tree."""

import pytest
from wlanpi_fpms2.state.menu_tree import build_menu_tree, MenuTree


def test_classic_tree_has_expected_roots():
    tree = build_menu_tree(mode="classic")
    assert tree.roots == ["network", "bluetooth", "utils", "modes", "apps", "system"]


def test_hotspot_tree_has_no_apps():
    tree = build_menu_tree(mode="hotspot")
    # Apps is not in the root list for non-classic modes
    assert "apps" not in tree.roots
    # The apps node still exists in the index (with hidden_in_mode set)
    assert "apps" in tree.index
    assert tree.index["apps"].hidden_in_mode == ["hotspot", "server", "bridge"]


def test_hotspot_mode_shows_single_classic_mode_option():
    tree = build_menu_tree(mode="hotspot")
    modes_node = tree.index["modes"]
    assert modes_node.name == "Mode"
    assert "modes.classic" in modes_node.children


def test_classic_mode_shows_full_modes_menu():
    tree = build_menu_tree(mode="classic")
    modes_node = tree.index["modes"]
    assert modes_node.name == "Modes"
    assert "modes.hotspot" in modes_node.children
    assert "modes.server" in modes_node.children
    assert "modes.bridge" in modes_node.children


def test_ssid_passphrase_hidden_in_classic():
    tree = build_menu_tree(mode="classic")
    node = tree.index["utils.ssid_passphrase"]
    assert "classic" in node.hidden_in_mode


def test_leaf_nodes_have_action_ids():
    tree = build_menu_tree(mode="classic")
    # Check a sampling of leaf nodes
    leaf_ids = [
        "network.interfaces",
        "bluetooth.status",
        "utils.reachability",
        "apps.profiler.status",
        "system.about",
        "system.reboot.confirm",
    ]
    for lid in leaf_ids:
        node = tree.index.get(lid)
        assert node is not None, f"Missing node: {lid}"
        assert node.action_id is not None, f"Missing action_id on leaf: {lid}"
        assert not node.children, f"Leaf should have no children: {lid}"


def test_branch_nodes_have_no_action_id():
    tree = build_menu_tree(mode="classic")
    branch_ids = ["network", "bluetooth", "utils", "apps", "system", "system.settings"]
    for bid in branch_ids:
        node = tree.index.get(bid)
        assert node is not None, f"Missing node: {bid}"
        assert node.action_id is None, f"Branch should not have action_id: {bid}"
        assert node.children, f"Branch should have children: {bid}"


def test_resolve_path_finds_correct_node():
    tree = build_menu_tree(mode="classic")
    # path [0] → "network"
    node = tree.resolve_path([0])
    assert node is not None
    assert node.id == "network"

    # path [0, 0] → "network.interfaces"
    node = tree.resolve_path([0, 0])
    assert node is not None
    assert node.id == "network.interfaces"


def test_resolve_path_out_of_bounds_returns_none():
    tree = build_menu_tree(mode="classic")
    assert tree.resolve_path([99]) is None
    assert tree.resolve_path([0, 99]) is None


def test_timezone_children_built_from_list():
    timezones = [
        {"country": "US", "timezones": ["America/New_York", "America/Chicago"]},
        {"country": "DE", "timezones": ["Europe/Berlin"]},
    ]
    tree = build_menu_tree(mode="classic", timezones=timezones)
    # The manual timezone node should have two country children
    manual_node = tree.index["system.settings.datetime.tz.manual"]
    assert len(manual_node.children) == 2
    # Each country child should have timezone leaves
    us_node_id = manual_node.children[0]
    us_node = tree.index[us_node_id]
    assert len(us_node.children) == 2


def test_profiler_other_submenu_exists():
    tree = build_menu_tree(mode="classic")
    other = tree.index["apps.profiler.other"]
    assert len(other.children) == 5
    assert "apps.profiler.other.2_4" in other.children


def test_all_action_ids_in_registry_map():
    """Ensure every action_id in the tree has a corresponding stub."""
    from wlanpi_fpms2.actions.stubs import build_stub_registry
    tree = build_menu_tree(mode="classic")
    registry = build_stub_registry()
    missing = []
    for node in tree.index.values():
        if node.action_id and node.action_id != "system.timezone.set":
            if node.action_id not in registry:
                missing.append(node.action_id)
    assert missing == [], f"Action IDs not in registry: {missing}"
