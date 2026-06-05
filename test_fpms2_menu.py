import urllib.request
import urllib.error
import json
import time

nodes = [
    "network.interfaces",
    "network.wlan_interfaces",
    "network.eth0_ipconfig",
    "network.eth0_vlan",
    "network.lldp",
    "network.cdp",
    "network.publicip4",
    "network.publicip6",
    "bluetooth.status",
    "utils.reachability",
    "utils.ssid_passphrase",
    "utils.usb",
    "utils.ufw",
    "system.about",
    "system.summary",
    "system.battery",
    "apps.profiler.status",
    "system.settings.datetime.show",
    "system.settings.rf.show"
]

def get_state():
    req = urllib.request.Request("http://localhost:8765/state")
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

def navigate(node_id):
    data = json.dumps({"node_id": node_id}).encode('utf-8')
    req = urllib.request.Request("http://localhost:8765/navigate", data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f"ERROR: {node_id} HTTP Error {e.code}")
        return False
    return True

for node in nodes:
    if not navigate(node):
        continue
    # wait for loading to finish
    max_wait = 10
    state = None
    while max_wait > 0:
        time.sleep(0.5)
        state = get_state()
        if not state.get("loading", True):
            break
        max_wait -= 1
        
    if state:
        page = state.get("page", {}) or {}
        alert = page.get("alert") if page else None
        
        if page and page.get("title") == "Error":
            print(f"FAIL: {node} returned error page: {page.get('lines')}")
        elif alert and alert.get("level") == "error":
            print(f"FAIL: {node} returned error alert: {alert.get('message')}")
        else:
            print(f"OK: {node}")
    else:
        print(f"TIMEOUT: {node}")
