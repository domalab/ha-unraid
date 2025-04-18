"""Unit tests for parsing command output in the Unraid integration."""
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from custom_components.unraid.api.ssh_client import UnraidSSHClient
from custom_components.unraid.api.command_parser import (
    parse_disk_info,
    parse_temperature_data,
    parse_docker_containers,
    parse_vm_list,
    parse_network_info,
    parse_ups_status,
    parse_parity_check_status,
)


class TestDiskInfoParsing:
    """Test parsing disk information command output."""

    def test_parse_lsblk_output(self):
        """Test parsing lsblk command output."""
        # Sample lsblk output
        lsblk_output = """NAME   SIZE FSTYPE MOUNTPOINT UUID MODEL
sda    8.0T xfs    /mnt/disk1  abcd1234 WDC_WD80EFAX-68LHPN0
sdb    4.0T xfs    /mnt/disk2  efgh5678 WDC_WD40EFRX-68WT0N0
nvme0n1 512G btrfs /mnt/cache  ijkl9012 Samsung_SSD_970_EVO_Plus_500GB
"""
        
        # Parse the output
        parsed_disks = parse_disk_info(lsblk_output)
        
        # Verify the results
        assert len(parsed_disks) == 3
        
        assert parsed_disks[0]["name"] == "sda"
        assert parsed_disks[0]["size"] == "8.0T"
        assert parsed_disks[0]["fstype"] == "xfs"
        assert parsed_disks[0]["mountpoint"] == "/mnt/disk1"
        assert parsed_disks[0]["uuid"] == "abcd1234"
        assert parsed_disks[0]["model"] == "WDC_WD80EFAX-68LHPN0"
        
        assert parsed_disks[1]["name"] == "sdb"
        assert parsed_disks[1]["mountpoint"] == "/mnt/disk2"
        
        assert parsed_disks[2]["name"] == "nvme0n1"
        assert parsed_disks[2]["fstype"] == "btrfs"
        assert parsed_disks[2]["model"] == "Samsung_SSD_970_EVO_Plus_500GB"

    def test_parse_df_output(self):
        """Test parsing df command output."""
        # Sample df output
        df_output = """Filesystem      Size  Used Avail Use% Mounted on
/dev/sda        8.0T  5.1T  2.9T  64% /mnt/disk1
/dev/sdb        4.0T  3.7T  0.3T  93% /mnt/disk2
/dev/nvme0n1    512G  210G  302G  41% /mnt/cache
"""
        
        # Parse the output
        parsed_usage = parse_disk_info(df_output, output_type="df")
        
        # Verify the results
        assert len(parsed_usage) == 3
        
        assert parsed_usage[0]["device"] == "/dev/sda"
        assert parsed_usage[0]["size"] == "8.0T"
        assert parsed_usage[0]["used"] == "5.1T"
        assert parsed_usage[0]["available"] == "2.9T"
        assert parsed_usage[0]["use_percent"] == "64%"
        assert parsed_usage[0]["mount_point"] == "/mnt/disk1"
        
        assert parsed_usage[1]["device"] == "/dev/sdb"
        assert parsed_usage[1]["use_percent"] == "93%"
        
        assert parsed_usage[2]["device"] == "/dev/nvme0n1"
        assert parsed_usage[2]["use_percent"] == "41%"

    def test_parse_smart_output(self):
        """Test parsing smartctl command output."""
        # Sample smartctl output
        smart_output = """smartctl 7.1 2019-03-31 r4903 [x86_64-linux-5.10.28-Unraid] (local build)
Copyright (C) 2002-19, Bruce Allen, Christian Franke, www.smartmontools.org

=== START OF INFORMATION SECTION ===
Model Family:     Western Digital Red
Device Model:     WDC WD80EFAX-68LHPN0
Serial Number:    ABCDEF123456
Firmware Version: 83.H0A83
User Capacity:    8,001,563,222,016 bytes [8.00 TB]
Sector Size:      4096 bytes logical/physical
Rotation Rate:    5400 rpm
SMART support is: Available - device has SMART capability.
SMART support is: Enabled

=== START OF SMART DATA SECTION ===
SMART overall-health self-assessment test result: PASSED

SMART Attributes Data Structure revision number: 16
Vendor Specific SMART Attributes with Thresholds:
ID# ATTRIBUTE_NAME          FLAGS    VALUE WORST THRESH FAIL RAW_VALUE
  1 Raw_Read_Error_Rate     POSR-K   100   100   051    -    0
  3 Spin_Up_Time            POS--K   177   175   021    -    5600
  4 Start_Stop_Count        -O--CK   100   100   000    -    18
  5 Reallocated_Sector_Ct   PO--CK   200   200   140    -    0
  7 Seek_Error_Rate         -OSR-K   200   200   000    -    0
  9 Power_On_Hours          -O--CK   098   098   000    -    1789
 10 Spin_Retry_Count        -O--CK   100   100   000    -    0
 11 Calibration_Retry_Count -O--CK   100   100   000    -    0
 12 Power_Cycle_Count       -O--CK   100   100   000    -    18
192 Power-Off_Retract_Count -O--CK   200   200   000    -    12
193 Load_Cycle_Count        -O--CK   200   200   000    -    49
194 Temperature_Celsius     -O---K   122   109   000    -    34
196 Reallocated_Event_Count -O--CK   200   200   000    -    0
197 Current_Pending_Sector  -O--CK   200   200   000    -    0
198 Offline_Uncorrectable   ----CK   100   253   000    -    0
199 UDMA_CRC_Error_Count    -O--CK   200   200   000    -    0
200 Multi_Zone_Error_Rate   ---R--   100   253   000    -    0

SMART Error Log Version: 1
No Errors Logged
"""
        
        # Parse the output
        parsed_smart = parse_disk_info(smart_output, output_type="smart")
        
        # Verify the results
        assert parsed_smart["model"] == "WDC WD80EFAX-68LHPN0"
        assert parsed_smart["serial"] == "ABCDEF123456"
        assert parsed_smart["capacity"] == "8,001,563,222,016 bytes [8.00 TB]"
        assert parsed_smart["health"] == "PASSED"
        assert parsed_smart["temperature"] == 34
        assert parsed_smart["power_on_hours"] == 1789
        assert parsed_smart["smart_attributes"]["Raw_Read_Error_Rate"] == 0
        assert parsed_smart["smart_attributes"]["Reallocated_Sector_Ct"] == 0


