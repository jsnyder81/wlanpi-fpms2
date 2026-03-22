"""Action registry — maps action_id strings to async handler functions.

Phase 2: real implementations for network, system, bluetooth, utils.
         Stubs remain for actions that need wlanpi-core gap endpoints.
"""

from __future__ import annotations

from wlanpi_fpms2.actions import network, system, bluetooth, utils
from wlanpi_fpms2.actions.apps import profiler, kismet, scanner


def build_action_registry() -> dict:
    return {
        # Network
        "network.interfaces":      network.show_interfaces,
        "network.wlan_interfaces": network.show_wlan_interfaces,
        "network.eth0_ipconfig":   network.show_eth0_ipconfig,
        "network.eth0_vlan":       network.show_eth0_vlan,
        "network.lldp":            network.show_lldp,
        "network.cdp":             network.show_cdp,
        "network.publicip4":       network.show_publicip4,
        "network.publicip6":       network.show_publicip6,

        # Bluetooth
        "bluetooth.status": bluetooth.bluetooth_status,
        "bluetooth.on":     bluetooth.bluetooth_on,
        "bluetooth.off":    bluetooth.bluetooth_off,
        "bluetooth.pair":   bluetooth.bluetooth_pair,

        # Utils
        "utils.reachability":      utils.show_reachability,
        "utils.speedtest":         utils.show_speedtest,
        "utils.cloud.arista":      utils.test_arista,
        "utils.cloud.aruba":       utils.test_aruba,
        "utils.cloud.extreme":     utils.test_extreme,
        "utils.cloud.meraki":      utils.test_meraki,
        "utils.cloud.mist":        utils.test_mist,
        "utils.cloud.ruckus":      utils.test_ruckus,
        "utils.port_blinker.start": utils.port_blinker_start,
        "utils.port_blinker.stop":  utils.port_blinker_stop,
        "utils.ssid_passphrase":    utils.show_ssid_passphrase,
        "utils.usb":                utils.show_usb,
        "utils.ufw":                utils.show_ufw,

        # Modes
        "modes.hotspot": utils.switch_to_hotspot,
        "modes.server":  utils.switch_to_server,
        "modes.bridge":  utils.switch_to_bridge,
        "modes.classic": utils.switch_to_classic,

        # Apps — Profiler
        "apps.profiler.status":       profiler.profiler_status,
        "apps.profiler.stop":         profiler.profiler_stop,
        "apps.profiler.start":        profiler.profiler_start,
        "apps.profiler.start_2_4":    profiler.profiler_start_2_4,
        "apps.profiler.start_5_36":   profiler.profiler_start_5_36,
        "apps.profiler.start_5_149":  profiler.profiler_start_5_149,
        "apps.profiler.start_no11r":  profiler.profiler_start_no11r,
        "apps.profiler.start_no11ax": profiler.profiler_start_no11ax,
        "apps.profiler.purge_reports": profiler.profiler_purge_reports,
        "apps.profiler.purge_files":   profiler.profiler_purge_files,

        # Apps — Kismet
        "apps.kismet.start": kismet.kismet_start,
        "apps.kismet.stop":  kismet.kismet_stop,

        # Apps — Scanner
        "apps.scanner.scan":         scanner.scanner_scan,
        "apps.scanner.scan_nohidden": scanner.scanner_scan_nohidden,
        "apps.scanner.csv":          scanner.scanner_csv,
        "apps.scanner.pcap_start":   scanner.scanner_pcap_start,
        "apps.scanner.pcap_stop":    scanner.scanner_pcap_stop,

        # System
        "system.about":           system.show_about,
        "system.help":            system.show_help,
        "system.summary":         system.show_summary,
        "system.battery":         system.show_battery,
        "system.date":            system.show_date,
        "system.timezone.auto":   system.set_timezone_auto,
        "system.timezone.set":    system.set_timezone,
        "system.reg_domain.show": system.show_reg_domain,
        "system.reg_domain.set_us": system.set_reg_domain_us,
        "system.reg_domain.set_br": system.set_reg_domain_br,
        "system.reg_domain.set_ca": system.set_reg_domain_ca,
        "system.reg_domain.set_cz": system.set_reg_domain_cz,
        "system.reg_domain.set_de": system.set_reg_domain_de,
        "system.reg_domain.set_fr": system.set_reg_domain_fr,
        "system.reg_domain.set_gb": system.set_reg_domain_gb,
        "system.reg_domain.set_nl": system.set_reg_domain_nl,
        "system.reg_domain.set_no": system.set_reg_domain_no,
        "system.rotate_display":    system.rotate_display,
        "system.updates.check":     system.check_updates,
        "system.updates.install":   system.install_updates,
        "system.reboot":            system.reboot,
        "system.shutdown":          system.shutdown,
    }
