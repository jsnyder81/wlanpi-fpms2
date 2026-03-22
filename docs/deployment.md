# wlanpi-fpms2 — Deployment Guide

These instructions assume both `wlanpi-core` and `wlanpi-fpms2` are cloned
directly on the WLANPi and run from source.

---

## Part A — wlanpi-core (from source)

The production wlanpi-core package runs via gunicorn on a Unix socket proxied
by nginx at `http://localhost/api/v1`. When running from source it binds
directly to `http://localhost:8000` instead. We stop the system service and
run from source so code changes take effect immediately.

### A1. Clone the repository

```bash
mkdir -p ~/source && cd ~/source
git clone https://github.com/WLAN-Pi/wlanpi-core.git
cd wlanpi-core
```

### A2. Install build dependencies and create a virtualenv

`dbus-python` (a wlanpi-core dependency) is a C extension that requires
system development libraries:

```bash
sudo apt-get install -y libdbus-1-dev libglib2.0-dev
```

Then create the virtualenv and install:

```bash
python3 -m venv venv
venv/bin/pip install -U pip
venv/bin/pip install -e .
```

### A3. Stop the system wlanpi-core service

```bash
sudo systemctl stop    wlanpi-core
sudo systemctl disable wlanpi-core
```

### A4. Run wlanpi-core from source

```bash
sudo venv/bin/python -m wlanpi_core --reload
```

wlanpi-core is now listening on `http://localhost:8000/api/v1`.

To run it as a background service during development, create a simple override:

```bash
sudo tee /etc/systemd/system/wlanpi-core-dev.service > /dev/null <<'EOF'
[Unit]
Description=wlanpi-core (dev, from source)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/wlanpi/source/wlanpi-core
ExecStart=/home/wlanpi/source/wlanpi-core/venv/bin/python -m wlanpi_core
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now wlanpi-core-dev.service
```

### A5. Verify wlanpi-core is running

All data endpoints require HMAC auth, so use the unauthenticated API index instead:

```bash
curl -s http://localhost:8000/api/v1 | head -5
```

Any HTML response confirms the service is up. Getting `{"detail":"Missing signature header"}` on a data endpoint also confirms it is running — that's the auth check, not a startup error.

---

## Part B — wlanpi-fpms2 (from source)

Before starting Part B, confirm SPI is enabled (required for the OLED display):

```bash
grep spi /boot/firmware/config.txt   # look for: dtparam=spi=on
```

If not present:

```bash
echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

---

## B1. Clone the repository

```bash
cd ~/source
git clone https://github.com/WLAN-Pi/wlanpi-fpms2.git
cd wlanpi-fpms2
```

---

## B2. Create a virtualenv and install

```bash
sudo python3 -m venv /opt/wlanpi-fpms2
sudo /opt/wlanpi-fpms2/bin/pip install --upgrade pip
sudo /opt/wlanpi-fpms2/bin/pip install -e ".[screen]"
```

The pip upgrade is required because the system pip shipped with Debian is
too old to support editable installs from `pyproject.toml` (needs pip ≥ 21.3).
The `-e` flag installs in editable mode — you can `git pull` and changes
take effect after a service restart, with no reinstall needed.

---

## B3. Install the systemd service units

```bash
sudo cp debian/wlanpi-fpms2.service        /etc/systemd/system/
sudo cp debian/wlanpi-fpms2-screen.service /etc/systemd/system/
sudo systemctl daemon-reload
```

---

## B4. Create the command symlinks

```bash
sudo ln -sf /opt/wlanpi-fpms2/bin/wlanpi-fpms2        /usr/bin/wlanpi-fpms2
sudo ln -sf /opt/wlanpi-fpms2/bin/wlanpi-fpms2-screen /usr/bin/wlanpi-fpms2-screen
sudo ln -sf /opt/wlanpi-fpms2/bin/wlanpi-fpms2-tui    /usr/bin/wlanpi-fpms2-tui
```

---

## B5. Point fpms2 at the from-source wlanpi-core

Because wlanpi-core is running on port 8000 (not behind nginx), override the
default API URL in the state service unit:

```bash
sudo mkdir -p /etc/systemd/system/wlanpi-fpms2.service.d
sudo tee /etc/systemd/system/wlanpi-fpms2.service.d/core-url.conf > /dev/null <<'EOF'
[Service]
Environment=WLANPI_CORE_BASE_URL=http://localhost:8000/api/v1
EOF
sudo systemctl daemon-reload
```

## B6. Stop wlanpi-fpms and start wlanpi-fpms2

The two packages conflict and cannot run at the same time.

```bash
sudo systemctl stop    wlanpi-fpms
sudo systemctl disable wlanpi-fpms