class TestTemperatureParsing:
    """Test parsing temperature command output."""

    def test_parse_sensors_output(self):
        """Test parsing sensors command output."""
        # Sample sensors output in JSON format
        sensors_json = """
{
  "coretemp-isa-0000": {
    "Adapter": "ISA adapter",
    "Package id 0": {
      "temp1_input": 45.0,
      "temp1_max": 100.0,
      "temp1_crit": 100.0
    },
    "Core 0": {
      "temp2_input": 42.0,
      "temp2_max": 100.0,
      "temp2_crit": 100.0
    },
    "Core 1": {
      "temp3_input": 43.0,
      "temp3_max": 100.0,
      "temp3_crit": 100.0
    }
  },
  "nvme-pci-0100": {
    "Adapter": "PCI adapter",
    "Composite": {
      "temp1_input": 38.85,
      "temp1_max": 81.85,
      "temp1_min": -273.15,
      "temp1_crit": 84.85
    }
  }
}
"""
        
        # Parse the output
        parsed_temps = parse_temperature_data(sensors_json)
        
        # Verify the results
        assert "cpu" in parsed_temps
        assert parsed_temps["cpu"] == 45.0
        assert "core0" in parsed_temps
        assert parsed_temps["core0"] == 42.0
        assert "core1" in parsed_temps
        assert parsed_temps["core1"] == 43.0
        assert "nvme" in parsed_temps
        assert parsed_temps["nvme"] == 38.85


