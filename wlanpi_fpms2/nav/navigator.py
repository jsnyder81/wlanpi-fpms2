"""Pure navigation logic for fpms2.

handle_input(state, event, tree) -> (new_nav, action_id | None)

This module is free of side effects: it takes the current state and an
input event and returns what the new navigation should be, plus an optional
action_id to dispatch. The caller (router) applies the changes to the store.
"""

from __future__ import annotations

from dataclasses import dataclass

from wlanpi_fpms2.state.models import (
    DisplayState,
    FpmsState,
    InputEvent,
    NavLocation,
)
from wlanpi_fpms2.state.menu_tree import MenuTree


@dataclass
class NavResult:
    nav: NavLocation
    action_id: str | None = None   # set when a leaf action should be dispatched
    scroll_delta: int = 0          # +1 / -1 for paged-table scroll


def handle_input(
    state: FpmsState,
    event: InputEvent,
    tree: MenuTree,
) -> NavResult:
    """Compute the navigation result for a button press.

    All inputs are blocked when ``state.loading`` is True, except ``left``
    (which cancels the running action and returns to the menu).
    """
    button = event.button
    nav = state.nav.model_copy(deep=True)
    display_state = nav.display_state

    # Loading guard — only "left" gets through
    if state.loading and button != "left":
        return NavResult(nav=nav)

    # key1/key2/key3 shortcuts — not implemented yet, ignore
    if button in ("key1", "key2", "key3"):
        return NavResult(nav=nav)

    # ------------------------------------------------------------------
    # Home page
    # ------------------------------------------------------------------
    if display_state == "home":
        if button in ("down", "right", "center"):
            # Enter the top-level menu
            nav.display_state = "menu"
            nav.path = [0]
            return NavResult(nav=nav)
        if button == "up":
            # Toggle alternate home page — no nav change, but we signal it
            # via a special no-op (the store/router will handle alt toggle)
            return NavResult(nav=nav)
        return NavResult(nav=nav)

    # ------------------------------------------------------------------
    # Menu navigation
    # ------------------------------------------------------------------
    if display_state == "menu":
        current_node = tree.resolve_path(nav.path)
        siblings = tree.siblings_of_path(nav.path)
        current_idx = nav.path[-1] if nav.path else 0

        if button == "down":
            next_idx = (current_idx + 1) % len(siblings) if siblings else 0
            nav.path = nav.path[:-1] + [next_idx]
            return NavResult(nav=nav)

        if button == "up":
            next_idx = (current_idx - 1) % len(siblings) if siblings else 0
            nav.path = nav.path[:-1] + [next_idx]
            return NavResult(nav=nav)

        if button == "left":
            if len(nav.path) <= 1:
                # Back to home from top-level menu
                nav.display_state = "home"
                nav.path = [0]
            else:
                nav.path = nav.path[:-1]
            return NavResult(nav=nav)

        if button in ("right", "center"):
            if current_node is None:
                return NavResult(nav=nav)
            if current_node.children:
                # Enter submenu
                nav.path = nav.path + [0]
                return NavResult(nav=nav)
            if current_node.action_id:
                # Leaf: dispatch action, transition to page
                nav.display_state = "page"
                return NavResult(nav=nav, action_id=current_node.action_id)
            return NavResult(nav=nav)

    # ------------------------------------------------------------------
    # Page (action result displayed)
    # ------------------------------------------------------------------
    if display_state == "page":
        if button == "left":
            # Back to menu at current path (without popping — stay where we were)
            nav.display_state = "menu"
            return NavResult(nav=nav)

        if button == "down":
            return NavResult(nav=nav, scroll_delta=+1)

        if button == "up":
            return NavResult(nav=nav, scroll_delta=-1)

        # right/center while on a page re-runs the action (refresh)
        if button in ("right", "center"):
            current_node = tree.resolve_path(nav.path)
            if current_node and current_node.action_id:
                return NavResult(nav=nav, action_id=current_node.action_id)

        return NavResult(nav=nav)

    return NavResult(nav=nav)


def navigate_to_node(state: FpmsState, node_id: str, tree: MenuTree) -> NavResult:
    """Jump directly to a node by ID without simulating button presses.

    Branch node → enter its submenu (first child selected).
    Leaf node   → select it and return action_id for dispatch.
    Returns the unchanged nav if node_id is not found.
    """
    path = tree.find_path(node_id)
    if path is None:
        return NavResult(nav=state.nav.model_copy(deep=True))

    node = tree.index.get(node_id)
    if node is None:
        return NavResult(nav=state.nav.model_copy(deep=True))

    nav = state.nav.model_copy(deep=True)

    if node.children:
        # Branch: enter the submenu with the first child selected
        nav.path = path + [0]
        nav.display_state = "menu"
        return NavResult(nav=nav)

    if node.action_id:
        # Leaf: navigate to it and dispatch its action
        nav.path = path
        nav.display_state = "page"
        return NavResult(nav=nav, action_id=node.action_id)

    # Branch with no children or leaf with no action — just select it
    nav.path = path
    nav.display_state = "menu"
    return NavResult(nav=nav)


def path_node_name(path: list[int], tree: MenuTree) -> str:
    """Return the name of the node at the given path, or empty string."""
    node = tree.resolve_path(path)
    return node.name if node else ""


def current_children_names(nav: NavLocation, tree: MenuTree) -> list[str]:
    """Return display names of siblings at current nav level (for rendering)."""
    siblings = tree.siblings_of_path(nav.path)
    return [tree.index[sid].name for sid in siblings if sid in tree.index]
