"""Stateless renderer: FpmsState + MenuTree → PIL.Image.

All rendering functions are pure — no side effects, no global state mutation.
The caller owns the Image returned.

Ported from wlanpi-fpms/fpms/modules/pages/ and homepage.py.
Key changes:
  - No g_vars dict — all inputs are typed parameters
  - No oled.drawImage calls — caller sends the returned Image to the screen
  - Data is read from FpmsState / HomepageData, not subprocess calls
"""

from __future__ import annotations

import pathlib
from textwrap import wrap
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from wlanpi_fpms2.state.menu_tree import MenuTree
    from wlanpi_fpms2.state.models import FpmsState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_WIDTH  = 128
PAGE_HEIGHT = 128
STATUS_BAR_HEIGHT = 16
SYSTEM_BAR_HEIGHT = 15
MAX_PAGE_LINES  = 8   # items visible in menu
MAX_TABLE_LINES = 9   # rows visible in simple-table

_FONTS_DIR = pathlib.Path(__file__).parent / "fonts"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONTS_DIR / name), size)


# Loaded once at module import time — safe because PIL ImageFont is thread-safe
TINY_FONT = _font("DejaVuSansMono.ttf",      7)
SMART_FONT = _font("DejaVuSansMono-Bold.ttf", 10)
FONT11    = _font("DejaVuSansMono.ttf",      11)
FONTB10   = _font("DejaVuSansMono-Bold.ttf", 10)
FONTB11   = _font("DejaVuSansMono-Bold.ttf", 11)
FONTB12   = _font("DejaVuSansMono-Bold.ttf", 12)
FONTB13   = _font("DejaVuSansMono-Bold.ttf", 13)
ICONS     = _font("ionicons.ttf",            13)

# ---------------------------------------------------------------------------
# Theme  (DarkTheme — matches wlanpi-fpms default)
# ---------------------------------------------------------------------------

T = {
    "display_background":            "black",
    "text_color":                    "white",
    "text_secondary_color":          "#aeb0b5",
    "text_tertiary_color":           "#4773aa",
    "text_highlighted_color":        "#f9c642",
    "status_bar_foreground":         "white",
    "status_bar_background":         "#0071bc",
    "status_bar_battery_low":        "#fdb81e",
    "status_bar_battery_full":       "#94bfa2",
    "status_bar_temp_high":          "#b21b21",
    "status_bar_temp_med":           "#e5b63c",
    "status_bar_temp_low":           "#fad980",
    "status_bar_wifi_active":        "#fad980",
    "system_bar_foreground":         "#aeb0b5",
    "system_bar_background":         "#323a45",
    "page_title_foreground":         "white",
    "page_title_background":         "#0071bc",
    "page_item_foreground":          "white",
    "page_item_background":          "black",
    "page_icon_foreground":          "#0071bc",
    "page_selected_item_foreground": "black",
    "page_selected_item_background": "#f9c642",
    "simple_table_title_foreground": "black",
    "simple_table_title_background": "#f9c642",
    "simple_table_row_foreground":   "white",
    "alert_info_title_foreground":   "white",
    "alert_info_title_background":   "#2e8540",
    "alert_error_title_foreground":  "white",
    "alert_error_title_background":  "#cd2026",
    "alert_message_foreground":      "white",
    "complication_ok_color":         "#2e8540",
    "complication_warning_color":    "#fdb81e",
    "complication_error_color":      "#cd2026",
    "complication_unknown_color":    "#5b616b",
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(state: "FpmsState", tree: "MenuTree") -> Image.Image:
    """Return a fresh 128×128 RGB PIL Image for the given state."""
    image = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), T["display_background"])
    draw  = ImageDraw.Draw(image)

    if state.screen_sleeping:
        return image  # all-black

    ds = state.nav.display_state

    if ds == "home":
        _render_home(draw, state)
    elif ds == "menu":
        _render_menu(draw, state, tree)
        if state.loading:
            _render_loading_overlay(draw)
    elif ds == "page":
        if state.current_page is not None:
            if state.current_page.alert is not None:
                _render_alert(draw, state.current_page)
            elif state.current_page.raw_image_b64:
                _render_qr_page(image, draw, state.current_page)
            else:
                _render_simple_table(draw, state.current_page, state.scroll_index)
        if state.loading:
            _render_loading_overlay(draw)

    if state.display_orientation == "flipped":
        image = image.rotate(180)

    return image


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------