class TestDockerParsing:
    """Test parsing Docker command output."""

    def test_parse_docker_ps_output(self):
        """Test parsing docker ps command output."""
        # Sample docker ps output
        docker_ps = """CONTAINER ID   IMAGE                             COMMAND                  CREATED      STATUS          PORTS     NAMES
abc123def456   homeassistant/home-assistant:latest   "/init"                   2 days ago   Up 2 days                 homeassistant
def456ghi789   plexinc/pms-docker:latest            "/init"                   2 days ago   Up 2 days                 plex
jkl012mno345   linuxserver/radarr:latest            "/init"                   2 days ago   Exited (0) 1 day ago     radarr"""
        
        # Parse the output
        parsed_containers = parse_docker_containers(docker_ps)
        
        # Verify the results
        assert len(parsed_containers) == 3
        
        assert parsed_containers[0]["id"] == "abc123def456"
        assert parsed_containers[0]["image"] == "homeassistant/home-assistant:latest"
        assert parsed_containers[0]["command"] == "/init"
        assert parsed_containers[0]["created"] == "2 days ago"
        assert parsed_containers[0]["status"] == "Up 2 days"
        assert parsed_containers[0]["name"] == "homeassistant"
        assert parsed_containers[0]["state"] == "running"
        
        assert parsed_containers[1]["name"] == "plex"
        assert parsed_containers[1]["state"] == "running"
        
        assert parsed_containers[2]["name"] == "radarr"
        assert parsed_containers[2]["state"] == "exited"


class TestVMParsing:
    """Test parsing VM command output."""

    def test_parse_virsh_list_output(self):
        """Test parsing virsh list command output."""
        # Sample virsh list output
        virsh_list = """ Id   Name          State
-----------------------------
 1    Windows10     running
 -    Ubuntu20.04   shut off
 -    MacOS         shut off
"""
        
        # Parse the output
        parsed_vms = parse_vm_list(virsh_list)
        
        # Verify the results
        assert len(parsed_vms) == 3
        
        assert parsed_vms[0]["id"] == "1"
        assert parsed_vms[0]["name"] == "Windows10"
        assert parsed_vms[0]["state"] == "running"
        
        assert parsed_vms[1]["name"] == "Ubuntu20.04"
        assert parsed_vms[1]["state"] == "shut off"
        
        assert parsed_vms[2]["name"] == "MacOS"
        assert parsed_vms[2]["state"] == "shut off"


class TestNetworkParsing:
    """Test parsing network command output."""

    def test_parse_ip_addr_output(self):
        """Test parsing ip addr command output."""
        # Sample ip addr output
        ip_addr = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host 
       valid_lft forever preferred_lft forever
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP group default qlen 1000
    link/ether 00:11:22:33:44:55 brd ff:ff:ff:ff:ff:ff
    inet 192.168.1.10/24 brd 192.168.1.255 scope global eth0
       valid_lft forever preferred_lft forever
    inet6 fe80::211:22ff:fe33:4455/64 scope link 
       valid_lft forever preferred_lft forever
3: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    link/ether 00:11:22:33:44:56 brd ff:ff:ff:ff:ff:ff
    inet 192.168.1.11/24 brd 192.168.1.255 scope global br0
       valid_lft forever preferred_lft forever
    inet6 fe80::211:22ff:fe33:4456/64 scope link 
       valid_lft forever preferred_lft forever