sudo systemctl enable wlanpi-fpms2.service wlanpi-fpms2-screen.service
sudo systemctl start  wlanpi-fpms2.service wlanpi-fpms2-screen.service
```

Check that both services are running:

```bash
sudo systemctl status wlanpi-fpms2.service
sudo systemctl status wlanpi-fpms2-screen.service
```

Follow the logs live:

```bash
sudo journalctl -u wlanpi-fpms2 -f
sudo journalctl -u wlanpi-fpms2-screen -f
```

---

## B7. Smoke test (no hardware needed)

```bash
# State service health check
curl http://127.0.0.1:8765/health
# → {"status":"ok","version":"0.1.0"}

# Full state snapshot
curl http://127.0.0.1:8765/state | python3 -m json.tool

# Simulate a button press
curl -X POST http://127.0.0.1:8765/input \
     -H 'Content-Type: application/json' \
     -d '{"button":"down"}'
# → {"status":"ok"}

# Watch live state changes over WebSocket (requires websocat: apt install websocat)
websocat ws://127.0.0.1:8765/ws
```

---

## Updating after a code change

**wlanpi-fpms2:**

```bash
cd ~/source/wlanpi-fpms2
git pull
sudo systemctl restart wlanpi-fpms2 wlanpi-fpms2-screen
```

Because both packages are installed in editable mode, a restart picks up
changes immediately — no reinstall required.

If `pyproject.toml` dependencies change (new packages added):

```bash
sudo /opt/wlanpi-fpms2/bin/pip install -e ".[screen]"
sudo systemctl restart wlanpi-fpms2 wlanpi-fpms2-screen
```

**wlanpi-core:**

```bash
cd ~/source/wlanpi-core
git pull
sudo systemctl restart wlanpi-core-dev
```

---

## Reverting to wlanpi-fpms

```bash
sudo systemctl stop    wlanpi-fpms2-screen wlanpi-fpms2
sudo systemctl disable wlanpi-fpms2-screen wlanpi-fpms2
sudo systemctl enable  wlanpi-fpms
sudo systemctl start   wlanpi-fpms
```

---

## Building a Debian package (optional, for distribution)

Run this on the WLANPi itself (or any ARM64 Debian build host):

```bash
sudo apt-get install -y debhelper dh-python dh-virtualenv \
    python3-dev python3-venv python3-setuptools \
    libjpeg-dev libopenjp2-7-dev zlib1g-dev libfreetype6-dev

cd ~/wlanpi-fpms2
dpkg-buildpackage -us -uc -b
# Produces: ../wlanpi-fpms2_0.1.0_arm64.deb

sudo dpkg -i ../wlanpi-fpms2_*.deb
sudo apt-get install -f   # fix any missing dependencies
```

The `postinst` script handles symlinks, SPI config, and `systemctl enable`
automatically. Reboot (or `systemctl start` both services) to activate.

---

## Environment variable reference

| Variable | Default | Description |
|---|---|---|
| `WLANPI_STATE_URL` | `http://127.0.0.1:8765` | State service URL (used by screen client) |
| `WLANPI_SCREEN_DRIVER` | auto | Force driver: `luma` or `st7735` |
| `WLANPI_BUTTON_MAP` | auto | JSON dict overriding GPIO pin→button mapping |
| `WLANPI_CORE_SECRET_PATH` | `/home/wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin` | HMAC shared secret path |
| `WLANPI_CORE_BASE_URL` | `http://localhost/api/v1` | wlanpi-core API base URL |

Set these in the systemd unit's `[Service]` section as `Environment=KEY=value`.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Screen stays blank | `journalctl -u wlanpi-fpms2-screen` — likely SPI not enabled or wrong driver |
| `Loading...` never resolves | `journalctl -u wlanpi-fpms2` — wlanpi-core probably unreachable |
| Buttons do nothing | Verify `WLANPI_BUTTON_MAP` / GPIO pins; check `/dev/gpiochip0` exists |
| `/health` returns 500 | wlanpi-core secret file missing — check `WLANPI_CORE_SECRET_PATH` |
| State service won't start | Port 8765 already in use: `ss -tlnp \| grep 8765` |