def _render_home(draw: ImageDraw.ImageDraw, state: "FpmsState") -> None:
    hp = state.homepage
    padding = 2
    y = 0

    # Status bar (time, icons)
    y += _draw_status_bar(draw, state, y=y)
    y += padding * 4

    # Alternate home page (QR code view)
    if state.home_page_alternate and hp:
        _render_home_qr(draw, state, y)
        return

    # Mode title
    mode_label = _mode_display_name(hp.mode if hp else "classic")
    if len(mode_label) > 21:
        mode_label = mode_label[:19] + ".."
    title_w = FONTB13.getbbox(mode_label)[2]
    draw.text(((PAGE_WIDTH - title_w) / 2, y + padding), mode_label,
              font=FONTB13, fill=T["text_highlighted_color"])
    y += 14 + padding * 2

    # Mode-specific content
    if hp:
        y = _render_home_mode_content(draw, hp, y)

    # Alert bar (above complications strip)
    if hp and hp.alerts:
        _draw_alert_bar(draw, hp.alerts[0])

    # Complications strip (above system bar)
    if state.complications:
        _draw_complications_strip(draw, state.complications)

    # System bar (hostname)
    hostname = hp.hostname if hp else ""
    _draw_system_bar(draw, hostname)


def _render_home_mode_content(
    draw: ImageDraw.ImageDraw, hp, y: int
) -> int:
    """Render mode-specific interface info on home screen. Returns new y."""
    padding = 2
    mode = hp.mode

    # Primary IP (large, centered)
    if hp.primary_ip:
        ip = hp.primary_ip
        ip_w = FONTB12.getbbox(ip)[2]
        draw.text(((PAGE_WIDTH - ip_w) / 2, y + padding), ip,
                  font=FONTB12, fill=T["text_color"])
        y += 13 + padding

    if mode == "hotspot":
        # Connected client count
        if hp.client_count is not None:
            label = f"Clients: {hp.client_count}"
            lw = SMART_FONT.getbbox(label)[2]
            draw.text(((PAGE_WIDTH - lw) / 2, y), label,
                      font=SMART_FONT, fill=T["text_secondary_color"])
            y += 11

    # WLAN interfaces (for all modes)
    if hp.wlan_interfaces:
        for wif in hp.wlan_interfaces[:2]:
            label = f"wlan: {wif.name}"
            lw = SMART_FONT.getbbox(label)[2]
            draw.text(((PAGE_WIDTH - lw) / 2, y), label,
                      font=SMART_FONT, fill=T["text_secondary_color"])
            y += 11

    # Secondary interfaces (classic, server, bridge)
    if mode in ("classic", "server", "bridge") and hp.secondary_ips:
        for sec in hp.secondary_ips[:3]:
            label = f"{sec['name']}: {sec['ip']}"
            if len(label) > 21:
                label = label[:19] + ".."
            lw = SMART_FONT.getbbox(label)[2]
            draw.text(((PAGE_WIDTH - lw) / 2, y), label,
                      font=SMART_FONT, fill=T["text_secondary_color"])
            y += 11

    return y


