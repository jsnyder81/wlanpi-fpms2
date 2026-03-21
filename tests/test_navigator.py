"""Tests for the pure navigation logic."""

import pytest
from wlanpi_fpms2.state.menu_tree import build_menu_tree
from wlanpi_fpms2.state.models import FpmsState, InputEvent, NavLocation
from wlanpi_fpms2.nav.navigator import handle_input, NavResult


@pytest.fixture
def tree():
    return build_menu_tree(mode="classic")


@pytest.fixture
def state_home() -> FpmsState:
    return FpmsState(nav=NavLocation(path=[0], display_state="home"))


@pytest.fixture
def state_menu() -> FpmsState:
    return FpmsState(nav=NavLocation(path=[0], display_state="menu"))


def _press(state: FpmsState, button: str, tree) -> NavResult:
    return handle_input(state, InputEvent(button=button), tree)


class TestHomeNavigation:
    def test_down_from_home_enters_menu(self, state_home, tree):
        result = _press(state_home, "down", tree)
        assert result.nav.display_state == "menu"
        assert result.nav.path == [0]

    def test_right_from_home_enters_menu(self, state_home, tree):
        result = _press(state_home, "right", tree)
        assert result.nav.display_state == "menu"

    def test_center_from_home_enters_menu(self, state_home, tree):
        result = _press(state_home, "center", tree)
        assert result.nav.display_state == "menu"

    def test_up_from_home_stays_home(self, state_home, tree):
        result = _press(state_home, "up", tree)
        assert result.nav.display_state == "home"


class TestMenuNavigation:
    def test_down_wraps_around(self, state_menu, tree):
        # 6 root items (classic): network(0)..system(5)
        state = FpmsState(nav=NavLocation(path=[5], display_state="menu"))
        result = _press(state, "down", tree)
        assert result.nav.path == [0]  # wrapped to first

    def test_down_increments(self, state_menu, tree):
        result = _press(state_menu, "down", tree)
        assert result.nav.path == [1]  # bluetooth

    def test_up_wraps_around(self, state_menu, tree):
        # At first item → wrap to last
        result = _press(state_menu, "up", tree)
        assert result.nav.path[-1] == 5  # last root item (system)

    def test_up_decrements(self, tree):
        state = FpmsState(nav=NavLocation(path=[2], display_state="menu"))
        result = _press(state, "up", tree)
        assert result.nav.path == [1]

    def test_right_enters_submenu(self, state_menu, tree):
        # path [0] = network (has children)
        result = _press(state_menu, "right", tree)
        assert result.nav.path == [0, 0]  # entered submenu

    def test_center_enters_submenu(self, state_menu, tree):
        result = _press(state_menu, "center", tree)
        assert result.nav.path == [0, 0]

    def test_left_at_top_goes_home(self, state_menu, tree):
        result = _press(state_menu, "left", tree)
        assert result.nav.display_state == "home"

    def test_left_pops_submenu_level(self, tree):
        state = FpmsState(nav=NavLocation(path=[0, 0], display_state="menu"))
        result = _press(state, "left", tree)
        assert result.nav.path == [0]
        assert result.nav.display_state == "menu"

    def test_right_on_leaf_dispatches_action(self, tree):
        # Navigate to network > interfaces (path [0, 0])
        state = FpmsState(nav=NavLocation(path=[0, 0], display_state="menu"))
        result = _press(state, "right", tree)
        assert result.action_id == "network.interfaces"
        assert result.nav.display_state == "page"

    def test_center_on_leaf_dispatches_action(self, tree):
        state = FpmsState(nav=NavLocation(path=[0, 0], display_state="menu"))
        result = _press(state, "center", tree)
        assert result.action_id == "network.interfaces"


class TestPageNavigation:
    @pytest.fixture
    def state_page(self):
        return FpmsState(
            nav=NavLocation(path=[0, 0], display_state="page"),
            scroll_index=0,
            scroll_max=3,
        )

    def test_left_exits_page_to_menu(self, state_page, tree):
        result = _press(state_page, "left", tree)
        assert result.nav.display_state == "menu"
        assert result.action_id is None

    def test_down_scrolls(self, state_page, tree):
        result = _press(state_page, "down", tree)
        assert result.scroll_delta == 1

    def test_up_scrolls(self, state_page, tree):
        result = _press(state_page, "up", tree)
        assert result.scroll_delta == -1


class TestLoadingGuard:
    def test_input_blocked_while_loading(self, state_menu, tree):
        state_menu.loading = True
        result = _press(state_menu, "down", tree)
        # path should not change
        assert result.nav.path == state_menu.nav.path

    def test_left_passes_loading_guard(self, state_menu, tree):
        state_menu.loading = True
        result = _press(state_menu, "left", tree)
        # Navigation changes (go home)
        assert result.nav.display_state == "home"
