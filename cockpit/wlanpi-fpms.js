/**
 * WLANPi FPMS Cockpit Plugin
 *
 * Uses cockpit.http() to reach the fpms2 state service on
 * 127.0.0.1:8765 via the Cockpit bridge transport.
 * No auth required — the state service is unauthenticated localhost.
 *
 * State flow:
 *   Poll GET /state every ~1.5s → renderState(state) → update DOM
 *   Button clicks → POST /input → immediate re-poll for fresh state
 */

/* global cockpit */

(function () {
    "use strict";

    var FPMS_PORT    = 8765;
    var FPMS_HOST    = "127.0.0.1";
    var POLL_MS      = 1500;   // background poll interval
    var BUTTON_WAIT  = 250;    // ms after button press before re-polling

    // -----------------------------------------------------------------------
    // HTTP client via Cockpit bridge transport
    // -----------------------------------------------------------------------

    var http = cockpit.http({ port: FPMS_PORT, address: FPMS_HOST });

    // -----------------------------------------------------------------------
    // Menu tree (fetched once, refreshed every 30s)
    // -----------------------------------------------------------------------

    /** @type {Object.<string, Object>}  node id → MenuNode */
    var menuIndex = {};

    /** Current device mode — updated on every state poll. */
    var currentMode = "classic";

    function fetchMenu() {
        http.get("/menu")
            .done(function (data) {
                try {
                    var nodes = JSON.parse(data);
                    var idx = {};
                    nodes.forEach(function (n) { idx[n.id] = n; });
                    menuIndex = idx;
                } catch (e) {
                    console.warn("fpms: could not parse /menu", e);
                }
            });
    }

    // -----------------------------------------------------------------------
    // State polling
    // -----------------------------------------------------------------------

    function pollState() {
        http.get("/state")
            .done(function (data) {
                try {
                    renderState(JSON.parse(data));
                    setConnected(true);
                } catch (e) {
                    console.warn("fpms: could not parse /state", e);
                }
            })
            .fail(function (err) {
                setConnected(false);
                console.warn("fpms: /state poll failed", err);
            });
    }

    // -----------------------------------------------------------------------
    // Button input + direct navigation
    // -----------------------------------------------------------------------

    function sendButton(btn) {
        http.post(
            "/input",
            JSON.stringify({ button: btn }),
            { "Content-Type": "application/json" }
        )
            .done(function () {
                // Re-poll immediately so the UI feels snappy
                setTimeout(pollState, BUTTON_WAIT);
            })
            .fail(function (err) {
                console.warn("fpms: failed to send button", btn, err);
            });
    }

    /** Jump directly to a node by ID via POST /navigate. */
    function navigateTo(nodeId) {
        http.post(
            "/navigate",
            JSON.stringify({ node_id: nodeId }),
            { "Content-Type": "application/json" }
        )
            .done(function () {
                setTimeout(pollState, BUTTON_WAIT);
            })
            .fail(function (err) {
                console.warn("fpms: navigate failed for", nodeId, err);
                flashError("Nav failed: " + (err.problem || err.status || "error"));
            });
    }

    /** Briefly show an error in the connection badge, then restore. */
    function flashError(msg) {
        var badge = el("conn-badge");
        var prev  = { text: badge.textContent, cls: badge.className };
        badge.textContent = "⚠ " + msg;
        badge.className   = "fpms-badge fpms-badge-error";
        setTimeout(function () {
            badge.textContent = prev.text;
            badge.className   = prev.cls;
        }, 3000);
    }

    // -----------------------------------------------------------------------
    // Main render dispatcher
    // -----------------------------------------------------------------------

    function renderState(state) {
        currentMode = (state.homepage && state.homepage.mode) || "classic";
        renderDeviceCard(state);
        renderComplications(state);

        // Loading overlay
        el("loading-overlay").style.display = state.loading ? "flex" : "none";

        if (state.shutdown_in_progress) {
            showPanel("home");
            el("home-content").textContent = "Device is rebooting…\nPlease wait.";
            el("breadcrumb").textContent = "System";
            return;
        }

        var display = (state.nav && state.nav.display_state) || "home";
        showPanel(display);
        renderBreadcrumb(state, display);

        if (display === "home") {
            renderHome(state);
        } else if (display === "menu") {
            renderMenu(state);
        } else {
            renderPage(state);
        }
    }

    // -----------------------------------------------------------------------
    // Panel switching
    // -----------------------------------------------------------------------

    function showPanel(name) {
        ["home", "menu", "page"].forEach(function (id) {
            el("panel-" + id).style.display = (id === name) ? "" : "none";
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
        lines.push("  Use the nav buttons (→) to open the menu.");
        el("home-content").textContent = lines.join("\n");
    }

    // -----------------------------------------------------------------------
    // Menu panel
    // -----------------------------------------------------------------------

    function renderMenu(state) {
        var path       = (state.nav && state.nav.path) || [0];
        var currentIdx = path[path.length - 1] || 0;
        var siblings   = siblingsOfPath(path);

        var list = el("menu-list");
        list.innerHTML = "";

        siblings.forEach(function (nodeId, i) {
            var node = menuIndex[nodeId];
            if (!node) return;

            var li         = document.createElement("li");
            var isSelected = (i === currentIdx);
            li.className   = "fpms-menu-item" + (isSelected ? " fpms-menu-selected" : "");

            var arrow = (node.children && node.children.length) ? "▸ " : "   ";
            li.textContent = arrow + node.name;

            // Direct navigation: jump straight to this node
            li.addEventListener("click", (function (nid) {
                return function () { navigateTo(nid); };
            })(nodeId));

            list.appendChild(li);
        });
    }

    // -----------------------------------------------------------------------
    // Page panel
    // -----------------------------------------------------------------------

    function renderPage(state) {
        var page = state.current_page;
        if (!page) {
            el("page-title").textContent   = "";
            el("page-content").textContent = "";
            return;
        }

        var titleText = page.title || "";
        if (page.page_count > 1) {
            titleText += "  (page " + (page.page_index + 1) + "/" + page.page_count + ")";
        }
        el("page-title").textContent   = titleText;
        el("page-content").textContent = (page.lines || []).join("\n");

        var qrEl = el("page-qr");
        if (page.raw_image_b64) {
            qrEl.src = "data:image/png;base64," + page.raw_image_b64;
            qrEl.style.display = "";
        } else {
            qrEl.src = "";
            qrEl.style.display = "none";
        }

        var alertEl = el("page-alert");
        if (page.alert) {
            var cls = { error: "fpms-alert-error", warning: "fpms-alert-warning", info: "fpms-alert-info" }[page.alert.level] || "";
            alertEl.className    = "fpms-alert " + cls;
            alertEl.textContent  = page.alert.message;
            alertEl.style.display = "";
        } else {
            alertEl.style.display = "none";
        }

        var hintEl = el("page-scroll-hint");
        if (state.scroll_max > 0) {
            hintEl.textContent  = "↑↓ scroll  (" + (state.scroll_index + 1) + "/" + (state.scroll_max + 1) + ")";
            hintEl.style.display = "";
        } else {
            hintEl.style.display = "none";
        }
    }

    // -----------------------------------------------------------------------
    // Breadcrumb (clickable ancestors)
    // -----------------------------------------------------------------------

    function renderBreadcrumb(state, display) {
        var container = el("breadcrumb");

        if (display === "home") {
            container.textContent = "Home";
            return;
        }

        var path  = (state.nav && state.nav.path) || [0];
        var parts = [
            { name: "Home",      nodeId: "__home__" },
            { name: "Main Menu", nodeId: "__main_menu__" },
        ];
        var ids = topLevelNodeIds();

        for (var depth = 0; depth < path.length - 1; depth++) {
            var nodeId = ids[path[depth]];
            var node   = menuIndex[nodeId];
            if (!node) break;
            parts.push({ name: node.name, nodeId: nodeId });
            ids = node.children || [];
        }

        if (display === "page" && state.current_page) {
            parts.push({ name: state.current_page.title, nodeId: null });
        }

        // All non-last parts are clickable via POST /navigate
        container.innerHTML = "";
        parts.forEach(function (part, i) {
            if (i > 0) {
                var sep = document.createElement("span");
                sep.className   = "fpms-breadcrumb-sep";
                sep.textContent = " › ";
                container.appendChild(sep);
            }

            var span   = document.createElement("span");
            var isLast = (i === parts.length - 1);

            if (!isLast && part.nodeId) {
                span.className   = "fpms-breadcrumb-link";
                span.textContent = part.name;
                span.addEventListener("click", (function (nid) {
                    return function () { navigateTo(nid); };
                })(part.nodeId));
            } else {
                span.className   = "fpms-breadcrumb-current";
                span.textContent = part.name;
            }

            container.appendChild(span);
        });
    }

    // -----------------------------------------------------------------------
    // Device info card
    // -----------------------------------------------------------------------

    function renderDeviceCard(state) {
        var hp = state.homepage || {};
        setText("info-hostname",  hp.hostname   || "—");
        setText("info-ip",        hp.primary_ip || "—");
        setText("info-mode",      titleCase(hp.mode || "classic"));
        setHtml("info-bt",        hp.bluetooth_on
            ? "<span class='fpms-ok'>● On</span>"
            : "<span class='fpms-dim'>○ Off</span>");
        setHtml("info-profiler",  hp.profiler_active
            ? "<span class='fpms-ok'>● Active</span>"
            : "<span class='fpms-dim'>○ Stopped</span>");
        setHtml("info-reachable", reachableHtml(hp.reachable));
        setText("info-time",      hp.time_str || "—");
    }

    // -----------------------------------------------------------------------
    // Complications bar
    // -----------------------------------------------------------------------

    function renderComplications(state) {
        var comps = state.complications || [];
        var bar   = el("complications-bar");
        if (!comps.length) {
            bar.style.display = "none";
            return;
        }
        bar.style.display = "";
        var parts = comps.map(function (c) {
            var cls  = { ok: "fpms-ok", warning: "fpms-warn", error: "fpms-err" }[c.status] || "";
            var icon = (c.icon && c.icon.length === 1) ? c.icon + " " : "";
            return "<span class='" + cls + "'>" + esc(icon + c.label + ": " + c.value) + "</span>";
        });
        el("complications-content").innerHTML = parts.join(" &nbsp;│&nbsp; ");
    }

    // -----------------------------------------------------------------------
    // Connection status badge
    // -----------------------------------------------------------------------

    function setConnected(connected) {
        var badge = el("conn-badge");
        if (connected) {
            badge.textContent = "● Connected";
            badge.className   = "fpms-badge fpms-badge-ok";
        } else {
            badge.textContent = "○ Connecting";
            badge.className   = "fpms-badge fpms-badge-warning";
        }
    }

    // -----------------------------------------------------------------------
    // Menu tree helpers
    // -----------------------------------------------------------------------

    /** Return true if a node should be visible in the current mode. */
    function nodeVisible(node) {
        if (!node) return false;
        var hidden = node.hidden_in_mode || [];
        if (hidden.indexOf(currentMode) !== -1) return false;
        var visible = node.visible_in_mode || [];
        if (visible.length > 0 && visible.indexOf(currentMode) === -1) return false;
        return true;
    }

    function siblingsOfPath(path) {
        if (path.length <= 1) return topLevelNodeIds();
        var ids    = topLevelNodeIds();
        var parent = null;
        for (var d = 0; d < path.length - 1; d++) {
            parent = menuIndex[ids[path[d]]];
            if (!parent || !parent.children) return ids;
            ids = parent.children.filter(function (id) {
                return nodeVisible(menuIndex[id]);
            });
        }
        return ids;
    }

    function topLevelNodeIds() {
        var childSet = {};
        Object.keys(menuIndex).forEach(function (id) {
            (menuIndex[id].children || []).forEach(function (c) { childSet[c] = true; });
        });
        return Object.keys(menuIndex).filter(function (id) {
            return !childSet[id] && nodeVisible(menuIndex[id]);
        });
    }

    // -----------------------------------------------------------------------
    // DOM / string helpers
    // -----------------------------------------------------------------------

    function el(id)       { return document.getElementById(id); }
    function setText(id, t) { var e = el(id); if (e) e.textContent = t; }
    function setHtml(id, h) { var e = el(id); if (e) e.innerHTML = h; }

    function esc(str) {
        return String(str)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function titleCase(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }

    function reachableStr(v) {
        return v === true ? "Yes" : v === false ? "No" : "Unknown";
    }

    function reachableHtml(v) {
        if (v === true)  return "<span class='fpms-ok'>● Yes</span>";
        if (v === false) return "<span class='fpms-err'>● No</span>";
        return "<span class='fpms-dim'>○ Unknown</span>";
    }

    // -----------------------------------------------------------------------
    // Boot sequence
    // -----------------------------------------------------------------------

    // Wire nav buttons via event listeners (CSP blocks inline onclick=)
    document.querySelectorAll("[data-button]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            sendButton(btn.getAttribute("data-button"));
        });
    });

    // Keyboard shortcuts
    var KEY_MAP = {
        ArrowUp:    "up",
        ArrowDown:  "down",
        ArrowLeft:  "left",
        ArrowRight: "right",
        Enter:      "center",
        Escape:     "left",
        Backspace:  "left",
        F1:         "key1",
        F2:         "key2",
        F3:         "key3",
    };
    document.addEventListener("keydown", function (e) {
        var btn = KEY_MAP[e.key];
        if (!btn) return;
        e.preventDefault();
        sendButton(btn);
    });

    fetchMenu();
    pollState();
    setInterval(pollState, POLL_MS);
    setInterval(fetchMenu, 30000);

}());