def _render_home_qr(draw: ImageDraw.ImageDraw, state: "FpmsState", y: int) -> None:
    """Render the QR code alternate home page."""
    import base64
    import io

    hp = state.homepage
    ssid = passphrase = None

    if hp.mode == "classic" and hp.profiler_active:
        ssid = hp.profiler_ssid
        passphrase = hp.profiler_passphrase
    elif hp.mode != "classic":
        ssid = hp.hotspot_ssid
        passphrase = hp.hotspot_passphrase

    if not ssid:
        # Nothing to show — draw a centered message
        msg = "No QR available"
        mw = SMART_FONT.getbbox(msg)[2]
        draw.text(((PAGE_WIDTH - mw) / 2, y + 20), msg,
                  font=SMART_FONT, fill=T["text_secondary_color"])
        _draw_system_bar(draw, hp.hostname if hp else "")
        return

    # Generate QR code
    try:
        import qrcode
        data = f"WIFI:S:{ssid};T:WPA;P:{passphrase or ''};;"
        qr_img = qrcode.make(data)
        # Scale to fit between status bar and system bar
        available = PAGE_HEIGHT - y - SYSTEM_BAR_HEIGHT - 20
        qr_img = qr_img.resize((available, available))

        # We can't paste into ImageDraw, so we encode and decode
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        qr_pil = Image.open(buf).convert("RGB")
        # Draw QR centered
        qr_x = (PAGE_WIDTH - available) // 2
        # We return to the Image via draw._image
        draw._image.paste(qr_pil, (qr_x, y))

        # SSID label below QR
        label_y = y + available + 2
        label = ssid if len(ssid) <= 21 else ssid[:19] + ".."
        lw = TINY_FONT.getbbox(label)[2]
        draw.text(((PAGE_WIDTH - lw) / 2, label_y), label,
                  font=TINY_FONT, fill=T["text_secondary_color"])
    except Exception:
        msg = "QR error"
        mw = SMART_FONT.getbbox(msg)[2]
        draw.text(((PAGE_WIDTH - mw) / 2, y + 20), msg,
                  font=SMART_FONT, fill=T["text_secondary_color"])

    _draw_system_bar(draw, hp.hostname if hp else "")


def _draw_alert_bar(draw: ImageDraw.ImageDraw, alert_text: str) -> None:
    """Draw a single alert line above the complications strip / system bar."""
    alert_y = PAGE_HEIGHT - SYSTEM_BAR_HEIGHT - 28
    color = (T["alert_error_title_background"] if "NOT SET" in alert_text
             or "NO WI-FI" in alert_text else T["alert_info_title_background"])
    if len(alert_text) > 21:
        alert_text = alert_text[:19] + ".."
    aw = TINY_FONT.getbbox(alert_text)[2]
    draw.rectangle((0, alert_y, PAGE_WIDTH, alert_y + 12), fill=color)
    draw.text(((PAGE_WIDTH - aw) / 2, alert_y + 2), alert_text,
              font=TINY_FONT, fill="white")


def _mode_display_name(mode: str) -> str:
    return {
        "classic": "Classic",
        "hotspot": "Hotspot",
        "server":  "DHCP Server",
        "bridge":  "Bridge",
    }.get(mode, mode.capitalize())


def _draw_status_bar(draw: ImageDraw.ImageDraw, state: "FpmsState", y: int = 0) -> int:
    """Draw status bar (time + icons). Returns bar height."""
    draw.rectangle((0, y, PAGE_WIDTH, y + STATUS_BAR_HEIGHT), fill=T["status_bar_background"])

    hp = state.homepage
    time_str = hp.time_str if hp else "--:--"
    draw.text((2 + 2, y + 2), time_str, font=FONTB11, fill=T["status_bar_foreground"])

    x = PAGE_WIDTH - 4
    fg = T["status_bar_foreground"]

    # Battery indicator
    if hp and hp.battery and hp.battery.present:
        x -= 18
        _draw_battery(draw, x, y + 3, hp.battery)

    # Temperature indicator (only shown when hot: >= 70C)
    if hp and hp.cpu_temp is not None and hp.cpu_temp >= 70:
        x -= 10
        color = (T["status_bar_temp_high"] if hp.cpu_temp >= 80
                 else T["status_bar_temp_med"] if hp.cpu_temp >= 75
                 else T["status_bar_temp_low"])
        draw.rectangle((x, y + 4, x + 4, y + 12), outline=color)
        draw.rectangle((x + 1, y + 2, x + 3, y + 4), fill=color)
        draw.ellipse((x - 1, y + 10, x + 5, y + 15), fill=color)

    # WiFi adapter indicators
    if hp and hp.wlan_interfaces:
        for wif in hp.wlan_interfaces[:2]:
            x -= 10
            _draw_wifi_icon(draw, x, y + 2, fg)

    # Bluetooth indicator
    if hp and hp.bluetooth_on:
        bt_icon = chr(0xf128)
        icon_w = ICONS.getbbox(bt_icon)[2]
        x -= icon_w + 2
        draw.text((x, y), bt_icon, font=ICONS, fill=fg)

    # Reachability indicator (globe)
    h = STATUS_BAR_HEIGHT - 2
    x -= h + 2
    _draw_globe(draw, x, y + 1, h, reachable=hp.reachable if hp else None)

    return STATUS_BAR_HEIGHT


