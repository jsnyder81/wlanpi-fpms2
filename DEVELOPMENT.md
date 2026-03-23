# wlanpi-fpms2 Development Setup

This document covers how to set up a fresh WLANPi for development of **wlanpi-fpms2** alongside a dev copy of **wlanpi-core**.

---

## Overview

Two services run side by side:

| Service | Port / Socket | User | What it is |
|---------|---------------|------|-----------|
| **wlanpi-core-dev** | `http://localhost:8000` | `root` | Dev copy of the REST API backend |
| **wlanpi-fpms2** | `http://127.0.0.1:8765` | `wlanpi` | fpms2 state service (FastAPI + WebSocket) |
| **wlanpi-fpms2-screen** | (systemd) | `root` | OLED + GPIO thin client |

Both the production `wlanpi-core` (port 80 via nginx) and `wlanpi-fpms` are **stopped and disabled** during development. They can be restored at any time (see Part 6).

---

## Prerequisites

On your Mac, push both repos to the WLANPi (or clone them directly on device):

```bash
# From Mac — copy source trees to WLANPi
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    ~/source/wlanpi-core   wlanpi@wlanpi-XXX.local:~/source/
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    ~/source/wlanpi-fpms2  wlanpi@wlanpi-XXX.local:~/source/
```

Then SSH in for all subsequent steps:

```bash
ssh wlanpi@wlanpi-XXX.local
```

---

## Part 1 — wlanpi-core-dev

This runs your local copy of wlanpi-core directly on port **8000**, separate from the production instance on port 80.

### 1.1 Install system dependencies

`dbus-python` (a wlanpi-core dependency) requires native dbus headers and cannot be built from source by pip alone. Install the system package first so pip can use it:

```bash
sudo apt-get update
sudo apt-get install -y \
    python3-venv python3-pip git \
    libdbus-1-dev libglib2.0-dev python3-dbus \
    build-essential pkg-config
```

### 1.2 Stop and disable the production wlanpi-core

The production wlanpi-core runs via gunicorn on a unix socket (proxied by nginx on port 80). Stop it before starting the dev instance to avoid conflicts with the shared secret file and DBus resources:

```bash
sudo systemctl stop wlanpi-core wlanpi-core.socket
sudo systemctl disable wlanpi-core wlanpi-core.socket
```

> **To restore later:** `sudo systemctl enable --now wlanpi-core.socket wlanpi-core`

### 1.3 Create the venv and install (wlanpi-core)

Create the venv with `--system-site-packages` so the pip-installed `dbus-python` wheel from apt is visible inside it (avoids the meson build error):

```bash
cd ~/source/wlanpi-core
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -U pip wheel setuptools
pip install .
deactivate
```

### 1.4 Install the dev systemd service

Create `/etc/systemd/system/wlanpi-core-dev.service`:

```bash
sudo tee /etc/systemd/system/wlanpi-core-dev.service > /dev/null << 'EOF'
[Unit]
Description=WLANPi Core DEV (port 8000)
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/home/wlanpi/source/wlanpi-core
ExecStart=/home/wlanpi/source/wlanpi-core/venv/bin/python -m wlanpi_core --port 8000
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wlanpi-core-dev
sudo systemctl start wlanpi-core-dev
sudo systemctl status wlanpi-core-dev
```

### 1.5 Verify wlanpi-core-dev is running

The shared secret lives at `/home/wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin` (created automatically on first run by the production wlanpi-core install). The dev instance reads the same file, so HMAC auth works immediately.

Quick smoke test:

```bash
# Read the secret as hex
secret=$(xxd -p -c 256 /home/wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin | tr -d '\n')

# Sign a GET /api/v1/system/device/info request
path="/api/v1/system/device/info"
sig=$(printf 'GET\n%s\n\n' "$path" | openssl dgst -sha256 -mac hmac \
    -macopt "hexkey:$secret" | awk '{print $2}')

curl -s -H "X-Request-Signature: $sig" \
    "http://localhost:8000${path}" | python3 -m json.tool
```

You should see device info JSON. If you get a 401, check the journal:

```bash
sudo journalctl -f -u wlanpi-core-dev
```

### 1.6 Updating wlanpi-core-dev after code changes

After editing files on your Mac and rsyncing:

