import asyncio
from wlanpi_fpms2.core_client.client import CoreApiClient
from wlanpi_fpms2.core_client.hmac_auth import _DEFAULT_SECRET_PATH

async def main():
    secret = _DEFAULT_SECRET_PATH.read_bytes()
    endpoints = [
        "get_device_info",
        "get_device_stats",
        "get_bluetooth_status",
        "get_wlan_interfaces",
        "get_network_info",
        "get_reachability",
        "get_usb",
        "get_ufw",
        "get_timezone",
        "list_timezones",
        "get_reg_domain",
        "get_updates",
        "get_battery",
        "get_datetime",
        "get_ssid_passphrase",
        "get_connected_clients",
        "get_public_ipv6",
        "get_profiler_status",
    ]
    
    async with CoreApiClient(base_url="http://localhost:31415/api/v1", secret=secret) as client:
        for name in endpoints:
            func = getattr(client, name)
            try:
                await func()
                print(f"OK: {name}")
            except Exception as e:
                print(f"ERROR: {name} - {type(e).__name__}: {e}")
                
        try:
            await client.get_service_status("kismet")
            print("OK: get_service_status")
        except Exception as e:
            print(f"ERROR: get_service_status - {type(e).__name__}: {e}")
            
        try:
            await client.get_interfaces()
            print("OK: get_interfaces")
        except Exception as e:
            print(f"ERROR: get_interfaces - {type(e).__name__}: {e}")

        try:
            await client.get_vlans("eth0")
            print("OK: get_vlans")
        except Exception as e:
            print(f"ERROR: get_vlans - {type(e).__name__}: {e}")

asyncio.run(main())
