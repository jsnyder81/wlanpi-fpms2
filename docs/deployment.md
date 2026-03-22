# wlanpi-fpms2 — Deployment Guide

These instructions assume the repository is cloned directly on the WLANPi.

---

## Prerequisites

```bash
# wlanpi-core must be installed and running
systemctl status wlanpi-core

# Python 3.11+
python3 --version

# git (to clone the repo)
git --version

# SPI must be enabled in /boot/firmware/config.txt (or /boot/config.txt)
grep spi /boot/firmware/config.txt
# Look for: dtparam=spi=on
```

If SPI is not enabled, add it and reboot:

```bash
echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

---

## 1. Clone the repository

```bash
git clone https://github.com/WLAN-Pi/wlanpi-fpms2.git
cd wlanpi-fpms2
```

---

## 2. Create a virtualenv and install

```bash
sudo python3 -m venv /opt/wlanpi-fpms2
sudo /opt/wlanpi-fpms2/bin/pip install --upgrade pip
sudo /opt/wlanpi-fpms2/bin/pip install -e .
```

The pip upgrade is required because the system pip shipped with Debian is
too old to support editable installs from `pyproject.toml` (needs pip ≥ 21.3).
The `-e` flag installs in editable mode — you can `git pull` and changes
take effect after a service restart, with no reinstall needed.

---

## 3. Install the systemd service units

```bash
sudo cp debian/wlanpi-fpms2.service        /etc/systemd/system/
sudo cp debian/wlanpi-fpms2-screen.service /etc/systemd/system/
sudo systemctl daemon-reload
```

---

## 4. Create the command symlinks

```bash
sudo ln -sf /opt/wlanpi-fpms2/bin/wlanpi-fpms2        /usr/bin/wlanpi-fpms2
sudo ln -sf /opt/wlanpi-fpms2/bin/wlanpi-fpms2-screen /usr/bin/wlanpi-fpms2-screen
sudo ln -sf /opt/wlanpi-fpms2/bin/wlanpi-fpms2-tui    /usr/bin/wlanpi-fpms2-tui
```

---

## 5. Stop wlanpi-fpms and start wlanpi-fpms2

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

## 6. Smoke test (no hardware needed)

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

# Watch live state changes over WebSocket (requires wscat: npm i -g wscat)
wscat -c ws://127.0.0.1:8765/ws
```

---

## Updating after a code change

```bash
cd ~/wlanpi-fpms2
git pull
sudo systemctl restart wlanpi-fpms2 wlanpi-fpms2-screen
```

Because the package is installed in editable mode, the restart picks up
changes immediately — no reinstall required.

If `pyproject.toml` dependencies change (new packages added), run:

```bash
sudo /opt/wlanpi-fpms2/bin/pip install -e .
sudo systemctl restart wlanpi-fpms2 wlanpi-fpms2-screen
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
