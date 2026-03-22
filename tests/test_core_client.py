"""Tests for CoreApiClient using respx to mock httpx."""

import pytest
import respx
import httpx

from wlanpi_fpms2.core_client.client import CoreApiClient
from wlanpi_fpms2.core_client.hmac_auth import sign_request, HmacAuth
from wlanpi_fpms2.core_client.models import (
    BluetoothStatus,
    DeviceInfo,
    DeviceStats,
    ReachabilityTest,
)

# Use a fixed test secret to avoid needing the file on disk
_TEST_SECRET = b"test-secret-32-bytes-fixed-value"


@pytest.fixture
def client():
    return CoreApiClient(
        base_url="http://localhost/api/v1",
        secret=_TEST_SECRET,
    )


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------

class TestHmacSigning:
    def test_sign_request_returns_hex_string(self):
        sig = sign_request("GET", "/api/v1/system/device/info", secret=_TEST_SECRET)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex digest

    def test_sign_request_is_deterministic(self):
        sig1 = sign_request("GET", "/test", secret=_TEST_SECRET)
        sig2 = sign_request("GET", "/test", secret=_TEST_SECRET)
        assert sig1 == sig2

    def test_sign_request_differs_by_method(self):
        sig_get  = sign_request("GET",  "/test", secret=_TEST_SECRET)
        sig_post = sign_request("POST", "/test", secret=_TEST_SECRET)
        assert sig_get != sig_post

    def test_sign_request_includes_query_params(self):
        sig_no_q = sign_request("GET", "/test", secret=_TEST_SECRET)
        sig_with_q = sign_request("GET", "/test", query_params={"name": "foo"}, secret=_TEST_SECRET)
        assert sig_no_q != sig_with_q

    def test_sign_request_includes_body(self):
        sig_empty = sign_request("POST", "/test", body=b"", secret=_TEST_SECRET)
        sig_body  = sign_request("POST", "/test", body=b'{"key":"val"}', secret=_TEST_SECRET)
        assert sig_empty != sig_body

    def test_hmac_auth_adds_header(self):
        auth = HmacAuth(secret=_TEST_SECRET)
        request = httpx.Request("GET", "http://localhost/api/v1/system/device/info")
        # Run auth flow
        for r in auth.auth_flow(request):
            pass
        assert "X-Request-Signature" in r.headers


# ---------------------------------------------------------------------------
# CoreApiClient — mocked HTTP responses
# ---------------------------------------------------------------------------

@pytest.mark.respx(base_url="http://localhost")
class TestCoreApiClientSystem:
    async def test_get_device_info(self, client, respx_mock):
        respx_mock.get("/api/v1/system/device/info").mock(return_value=httpx.Response(
            200,
            json={
                "model": "WLANPi Pro",
                "name": "wlanpi",
                "hostname": "wlanpi.local",
                "software_version": "3.2.0",
                "mode": "classic",
            },
        ))
        info = await client.get_device_info()
        assert isinstance(info, DeviceInfo)
        assert info.model == "WLANPi Pro"
        assert info.mode == "classic"

    async def test_get_device_stats(self, client, respx_mock):
        respx_mock.get("/api/v1/system/device/stats").mock(return_value=httpx.Response(
            200,
            json={
                "ip": "192.168.1.1",
                "cpu": "CPU Load: 0.15",
                "ram": "Mem: 256/512MB 50.00%",
                "disk": "Disk: 4/16GB 25%",
                "cpu_temp": "45.0",
                "uptime": "2h 15m",
            },
        ))
        stats = await client.get_device_stats()
        assert isinstance(stats, DeviceStats)
        assert stats.ip == "192.168.1.1"

    async def test_get_service_status(self, client, respx_mock):
        respx_mock.get("/api/v1/system/service/status").mock(return_value=httpx.Response(
            200, json={"name": "wlanpi-profiler", "active": True},
        ))
        svc = await client.get_service_status("wlanpi-profiler")
        assert svc.active is True

    async def test_start_service(self, client, respx_mock):
        respx_mock.post("/api/v1/system/service/start").mock(
            return_value=httpx.Response(200, json={"name": "kismet", "active": True})
        )
        result = await client.start_service("kismet")
        assert result["active"] is True


@pytest.mark.respx(base_url="http://localhost")
class TestCoreApiClientBluetooth:
    async def test_get_bluetooth_status(self, client, respx_mock):
        respx_mock.get("/api/v1/bluetooth/status").mock(return_value=httpx.Response(
            200,
            json={
                "name": "WLANPi",
                "alias": "WLANPi",
                "addr": "AA:BB:CC:DD:EE:FF",
                "power": "on",
                "paired_devices": [],
            },
        ))
        bt = await client.get_bluetooth_status()
        assert isinstance(bt, BluetoothStatus)
        assert bt.power == "on"

    async def test_set_bluetooth_power_on(self, client, respx_mock):
        respx_mock.post("/api/v1/bluetooth/power/on").mock(
            return_value=httpx.Response(200, json={"status": "success", "action": "on"})
        )
        result = await client.set_bluetooth_power(on=True)
        assert result["action"] == "on"


@pytest.mark.respx(base_url="http://localhost")
class TestCoreApiClientUtils:
    async def test_get_reachability(self, client, respx_mock):
        respx_mock.get("/api/v1/utils/reachability").mock(return_value=httpx.Response(
            200,
            json={
                "Ping Google": "ok",
                "Browse Google": "ok",
                "Ping Gateway": "ok",
                "Arping Gateway": "ok",
            },
        ))
        reach = await client.get_reachability()
        assert isinstance(reach, ReachabilityTest)
        assert reach.ping_google == "ok"

    async def test_get_reachability_to_lines(self, client, respx_mock):
        respx_mock.get("/api/v1/utils/reachability").mock(return_value=httpx.Response(
            200,
            json={
                "Ping Google": "ok",
                "Browse Google": "ok",
                "Ping Gateway": "fail",
                "Arping Gateway": "ok",
            },
        ))
        reach = await client.get_reachability()
        lines = reach.to_lines()
        assert any("Ping Google" in l for l in lines)
        assert any("ok" in l for l in lines)

    async def test_http_error_raises(self, client, respx_mock):
        respx_mock.get("/api/v1/utils/reachability").mock(
            return_value=httpx.Response(503)
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_reachability()


@pytest.mark.respx(base_url="http://localhost")
class TestCoreApiClientNetwork:
    async def test_get_interfaces(self, client, respx_mock):
        respx_mock.get("/api/v1/network/interfaces").mock(return_value=httpx.Response(
            200,
            json={
                "interfaces": [
                    {
                        "ifindex": 2,
                        "ifname": "eth0",
                        "flags": ["UP", "RUNNING"],
                        "mtu": 1500,
                        "operstate": "UP",
                        "link_type": "ether",
                        "address": "aa:bb:cc:dd:ee:ff",
                        "addr_info": [
                            {"family": "inet", "local": "192.168.1.100", "prefixlen": 24}
                        ],
                    }
                ]
            },
        ))
        ifaces = await client.get_interfaces()
        assert "interfaces" in ifaces
        eth0 = ifaces["interfaces"][0]
        assert eth0.ifname == "eth0"
        assert eth0.ipv4_addresses() == ["192.168.1.100/24"]
