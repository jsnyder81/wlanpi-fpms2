# wlanpi-fpms2 — Deployment Guide

Two deployment paths are documented here:

| Path | When to use |
|---|---|
| **Wheel (quick)** | Active development — copy a wheel to the device and pip-install |
| **Debian package** | Production / CI — proper `.deb` built with `dpkg-buildpackage` |

---

## Prerequisites (on the WLANPi device)

```bash
# wlanpi-core must be installed and running
systemctl status wlanpi-core

# Python 3.11+
python3 --version

# SPI must be enabled in /boot/firmware/config.txt (or /boot/config.txt)
# Look for: dtparam=spi=on
grep spi /boot/firmware/config.txt
```

If SPI is not enabled, add `dtparam=spi=on` to the config file and reboot.

---

## Path 1 — Wheel (quick, for active development)

### 1. Build the wheel on your Mac

```bash
cd /Users/jakesnyder/source/wlanpi-fpms2
python3 -m pip install build   # one-time
python3 -m build --wheel
# Produces: dist/wlanpi_fpms2-0.1.0-py3-none-any.whl
```

### 2. Copy to the WLANPi

```bash
scp dist/wlanpi_fpms2-*.whl wlanpi@wlanpi.local:/tmp/
```

### 3. Install on the WLANPi

```bash
ssh wlanpi@wlanpi.local

# Install into a dedicated virtualenv (recommended — keeps system Python clean)
sudo python3 -m venv /opt/wlanpi-fpms2
sudo /opt/wlanpi-fpms2/bin/pip install /tmp/wlanpi_fpms2-*.whl

# Or, if you prefer a plain user-level install (no venv):
pip3 install --user /tmp/wlanpi_fpms2-*.whl
```

### 4. Install the systemd service units

The service files live in the source tree. Copy them from your Mac or from
the installed package:

```bash
# From your Mac (replace <your-mac-ip> as needed):
scp debian/wlanpi-fpms2.service         wlanpi@wlanpi.local:/tmp/
scp debian/wlanpi-fpms2-screen.service  wlanpi@wlanpi.local:/tmp/

# On the WLANPi:
ssh wlanpi@wlanpi.local
sudo cp /tmp/wlanpi-fpms2.service        /etc/systemd/system/
sudo cp /tmp/wlanpi-fpms2-screen.service /etc/systemd/system/
```

Edit the `ExecStart` paths in the unit files if you used a custom install
location (default assumes `/opt/wlanpi-fpms2/bin/`):

```bash
sudo nano /etc/systemd/system/wlanpi-fpms2.service
# ExecStart=/opt/wlanpi-fpms2/bin/wlanpi-fpms2
```

### 5. Enable and start the services

```bash
# Stop the old fpms first (they conflict)
sudo systemctl stop wlanpi-fpms
sudo systemctl disable wlanpi-fpms

# Enable and start fpms2
sudo systemctl daemon-reload
sudo systemctl enable  wlanpi-fpms2.service wlanpi-fpms2-screen.service
sudo systemctl start   wlanpi-fpms2.service
sudo systemctl start   wlanpi-fpms2-screen.service

# Check status
sudo systemctl status wlanpi-fpms2.service
sudo systemctl status wlanpi-fpms2-screen.service

# Live logs
sudo journalctl -u wlanpi-fpms2 -f
sudo journalctl -u wlanpi-fpms2-screen -f
```

### 6. Quick smoke test (no hardware needed)

```bash
# On the WLANPi — verify the state service responds
curl http://127.0.0.1:8765/health
# → {"status":"ok","version":"0.1.0"}

curl http://127.0.0.1:8765/state | python3 -m json.tool

# Simulate a button press
curl -X POST http://127.0.0.1:8765/input \
     -H 'Content-Type: application/json' \
     -d '{"button":"down"}'
# → {"status":"ok"}

# Connect a WebSocket and watch state changes (requires wscat: npm i -g wscat)
wscat -c ws://127.0.0.1:8765/ws
```

### Iterating quickly (re-deploy after code changes)

```bash
# On your Mac:
python3 -m build --wheel && scp dist/wlanpi_fpms2-*.whl wlanpi@wlanpi.local:/tmp/

# On the WLANPi:
sudo systemctl stop wlanpi-fpms2-screen wlanpi-fpms2
sudo /opt/wlanpi-fpms2/bin/pip install --force-reinstall /tmp/wlanpi_fpms2-*.whl
sudo systemctl start wlanpi-fpms2 wlanpi-fpms2-screen
```