```bash
# Re-sync from Mac
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    ~/source/wlanpi-core/ wlanpi@wlanpi-XXX.local:~/source/wlanpi-core/

# On the WLANPi — reinstall into venv (if pyproject/setup.py changed)
cd ~/source/wlanpi-core && source venv/bin/activate && pip install . && deactivate

# Restart the service
sudo systemctl restart wlanpi-core-dev
```

If you only changed `.py` files (not `pyproject.toml`/`setup.py`), reinstalling isn't needed — just restart the service.

---

## Part 2 — wlanpi-fpms2

### 2.1 Install system dependencies

```bash
sudo apt-get install -y python3-venv python3-pip git
# For screen client (SPI, GPIO):
sudo apt-get install -y python3-spidev python3-gpiozero python3-rpi.gpio libgpiod-dev
```

### 2.2 Create the venv and install

```bash
cd ~/source/wlanpi-fpms2
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel setuptools
pip install .            # installs all core dependencies incl. qrcode, Pillow, textual
pip install .[screen]    # adds SPI/GPIO extras for the OLED client
deactivate
```

### 2.3 Point fpms2 at wlanpi-core-dev

fpms2 defaults to `http://localhost/api/v1` (the production nginx proxy). For dev, override this with an environment variable so it talks to port 8000 instead:

```bash
export WLANPI_CORE_BASE_URL=http://localhost:8000/api/v1
```

This environment variable is read by the state service at startup. Add it to the systemd unit (see §2.4) so it persists across reboots.

### 2.4 Stop the production FPMS and install dev systemd units

