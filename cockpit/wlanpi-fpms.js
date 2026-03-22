/**
 * WLANPi FPMS Cockpit Plugin
 *
 * Connects to the fpms2 state service at 127.0.0.1:8765 using
 * Cockpit's transport layer (cockpit.channel for WebSocket,
 * cockpit.http for REST). No authentication required — the
 * state service is unauthenticated localhost.
 *
 * State flow:
 *   WS /ws → renderState(state) → update DOM panels
 *   DOM buttons → sendButton(btn) → POST /input → state update via WS
 */

/* global cockpit */

(function () {
    "use strict";

    const FPMS_PORT = 8765;
    const FPMS_HOST = "127.0.0.1";
    const RECONNECT_DELAY_MS = 2000;

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------

    /** @type {Object.<string, Object>} menuIndex: node id → MenuNode */
    var menuIndex = {};

    /** @type {Object|null} last received FpmsState */
    var lastState = null;

    /** @type {boolean} */
    var wsConnected = false;

    /** @type {ReturnType<typeof cockpit.http>} */
    var http = cockpit.http(FPMS_PORT, { address: FPMS_HOST });

    // -----------------------------------------------------------------------
    // WebSocket connection via Cockpit channel
    // -----------------------------------------------------------------------

    function connectWebSocket() {
        var ws = cockpit.channel({
            payload: "websocket",
            address: FPMS_HOST,
            port: FPMS_PORT,
            path: "/ws"
        });

        ws.addEventListener("message", function (event, data) {
            try {
                var msg = JSON.parse(data);
                if (msg.type === "state") {
                    renderState(msg.state);
                }
                // ignore "ping" messages
            } catch (e) {
                console.warn("fpms: failed to parse WS message", e);
            }
        });

        ws.addEventListener("close", function () {
            setConnected(false);
            setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
        });

        ws.addEventListener("ready", function () {
            setConnected(true);
        });
    }

    // -----------------------------------------------------------------------
    // Initial data fetch
    // -----------------------------------------------------------------------

    function fetchInitialData() {
        // Fetch menu tree for name resolution
        http.get("/menu")
            .done(function (data) {
                var nodes = JSON.parse(data);
                menuIndex = {};
                nodes.forEach(function (node) {
                    menuIndex[node.id] = node;
                });
            })
            .fail(function (err) {
                console.warn("fpms: could not fetch menu tree", err);
            });

        // Fetch current state snapshot
        http.get("/state")
            .done(function (data) {
                renderState(JSON.parse(data));
            })
            .fail(function (err) {
                console.warn("fpms: could not fetch initial state", err);
            });
    }

    // -----------------------------------------------------------------------
    // Button input
    // -----------------------------------------------------------------------

    function sendButton(btn) {
        http.post(
            "/input",
            JSON.stringify({ button: btn }),
            { "Content-Type": "application/json" }
        ).fail(function (err) {
            console.warn("fpms: failed to send button", btn, err);
        });
    }

    // Make sendButton global so onclick= attributes can call it
    window.sendButton = sendButton;

    // -----------------------------------------------------------------------
    // Main render dispatcher
    // -----------------------------------------------------------------------

    function renderState(state) {
        lastState = state;

        renderDeviceCard(state);
        renderConnectionStatus(true);
        renderComplications(state);

        // Loading overlay
        var overlay = document.getElementById("loading-overlay");
        overlay.style.display = state.loading ? "flex" : "none";

        // Shutdown banner
        if (state.shutdown_in_progress) {
            showPanel("home");
            document.getElementById("home-content").textContent =
                "Device is rebooting…\nPlease wait.";
            return;
        }

        var display = (state.nav && state.nav.display_state) || "home";
        showPanel(display);

        if (display === "home") {
            renderHome(state);
        } else if (display === "menu") {
            renderMenu(state);
        } else {
            renderPage(state);
        }

        renderBreadcrumb(state);
    }

    // -----------------------------------------------------------------------
    // Panel switching
    // -----------------------------------------------------------------------

    function showPanel(name) {
        ["home", "menu", "page"].forEach(function (id) {
            var el = document.getElementById("panel-" + id);
            if (el) el.style.display = (id === name) ? "" : "none";
        });
    }

    // -----------------------------------------------------------------------
    // Home panel
    // -----------------------------------------------------------------------

    function renderHome(state) {
        var hp = state.homepage || {};
        var lines = [
            "  Hostname:  " + (hp.hostname || "—"),
            "  IP:        " + (hp.primary_ip || "—"),
            "  Mode:      " + titleCase(hp.mode || "classic"),
            "  Bluetooth: " + (hp.bluetooth_on ? "On" : "Off"),
            "  Profiler:  " + (hp.profiler_active ? "Active" : "Stopped"),
            "  Reachable: " + reachableStr(hp.reachable),
        ];
        if (hp.alerts && hp.alerts.length) {
            lines.push("");
            hp.alerts.forEach(function (a) { lines.push("  ! " + a); });
        }
        lines.push("");
        lines.push("  Use → or the nav buttons to open the menu.");
        document.getElementById("home-content").textContent = lines.join("\n");
    }

    // -----------------------------------------------------------------------
    // Menu panel
    // -----------------------------------------------------------------------

    function renderMenu(state) {
        var path = (state.nav && state.nav.path) || [0];
        var currentIdx = path[path.length - 1] || 0;

        // Find siblings at the current depth
        var siblings = siblingsOfPath(path);
        var list = document.getElementById("menu-list");
        list.innerHTML = "";

        siblings.forEach(function (nodeId, i) {
            var node = menuIndex[nodeId];
            if (!node) return;

            var li = document.createElement("li");
            li.className = "fpms-menu-item" + (i === currentIdx ? " fpms-menu-selected" : "");

            var arrow = node.children && node.children.length ? "▸ " : "   ";
            li.textContent = arrow + node.name;

            // Clicking a non-selected item: navigate to it via up/down + right
            li.addEventListener("click", function () {
                navigateToIndex(currentIdx, i, siblings.length);
            });

            list.appendChild(li);
        });
    }

    /**
     * Navigate to a menu item by index using button presses.
     * Sends the appropriate number of up/down presses then selects.
     */
    function navigateToIndex(fromIdx, toIdx, total) {
        var presses = [];
        if (toIdx === fromIdx) {
            presses = ["right"];
        } else if (toIdx > fromIdx) {
            for (var i = 0; i < toIdx - fromIdx; i++) presses.push("down");
            presses.push("right");
        } else {
            for (var j = 0; j < fromIdx - toIdx; j++) presses.push("up");
            presses.push("right");
        }
        // Send with small delays so the state service processes each button
        var delay = 0;
        presses.forEach(function (btn) {
            setTimeout(function () { sendButton(btn); }, delay);
            delay += 80;
        });
    }

    /**
     * Return the sibling node IDs at the current navigation depth.
     * The menu tree is a flat list with parent_id references.
     */
    function siblingsOfPath(path) {
        if (path.length === 1) {
            // Top-level: children of root nodes (nodes with no parent reference)
            return topLevelNodeIds();
        }
        // Resolve parent by walking path from root
        var ancestorIds = topLevelNodeIds();
        var parentNode = null;
        for (var depth = 0; depth < path.length - 1; depth++) {
            var idx = path[depth];
            if (idx >= ancestorIds.length) break;
            parentNode = menuIndex[ancestorIds[idx]];
            if (!parentNode || !parentNode.children) break;
            ancestorIds = parentNode.children;
        }
        return ancestorIds || [];
    }

    function topLevelNodeIds() {
        // Nodes whose IDs don't appear as any child of another node
        var allChildIds = new Set();
        Object.values(menuIndex).forEach(function (node) {
            (node.children || []).forEach(function (c) { allChildIds.add(c); });
        });
        return Object.keys(menuIndex).filter(function (id) {
            return !allChildIds.has(id);
        });
    }

    // -----------------------------------------------------------------------
    // Page panel
    // -----------------------------------------------------------------------

    function renderPage(state) {
        var page = state.current_page;
        if (!page) {
            document.getElementById("page-title").textContent = "";
            document.getElementById("page-content").textContent = "";
            return;
        }

        var titleText = page.title || "";
        if (page.page_count > 1) {
            titleText += "  (page " + (page.page_index + 1) + "/" + page.page_count + ")";
        }
        document.getElementById("page-title").textContent = titleText;
        document.getElementById("page-content").textContent = (page.lines || []).join("\n");

        var alertEl = document.getElementById("page-alert");
        if (page.alert) {
            var levelClass = { error: "fpms-alert-error", warning: "fpms-alert-warning", info: "fpms-alert-info" }[page.alert.level] || "";
            alertEl.className = "fpms-alert " + levelClass;
            alertEl.textContent = page.alert.message;
            alertEl.style.display = "";
        } else {
            alertEl.style.display = "none";
        }

        var hintEl = document.getElementById("page-scroll-hint");
        if (state.scroll_max > 0) {
            hintEl.textContent = "↑↓ scroll  (" + (state.scroll_index + 1) + "/" + (state.scroll_max + 1) + ")";
            hintEl.style.display = "";
        } else {
            hintEl.style.display = "none";
        }
    }

    // -----------------------------------------------------------------------
    // Breadcrumb
    // -----------------------------------------------------------------------

    function renderBreadcrumb(state) {
        var path = (state.nav && state.nav.path) || [0];
        var display = (state.nav && state.nav.display_state) || "home";

        if (display === "home") {
            document.getElementById("breadcrumb").textContent = "Home";
            return;
        }

        var parts = ["Main Menu"];
        var ancestorIds = topLevelNodeIds();
        for (var depth = 0; depth < path.length - 1; depth++) {
            var idx = path[depth];
            if (idx >= ancestorIds.length) break;
            var node = menuIndex[ancestorIds[idx]];
            if (!node) break;
            parts.push(node.name);
            ancestorIds = node.children || [];
        }

        if (display === "page" && state.current_page) {
            parts.push(state.current_page.title);
        }

        document.getElementById("breadcrumb").textContent = parts.join(" › ");
    }

    // -----------------------------------------------------------------------
    // Device info card
    // -----------------------------------------------------------------------

    function renderDeviceCard(state) {
        var hp = state.homepage || {};
        setText("info-hostname", hp.hostname || "—");
        setText("info-ip", hp.primary_ip || "—");
        setText("info-mode", titleCase(hp.mode || "classic"));
        setHtml("info-bt", hp.bluetooth_on
            ? "<span class='fpms-ok'>● On</span>"
            : "<span class='fpms-dim'>○ Off</span>");
        setHtml("info-profiler", hp.profiler_active
            ? "<span class='fpms-ok'>● Active</span>"
            : "<span class='fpms-dim'>○ Stopped</span>");
        setHtml("info-reachable", reachableHtml(hp.reachable));
        setText("info-time", hp.time_str || "—");
    }

    // -----------------------------------------------------------------------
    // Complications bar
    // -----------------------------------------------------------------------

    function renderComplications(state) {
        var comps = state.complications || [];
        var bar = document.getElementById("complications-bar");
        if (!comps.length) {
            bar.style.display = "none";
            return;
        }
        bar.style.display = "";
        var parts = comps.map(function (c) {
            var cls = { ok: "fpms-ok", warning: "fpms-warn", error: "fpms-err" }[c.status] || "";
            var icon = (c.icon && c.icon.length === 1) ? c.icon + " " : "";
            return "<span class='" + cls + "'>" + escHtml(icon + c.label + ": " + c.value) + "</span>";
        });
        document.getElementById("complications-content").innerHTML = parts.join(" &nbsp;│&nbsp; ");
    }

    // -----------------------------------------------------------------------
    // Connection status badge
    // -----------------------------------------------------------------------

    function setConnected(connected) {
        wsConnected = connected;
        var badge = document.getElementById("conn-badge");
        if (connected) {
            badge.textContent = "● Connected";
            badge.className = "fpms-badge fpms-badge-ok";
        } else {
            badge.textContent = "○ Connecting";
            badge.className = "fpms-badge fpms-badge-warning";
        }
    }

    // -----------------------------------------------------------------------
    // Utility helpers
    // -----------------------------------------------------------------------

    function setText(id, text) {
        var el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function setHtml(id, html) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = html;
    }

    function escHtml(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function titleCase(str) {
        if (!str) return "";
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    function reachableStr(val) {
        if (val === true) return "Yes";
        if (val === false) return "No";
        return "Unknown";
    }

    function reachableHtml(val) {
        if (val === true) return "<span class='fpms-ok'>● Yes</span>";
        if (val === false) return "<span class='fpms-err'>● No</span>";
        return "<span class='fpms-dim'>○ Unknown</span>";
    }

    // -----------------------------------------------------------------------
    // Boot sequence
    // -----------------------------------------------------------------------

    fetchInitialData();
    connectWebSocket();

}());