"""
        
        # Parse the output
        parsed_interfaces = parse_network_info(ip_addr)
        
        # Verify the results
        assert len(parsed_interfaces) == 3
        
        assert parsed_interfaces[0]["name"] == "lo"
        assert parsed_interfaces[0]["mac"] == "00:00:00:00:00:00"
        assert parsed_interfaces[0]["ipv4"] == "127.0.0.1/8"
        assert parsed_interfaces[0]["ipv6"] == "::1/128"
        assert parsed_interfaces[0]["state"] == "UNKNOWN"
        
        assert parsed_interfaces[1]["name"] == "eth0"
        assert parsed_interfaces[1]["mac"] == "00:11:22:33:44:55"
        assert parsed_interfaces[1]["ipv4"] == "192.168.1.10/24"
        assert parsed_interfaces[1]["state"] == "UP"
        
        assert parsed_interfaces[2]["name"] == "br0"
        assert parsed_interfaces[2]["ipv4"] == "192.168.1.11/24"


class TestUPSParsing:
    """Test parsing UPS command output."""

    def test_parse_upsc_output(self):
        """Test parsing upsc command output."""
        # Sample upsc output
        upsc_output = """battery.charge: 100
battery.runtime: 7200
battery.voltage: 27.0
device.mfr: APC
device.model: Smart-UPS 1500
device.serial: AS1234567890
device.type: ups
driver.name: usbhid-ups
driver.parameter.pollfreq: 30
driver.parameter.pollinterval: 2
driver.parameter.port: auto
driver.version: 2.7.4
driver.version.internal: 0.41
input.voltage: 230.0
output.current: 0.70
output.frequency: 50.0
output.voltage: 230.0
ups.beeper.status: enabled
ups.delay.shutdown: 20
ups.delay.start: 30
ups.load: 23
ups.mfr: APC
ups.model: Smart-UPS 1500
ups.serial: AS1234567890
ups.status: OL
ups.temperature: 25.0
ups.timer.reboot: 0
ups.timer.shutdown: -1"""
        
        # Parse the output
        parsed_ups = parse_ups_status(upsc_output)
        
        # Verify the results
        assert parsed_ups["battery_charge"] == 100
        assert parsed_ups["battery_runtime"] == 7200
        assert parsed_ups["model"] == "Smart-UPS 1500"
        assert parsed_ups["serial"] == "AS1234567890"
        assert parsed_ups["load"] == 23
        assert parsed_ups["status"] == "OL"
        assert parsed_ups["temperature"] == 25.0
        assert parsed_ups["input_voltage"] == 230.0


class TestParityParsing:
    """Test parsing parity check command output."""

    def test_parse_mdstat_output(self):
        """Test parsing /proc/mdstat output."""
        # Sample mdstat output
        mdstat_output = """Personalities : [raid1] [raid0] [raid10] [raid6] [raid5] [raid4] 
md0 : active raid1 sdb1[1] sda1[0]
      4095996 blocks super 1.0 [2/2] [UU]
      [=========>...........]  check = 45.3% (1855552/4095996) finish=2.1min speed=17498K/sec
      bitmap: 0/1 pages [0KB], 65536KB chunk

unused devices: <none>"""
        
        # Parse the output
        parsed_parity = parse_parity_check_status(mdstat_output)
        
        # Verify the results
        assert parsed_parity["active"] == True
        assert parsed_parity["progress"] == 45.3
        assert parsed_parity["speed"] == "17498K/sec"
        assert parsed_parity["finish"] == "2.1min"
        assert parsed_parity["device"] == "md0"

    def test_parse_parity_log_output(self):
        """Test parsing parity check log output."""
        # Sample parity check log
        parity_log = """Apr 12 00:00:01 unraid kernel: md: data-check of RAID array md0
Apr 12 01:23:45 unraid kernel: md: md0: data-check completed (41093/41093 blocks) in 5400 seconds
Apr 11 22:30:00 unraid kernel: md: data-check of RAID array md0
Apr 11 23:59:59 unraid kernel: md: md0: data-check aborted after 3600 seconds
"""
        
        # Parse the output
        parsed_log = parse_parity_check_status(parity_log, output_type="log")
        
        # Verify the results
        assert parsed_log["last_check"] == "Apr 12 01:23:45"
        assert parsed_log["last_status"] == "completed"
        assert parsed_log["last_duration"] == 5400
        assert parsed_log["previous_check"] == "Apr 11 22:30:00"
        assert parsed_log["previous_status"] == "aborted"
        assert parsed_log["previous_duration"] == 3600 