Stop the production fpms (leave wlanpi-core running on port 80 — it doesn't conflict):

```bash
sudo systemctl stop wlanpi-fpms
sudo systemctl disable wlanpi-fpms
```

Create `/etc/systemd/system/wlanpi-fpms2.service`:

```bash
sudo tee /etc/systemd/system/wlanpi-fpms2.service > /dev/null << 'EOF'
[Unit]
Description=WLANPi FPMS2 State Service (dev)
After=network.target
Conflicts=wlanpi-fpms.service

[Service]
Type=simple
User=wlanpi
Group=wlanpi
WorkingDirectory=/home/wlanpi/source/wlanpi-fpms2
ExecStart=/home/wlanpi/source/wlanpi-fpms2/.venv/bin/wlanpi-fpms2
Restart=on-failure
RestartSec=5
Environment=WLANPI_CORE_BASE_URL=http://localhost:8000/api/v1

[Install]
WantedBy=multi-user.target
EOF
```

Create `/etc/systemd/system/wlanpi-fpms2-screen.service`:

```bash
sudo tee /etc/systemd/system/wlanpi-fpms2-screen.service > /dev/null << 'EOF'
[Unit]
Description=WLANPi FPMS2 Screen Client (dev)
After=wlanpi-fpms2.service
Requires=wlanpi-fpms2.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/home/wlanpi/source/wlanpi-fpms2
ExecStart=/home/wlanpi/source/wlanpi-fpms2/.venv/bin/wlanpi-fpms2-screen
Restart=on-failure
RestartSec=3
TimeoutStopSec=10
Environment=WLANPI_STATE_URL=http://127.0.0.1:8765

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start both:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wlanpi-fpms2 wlanpi-fpms2-screen
sudo systemctl start wlanpi-fpms2
sudo systemctl start wlanpi-fpms2-screen
sudo systemctl status wlanpi-fpms2 wlanpi-fpms2-screen
```

### 2.5 Verify fpms2 is running

```bash
# State service health
curl http://127.0.0.1:8765/health

# Current state JSON
curl http://127.0.0.1:8765/state | python3 -m json.tool

# WebSocket stream (Ctrl-C to stop)
# Requires: pip install websockets (on your Mac or on device)
python3 -c "
import asyncio, websockets, json
async def watch():
    async with websockets.connect('ws://127.0.0.1:8765/ws') as ws:
        while True:
            msg = json.loads(await ws.recv())
            print(msg.get('type'), msg.get('state', {}).get('nav'))
asyncio.run(watch())
"
```

### 2.6 Use the Textual TUI (SSH)

```bash
# On the WLANPi — run as wlanpi user, no root needed
source ~/source/wlanpi-fpms2/.venv/bin/activate
wlanpi-fpms2-tui
```

Arrow keys navigate, Enter/→ selects, ← goes back, `q` quits. The TUI and OLED stay in sync — navigating in one updates the other.

### 2.7 Set up the Cockpit plugin

The Cockpit plugin is a static set of files in `cockpit/` — no build step required. Cockpit loads plugins by looking in `~/.local/share/cockpit/` for per-user plugins. Create a symlink so changes to your repo are reflected immediately without copying:

On a fresh WLANPi, `/home/wlanpi/.local` is owned by root. Fix that first, then create the symlink:

```bash
sudo chown -R wlanpi:wlanpi /home/wlanpi/.local
mkdir -p /home/wlanpi/.local/share/cockpit
ln -sf /home/wlanpi/source/wlanpi-fpms2/cockpit \
    /home/wlanpi/.local/share/cockpit/wlanpi-fpms2
```

Cockpit picks up the new plugin without a restart. Verify it is detected:

```bash
sudo cockpit-bridge --packages 2>/dev/null | grep -i wlanpi || \
    ls ~/.local/share/cockpit/
```

Then open Cockpit in your browser:

```
https://wlanpi-XXX.local:9090
```

Log in as `wlanpi`, and **WLANPi FPMS** should appear in the left-hand navigation menu. The plugin polls the fpms2 state service on `127.0.0.1:8765` via the Cockpit bridge transport — it will show a "○ Connecting" badge until `wlanpi-fpms2` is running.

> **Troubleshooting:** If the menu item doesn't appear, try a hard-refresh (`Cmd+Shift+R` / `Ctrl+Shift+R`) or an incognito window. Cockpit aggressively caches plugin lists. You can also check the browser console for any JS errors.

---

## Part 3 — Testing API endpoints

The test script at `scripts/test_phase4b_endpoints.sh` (in wlanpi-core repo) tests all Phase 4b endpoints against wlanpi-core-dev:

```bash
cd ~/source/wlanpi-core

# Read-only tests
bash scripts/test_phase4b_endpoints.sh

# Include write/mutating tests (timezone auto-detect, reg domain, etc.)
bash scripts/test_phase4b_endpoints.sh --write
```

---

## Part 4 — Logs and Debugging

### fpms2 state service

```bash
sudo journalctl -f -u wlanpi-fpms2
```

### Screen client

```bash
sudo journalctl -f -u wlanpi-fpms2-screen
```

### wlanpi-core-dev

```bash
sudo journalctl -f -u wlanpi-core-dev
```

---

## Part 5 — Updating after code changes

After editing on your Mac and rsyncing:

```bash
# Re-sync fpms2
rsync -av --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
    ~/source/wlanpi-fpms2/ wlanpi@wlanpi-XXX.local:~/source/wlanpi-fpms2/

# Restart on the WLANPi
sudo systemctl restart wlanpi-fpms2
# Screen client auto-restarts because it requires wlanpi-fpms2
```

If `pyproject.toml` changed (new dependency):

```bash
cd ~/source/wlanpi-fpms2
source .venv/bin/activate
pip install .
pip install .[screen]
deactivate
sudo systemctl restart wlanpi-fpms2 wlanpi-fpms2-screen
```

---

## Part 6 — Restoring production

To restore the original wlanpi-fpms and stop the dev services:

```bash
sudo systemctl stop wlanpi-fpms2-screen wlanpi-fpms2 wlanpi-core-dev
sudo systemctl disable wlanpi-fpms2-screen wlanpi-fpms2 wlanpi-core-dev
sudo systemctl enable --now wlanpi-core.socket wlanpi-core
sudo systemctl enable --now wlanpi-fpms
```

To remove the Cockpit plugin:

```bash
rm ~/.local/share/cockpit/wlanpi-fpms2
```

---

## Quick-reference: environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WLANPI_CORE_BASE_URL` | `http://localhost/api/v1` | Which wlanpi-core fpms2 calls |
| `WLANPI_STATE_URL` | `http://127.0.0.1:8765` | Which fpms2 state service the screen client connects to |
| `WLANPI_CORE_SECRET_PATH` | `/home/wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin` | HMAC shared secret location |