def _draw_battery(draw: ImageDraw.ImageDraw, x: int, y: int, battery) -> None:
    """Draw a small battery icon with fill level."""
    w, h = 14, 8
    # Outline
    draw.rectangle((x, y, x + w, y + h), outline=T["status_bar_foreground"])
    # Nub
    draw.rectangle((x + w, y + 2, x + w + 2, y + h - 2), fill=T["status_bar_foreground"])
    # Fill
    level = battery.level_pct or 0
    fill_w = int(w * level / 100)
    color = T["status_bar_battery_low"] if level <= 25 else T["status_bar_battery_full"]
    if battery.charging:
        color = T["status_bar_battery_full"]
    if fill_w > 0:
        draw.rectangle((x + 1, y + 1, x + fill_w, y + h - 1), fill=color)


def _draw_wifi_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color: str) -> None:
    """Draw a small WiFi pie-slice icon."""
    for r in (10, 7, 4):
        draw.arc((x - r // 2, y, x + r // 2 + 4, y + r + 2), 200, 340, fill=color)
    draw.rectangle((x + 1, y + 8, x + 3, y + 10), fill=color)


def _draw_globe(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    size: int,
    reachable: bool | None,
) -> None:
    """Small globe icon. Struck-through when not reachable."""
    fg = T["status_bar_foreground"]
    draw.ellipse((x + 2, y + 1, x + size, y + size - 1), outline=fg)
    draw.ellipse((x + 4, y + 1, x + size - 2, y + size - 1), outline=fg)
    draw.line((x + 2, y + size // 2, x + size, y + size // 2), fill=fg)
    if reachable is False:
        draw.line((x + 1, y, x + size + 1, y + size), fill=fg, width=2)


def _draw_system_bar(draw: ImageDraw.ImageDraw, contents: str) -> None:
    y = PAGE_HEIGHT - SYSTEM_BAR_HEIGHT - 1
    draw.rectangle((0, y, PAGE_WIDTH, PAGE_HEIGHT), fill=T["system_bar_background"])
    if contents:
        if len(contents) > 21:
            contents = contents[:19] + ".."
        w = SMART_FONT.getbbox(contents)[2]
        draw.text(((PAGE_WIDTH - w) / 2, y + 2), contents,
                  font=SMART_FONT, fill=T["system_bar_foreground"])


def _draw_complications_strip(draw: ImageDraw.ImageDraw, complications) -> None:
    """Render complications as small chips just above the system bar."""
    strip_y = PAGE_HEIGHT - SYSTEM_BAR_HEIGHT - 15
    status_colors = {
        "ok":      T["complication_ok_color"],
        "warning": T["complication_warning_color"],
        "error":   T["complication_error_color"],
        "unknown": T["complication_unknown_color"],
    }
    x = 2
    for comp in complications[:4]:
        color = status_colors.get(comp.status, T["complication_unknown_color"])
        label = f"{comp.label}: {comp.value}"
        if len(label) > 14:
            label = label[:13] + "…"
        draw.text((x, strip_y), label, font=TINY_FONT, fill=color)
        x += PAGE_WIDTH // 4


# ---------------------------------------------------------------------------
# Menu page
# ---------------------------------------------------------------------------


def _render_menu(
    draw: ImageDraw.ImageDraw,
    state: "FpmsState",
    tree: "MenuTree",
) -> None:
    path = state.nav.path

    # Resolve the parent node to get siblings (items at current level)
    sibling_ids = tree.siblings_of_path(path)
    if not sibling_ids:
        sibling_ids = tree.roots

    # Which item is selected? (last element in path)
    selected_idx = path[-1] if path else 0

    # Determine page title (parent node name, or "Menu" at top)
    if len(path) <= 1:
        page_title = "Menu"
    else:
        parent = tree.resolve_path(path[:-1])
        page_title = parent.name.upper() if parent else "Menu"

    if len(page_title) > 15:
        page_title = page_title[:13] + ".."

    # --- Title bar ---
    draw.rectangle((0, 0, PAGE_WIDTH, STATUS_BAR_HEIGHT), fill=T["page_title_background"])
    tw = FONTB12.getbbox(page_title)[2]
    draw.text(((PAGE_WIDTH - tw) / 2, 0), page_title,
              font=FONTB12, fill=T["page_title_foreground"])
    # Back nav indicator (chevron left)
    hy = STATUS_BAR_HEIGHT / 2
    draw.line([(4, hy), (8, 4)],                fill=T["page_title_foreground"], width=1)
    draw.line([(4, hy), (8, STATUS_BAR_HEIGHT - 4)], fill=T["page_title_foreground"], width=1)

    # --- Menu items ---
    y = STATUS_BAR_HEIGHT + 1
    y_offset = 14

    # Windowing: scroll to keep selection visible
    if len(sibling_ids) > MAX_PAGE_LINES:
        if selected_idx >= MAX_PAGE_LINES:
            start = selected_idx - (MAX_PAGE_LINES - 1)
        else:
            start = 0
        visible_ids = sibling_ids[start: start + MAX_PAGE_LINES]
        display_selected = selected_idx - start
    else:
        visible_ids = sibling_ids
        display_selected = selected_idx

    for i, node_id in enumerate(visible_ids):
        node = tree.index.get(node_id)
        if node is None:
            continue

        is_selected = (i == display_selected)
        has_children = bool(node.children)

        rect_fill = T["page_selected_item_background"] if is_selected else T["page_item_background"]
        text_fill = T["page_selected_item_foreground"] if is_selected else T["page_item_foreground"]
        icon_fill = T["page_selected_item_foreground"] if is_selected else T["page_icon_foreground"]

        draw.rectangle((0, y, PAGE_WIDTH, y + y_offset), fill=rect_fill)

        name = node.name
        draw.text((12, y), name, font=FONTB11, fill=text_fill)

        hy = y + y_offset / 2
        if has_children:
            # List icon (3 dots + lines)
            for dy in (-2, 0, 2):
                draw.line([(2, hy + dy), (2, hy + dy)], fill=icon_fill, width=1)
                draw.line([(4, hy + dy), (8, hy + dy)], fill=icon_fill, width=1)
            # Right chevron
            draw.line([(PAGE_WIDTH - 4, hy), (PAGE_WIDTH - 8, y + 3)],          fill=icon_fill, width=1)
            draw.line([(PAGE_WIDTH - 4, hy), (PAGE_WIDTH - 8, y + y_offset - 3)], fill=icon_fill, width=1)
        else:
            # Action dot
            if is_selected:
                draw.ellipse((3, hy - 2, 7, hy + 2), fill=icon_fill)
            else:
                draw.ellipse((3, hy - 2, 7, hy + 2), outline=icon_fill)

        y += y_offset


# ---------------------------------------------------------------------------
# Simple table (page content)
# ---------------------------------------------------------------------------


def _render_simple_table(
    draw: ImageDraw.ImageDraw,
    page,   # PageContent
    scroll_index: int = 0,
) -> None:
    y = 0
    font_offset = 2
    font_size   = 11
    title_max   = 17

    title = page.title or ""
    if len(title) > title_max:
        title = title[:title_max - 2] + ".."

    # Title bar
    draw.rectangle((0, 0, PAGE_WIDTH, STATUS_BAR_HEIGHT), fill=T["simple_table_title_background"])
    tw = SMART_FONT.getbbox(title)[2]
    draw.text(((PAGE_WIDTH - tw) / 2, font_offset), title,
              font=SMART_FONT, fill=T["simple_table_title_foreground"])
    # Back nav indicator
    hy = STATUS_BAR_HEIGHT / 2
    draw.line([(4, hy), (8, 4)],                fill=T["simple_table_title_foreground"], width=1)
    draw.line([(4, hy), (8, STATUS_BAR_HEIGHT - 4)], fill=T["simple_table_title_foreground"], width=1)

    font_offset += font_size + 4
    table_max = MAX_TABLE_LINES

    lines = list(page.lines)

    # Split long lines
    split_lines: list[str] = []
    for line in lines:
        if len(line) > 20:
            split_lines.extend(wrap(line, 20))
        else:
            split_lines.append(line)

    # Scroll window
    if len(split_lines) > table_max:
        start = scroll_index
        split_lines = split_lines[start: start + table_max]

    for line in split_lines:
        draw.text((0, font_offset), line,
                  font=SMART_FONT, fill=T["simple_table_row_foreground"])
        font_offset += font_size + 2


# ---------------------------------------------------------------------------
# QR code page
# ---------------------------------------------------------------------------


def _render_qr_page(image: Image.Image, draw: ImageDraw.ImageDraw, page) -> None:
    """Render a page that contains a base64-encoded QR PNG.

    Title bar at top, QR code centred below, text lines squeezed below that.
    """
    import base64
    import io

    title = page.title or ""
    if len(title) > 17:
        title = title[:15] + ".."

    # Title bar
    draw.rectangle((0, 0, PAGE_WIDTH, STATUS_BAR_HEIGHT), fill=T["simple_table_title_background"])
    tw = SMART_FONT.getbbox(title)[2]
    draw.text(((PAGE_WIDTH - tw) / 2, 2), title,
              font=SMART_FONT, fill=T["simple_table_title_foreground"])
    hy = STATUS_BAR_HEIGHT / 2
    draw.line([(4, hy), (8, 4)],                fill=T["simple_table_title_foreground"], width=1)
    draw.line([(4, hy), (8, STATUS_BAR_HEIGHT - 4)], fill=T["simple_table_title_foreground"], width=1)

    y = STATUS_BAR_HEIGHT + 2

    # Decode and scale the QR image to fit the available width
    try:
        raw = base64.b64decode(page.raw_image_b64)
        qr_img = Image.open(io.BytesIO(raw)).convert("RGB")
        # Leave room for text lines below
        text_lines = page.lines or []
        text_height = len(text_lines) * 11 if text_lines else 0
        available = PAGE_HEIGHT - y - text_height - 4
        qr_size = min(available, PAGE_WIDTH - 4)
        qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
        x_off = (PAGE_WIDTH - qr_size) // 2
        image.paste(qr_img, (x_off, y))
        y += qr_size + 2
    except Exception:
        pass  # if decode fails, just show text below the title

    # Text lines below QR
    for line in (page.lines or []):
        if y >= PAGE_HEIGHT - 2:
            break
        draw.text((2, y), line, font=TINY_FONT, fill=T["simple_table_row_foreground"])
        y += 10


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------


def _render_alert(draw: ImageDraw.ImageDraw, page) -> None:
    """Render PageContent that has an alert set."""
    alert = page.alert
    title = page.title or "Alert"

    level = alert.level if alert else "error"
    if level == "error":
        title_fg = T["alert_error_title_foreground"]
        title_bg = T["alert_error_title_background"]
    else:
        title_fg = T["alert_info_title_foreground"]
        title_bg = T["alert_info_title_background"]

    if len(title) > 17:
        title = title[:15] + ".."

    # Title bar
    draw.rectangle((0, 0, PAGE_WIDTH, STATUS_BAR_HEIGHT), fill=title_bg)
    tw = SMART_FONT.getbbox(title)[2]
    draw.text(((PAGE_WIDTH - tw) / 2, 2), title, font=SMART_FONT, fill=title_fg)
    hy = STATUS_BAR_HEIGHT / 2
    draw.line([(4, hy), (8, 4)],                fill=title_fg, width=1)
    draw.line([(4, hy), (8, STATUS_BAR_HEIGHT - 4)], fill=title_fg, width=1)

    # Message lines
    message = alert.message if alert else "\n".join(page.lines)
    item_list = wrap(message, 17, break_on_hyphens=False)
    font_offset = STATUS_BAR_HEIGHT + 4

    for item in item_list[:6]:
        iw = SMART_FONT.getbbox(item)[2]
        draw.text(((PAGE_WIDTH - iw) / 2, font_offset), item,
                  font=SMART_FONT, fill=T["alert_message_foreground"])
        font_offset += 12


# ---------------------------------------------------------------------------
# Loading overlay
# ---------------------------------------------------------------------------


def _render_loading_overlay(draw: ImageDraw.ImageDraw) -> None:
    """Semi-transparent loading indicator band at bottom of screen."""
    y = PAGE_HEIGHT - 16
    draw.rectangle((0, y, PAGE_WIDTH, PAGE_HEIGHT), fill="#323a45")
    msg = "Loading..."
    mw = SMART_FONT.getbbox(msg)[2]
    draw.text(((PAGE_WIDTH - mw) / 2, y + 2), msg,
              font=SMART_FONT, fill="#f9c642")