---

## Path 2 — Debian package (production / CI)

The Debian package builds a self-contained virtualenv at `/opt/wlanpi-fpms2`
using [dh-virtualenv](https://github.com/spotify/dh-virtualenv), the same
toolchain used by `wlanpi-fpms`.

### Build dependencies (on a Debian/Raspberry Pi OS build machine)

```bash
sudo apt-get update
sudo apt-get install -y \
    debhelper \
    dh-python \
    dh-virtualenv \
    python3 \
    python3-dev \
    python3-venv \
    python3-setuptools \
    pkg-config \
    libjpeg-dev \
    libopenjp2-7-dev \
    zlib1g-dev \
    libfreetype6-dev
```

> **Cross-compilation note:** Packages with compiled C extensions (e.g.
> Pillow) must be built on the same architecture as the target (ARM64 for
> CM4/RPi4). Use an ARM64 VM, a native WLANPi, or GitHub Actions
> (`runs-on: ubuntu-latest` with `qemu-user-static`).

### Build the package

```bash
cd /path/to/wlanpi-fpms2
dpkg-buildpackage -us -uc -b
# Produces: ../wlanpi-fpms2_0.1.0_arm64.deb
```

### Install the .deb on the WLANPi

```bash
# Copy the .deb to the device
scp ../wlanpi-fpms2_*.deb wlanpi@wlanpi.local:/tmp/

# Install (automatically stops wlanpi-fpms, enables SPI, reloads systemd)
ssh wlanpi@wlanpi.local
sudo dpkg -i /tmp/wlanpi-fpms2_*.deb

# Fix any missing dependencies if needed
sudo apt-get install -f
```

The `postinst` script automatically:
- Creates `/usr/bin/wlanpi-fpms2*` symlinks
- Enables `dtparam=spi=on` in `/boot/firmware/config.txt`
- Runs `systemctl daemon-reload` and enables both services

### Start the services (first install)

The services are enabled but not started automatically (to allow a reboot
after SPI is enabled). After the reboot, they start on their own.
Or start them manually without rebooting if SPI was already enabled:

```bash
sudo systemctl start wlanpi-fpms2.service
sudo systemctl start wlanpi-fpms2-screen.service
```

---

## Reverting to wlanpi-fpms

```bash
sudo systemctl stop  wlanpi-fpms2-screen wlanpi-fpms2
sudo systemctl disable wlanpi-fpms2-screen wlanpi-fpms2
sudo systemctl enable  wlanpi-fpms
sudo systemctl start   wlanpi-fpms
```

Or, if you installed via `.deb`:

```bash
sudo dpkg --remove wlanpi-fpms2
sudo systemctl start wlanpi-fpms
```

---

## Environment variable reference

| Variable | Default | Description |
|---|---|---|
| `WLANPI_STATE_URL` | `http://127.0.0.1:8765` | State service base URL (used by screen client) |
| `WLANPI_SCREEN_DRIVER` | auto | Force display driver: `luma` or `st7735` |
| `WLANPI_BUTTON_MAP` | auto | JSON dict overriding GPIO pin→button mapping |
| `WLANPI_CORE_SECRET_PATH` | `/home/wlanpi/.local/share/wlanpi-core/secrets/shared_secret.bin` | Path to HMAC shared secret |
| `WLANPI_CORE_BASE_URL` | `http://localhost/api/v1` | wlanpi-core API base URL |

Set these in the systemd unit's `[Service]` section as `Environment=KEY=value`.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Screen stays blank | `journalctl -u wlanpi-fpms2-screen` — likely SPI not enabled or wrong driver |
| `loading...` appears but never resolves | `journalctl -u wlanpi-fpms2` — wlanpi-core probably unreachable |
| Buttons do nothing | Check `WLANPI_BUTTON_MAP` or GPIO pin map; verify `/dev/gpiochip0` exists |
| `/health` returns 500 | wlanpi-core secret file not found — check `WLANPI_CORE_SECRET_PATH` |
| State service won't start | Check port 8765 is free: `ss -tlnp | grep 8765` |
