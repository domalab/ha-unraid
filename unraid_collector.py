#!/usr/bin/env python3
"""
Standalone Unraid data collector.
This tool connects to an Unraid server via SSH, collects system information,
and saves it to a JSON file for analysis.
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any

try:
    import asyncssh
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TaskProgressColumn
    from rich.table import Table
    from rich.markup import escape
    from rich.layout import Layout
    from rich.text import Text
    from rich import box
except ImportError:
    print("Required packages missing. Install with: pip install asyncssh tqdm rich")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Changed from DEBUG to INFO to reduce console output
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_LOGGER = logging.getLogger("unraid_collector")

# Add a stream handler to also print to console, but set to INFO
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)
_LOGGER.addHandler(console_handler)

# Create a global console for rich output
rich_console = Console()

class UnraidCollector:
    """Collects data from an Unraid server via SSH."""

    def __init__(self, host: str, username: str, password: str, port: int = 22) -> None:
        """Initialize the collector with connection parameters."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.conn = None
        self.data = {}
        self.command_timeout = 60  # Default command timeout in seconds

    async def connect(self) -> None:
        """Connect to the Unraid server via SSH."""
        _LOGGER.info(f"Connecting to {self.username}@{self.host}:{self.port}")
        try:
            self.conn = await asyncssh.connect(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                known_hosts=None  # In production, you should validate host keys
            )
            _LOGGER.info("Connected successfully")
        except (asyncssh.Error, OSError) as exc:
            _LOGGER.error(f"Connection failed: {exc}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from the Unraid server."""
        if self.conn:
            self.conn.close()
            await self.conn.wait_closed()
            _LOGGER.info("Disconnected from server")

    async def run_command(self, command: str) -> str:
        """Run a command on the Unraid server."""
        if not self.conn:
            await self.connect()

        _LOGGER.debug(f"Running command: {command}")
        result = await self.conn.run(command, timeout=self.command_timeout)
        if result.exit_status != 0:
            _LOGGER.warning(f"Command exited with status {result.exit_status}: {result.stderr}")

        return result.stdout

    async def collect_system_stats(self) -> Dict[str, Any]:
        """Collect basic system statistics."""
        _LOGGER.info("Collecting system statistics")

        result = {}

        # Get CPU info
        cpu_info_raw = await self.run_command("lscpu")
        result["cpu_info_raw"] = cpu_info_raw

        # Extract core count and model
        try:
            for line in cpu_info_raw.splitlines():
                if "CPU(s):" in line and "NUMA" not in line:
                    result["cpu_cores"] = int(line.split(":")[1].strip())
                if "Model name:" in line:
                    result["cpu_model"] = line.split(":")[1].strip()
        except (ValueError, IndexError) as e:
            _LOGGER.warning(f"Failed to parse CPU info: {e}")

        # Get memory usage
        mem_info = await self.run_command("cat /proc/meminfo")
        result["memory_info_raw"] = mem_info

        # Extract memory values
        try:
            mem_total = 0
            mem_available = 0

            for line in mem_info.splitlines():
                if "MemTotal:" in line:
                    mem_total = int(line.split()[1])
                elif "MemAvailable:" in line:
                    mem_available = int(line.split()[1])

            mem_used = mem_total - mem_available

            result["memory_usage"] = {
                "total": mem_total,
                "free": mem_available,
                "used": mem_used,
                "percentage": round((mem_used / mem_total) * 100, 1) if mem_total > 0 else 0,
            }
        except (ValueError, IndexError) as e:
            _LOGGER.warning(f"Failed to parse memory info: {e}")

        # Get CPU usage
        cpu_usage_raw = await self.run_command("top -bn1 | grep '%Cpu'")
        result["cpu_usage_raw"] = cpu_usage_raw

        try:
            cpu_idle = float(cpu_usage_raw.split("id,")[0].split(",")[-1].strip())
            result["cpu_usage"] = round(100 - cpu_idle, 1)
        except (ValueError, IndexError) as e:
            _LOGGER.warning(f"Failed to parse CPU usage: {e}")
            result["cpu_usage"] = 0

        # Get uptime
        uptime_raw = await self.run_command("cat /proc/uptime")
        result["uptime_raw"] = uptime_raw

        try:
            uptime_seconds = float(uptime_raw.split()[0])
            result["uptime"] = uptime_seconds
        except (ValueError, IndexError) as e:
            _LOGGER.warning(f"Failed to parse uptime: {e}")

        # Get kernel version
        kernel_version = await self.run_command("uname -r")
        result["kernel_version"] = kernel_version.strip()

        # Get Unraid version
        unraid_version = await self.run_command("cat /etc/unraid-version")
        result["unraid_version"] = unraid_version.strip()

        # Get temperatures
        temperatures_raw = await self.run_command("sensors -j")
        try:
            result["temperatures"] = json.loads(temperatures_raw)
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse temperature data")
            result["temperatures_raw"] = temperatures_raw

        # Get CPU load data from Unraid
        cpuload_raw = await self.run_command("cat /var/local/emhttp/cpuload.ini 2>/dev/null || echo 'No cpuload data'")
        result["cpuload_raw"] = cpuload_raw

        # Get diskload data from Unraid
        diskload_raw = await self.run_command("cat /var/local/emhttp/diskload.ini 2>/dev/null || echo 'No diskload data'")
        result["diskload_raw"] = diskload_raw

        # Get system fan information (more detailed than sensors)
        fan_info = {}

        # Try to get fan speeds using ipmitool if available (works on many servers)
        ipmi_available = await self.run_command("which ipmitool >/dev/null 2>&1 && echo 'available' || echo 'not available'")
        if ipmi_available.strip() == "available":
            ipmi_fan_data = await self.run_command("ipmitool sdr type fan 2>/dev/null || echo 'No IPMI fan data'")
            if "No IPMI fan data" not in ipmi_fan_data:
                fan_info["ipmi_fans"] = ipmi_fan_data

        # Get fan information from sysfs
        hwmon_fans = await self.run_command("find /sys/class/hwmon/*/fan*_input -type f -exec bash -c 'echo \"$(cat {}): $(cat {})\"' \\; 2>/dev/null || echo 'No hwmon fan data'")
        if "No hwmon fan data" not in hwmon_fans:
            fan_info["hwmon_fans"] = hwmon_fans

        # Get fan control settings
        fan_control = await self.run_command("cat /boot/config/plugins/dynamix.system.temp/dynamix.system.temp.cfg 2>/dev/null || echo 'No fan control config'")
        fan_info["fan_control_config"] = fan_control

        result["fan_info"] = fan_info

        return result

    async def collect_disk_info(self) -> Dict[str, Any]:
        """Collect disk information."""
        _LOGGER.info("Collecting disk information")
        console = Console()

        result = {}

        console.print("[cyan]➜[/cyan] Collecting basic disk information...")

        # Get disk list
        disk_list_raw = await self.run_command("ls -la /dev/sd* /dev/nvme* 2>/dev/null || echo 'No disks found'")
        result["disk_list_raw"] = disk_list_raw

        # Get array status
        array_status_raw = await self.run_command("cat /proc/mdstat")
        result["array_status_raw"] = array_status_raw

        # Get detailed disk info
        df_output = await self.run_command("df -h")
        result["disk_usage_raw"] = df_output

        # Get individual disk details
        disks_raw = await self.run_command("lsblk -J -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE")
        try:
            disks_data = json.loads(disks_raw)
            result["disks_data"] = disks_data
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse disk JSON data")
            result["disks_data_raw"] = disks_raw

        # Get disk mappings from Unraid's config
        disk_mappings_raw = await self.run_command("cat /boot/config/disk.cfg || echo 'File not found'")
        result["disk_mappings_raw"] = disk_mappings_raw

        # Get disk spin-down configuration
        spindown_config_raw = await self.run_command("cat /boot/config/disk.cfg | grep -E 'spindown|spinup' || echo 'No spindown config'")
        result["spindown_config_raw"] = spindown_config_raw

        # Parse spin-down configuration
        spindown_config = {}
        for line in spindown_config_raw.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                spindown_config[key.strip()] = value.strip()
        result["spindown_config"] = spindown_config

        # Try to get a list of physical disks
        physical_disks_raw = await self.run_command("ls -1 /dev/sd* /dev/nvme*n* 2>/dev/null | sort")
        physical_disks = [disk.strip() for disk in physical_disks_raw.splitlines() if not disk.endswith(('p1', 'p2', 'p3'))]

        # Check disk spin status (specific to Unraid)
        disk_spin_status = {}
        hdparm_available = await self.run_command("which hdparm >/dev/null 2>&1 && echo 'available' || echo 'not available'")
        smartctl_available = await self.run_command("which smartctl >/dev/null 2>&1 && echo 'available' || echo 'not available'")

        console.print("[cyan]➜[/cyan] Checking disk spin status...")
        for disk in physical_disks:
            if not disk:  # Skip empty strings
                continue

            disk_name = os.path.basename(disk)

            # Initialize as unknown
            disk_spin_status[disk_name] = "unknown"

            # Try multiple methods to detect spin state

            # First try hdparm for SATA disks
            if disk_name.startswith("sd") and hdparm_available.strip() == "available":
                hdparm_output = await self.run_command(f"hdparm -C {disk} 2>/dev/null || echo 'unknown'")
                if "standby" in hdparm_output.lower():
                    disk_spin_status[disk_name] = "spun_down"
                elif "active" in hdparm_output.lower():
                    disk_spin_status[disk_name] = "active"

            # If state is still unknown, try smartctl (works with more disk types)
            if disk_spin_status[disk_name] == "unknown" and smartctl_available.strip() == "available":
                smartctl_output = await self.run_command(f"smartctl -n standby -i {disk} 2>/dev/null || echo 'unknown'")
                if "Device is in STANDBY mode" in smartctl_output or "STANDBY" in smartctl_output:
                    disk_spin_status[disk_name] = "spun_down"
                elif "Device is in ACTIVE or IDLE mode" in smartctl_output or "ACTIVE" in smartctl_output:
                    disk_spin_status[disk_name] = "active"

            # Last resort - check if the device is an SSD/NVMe (always "active")
            if disk_spin_status[disk_name] == "unknown":
                if disk_name.startswith("nvme"):
                    # NVMe drives don't spin down in the same way
                    disk_spin_status[disk_name] = "active"
                else:
                    # Check if it's an SSD using rotation rate
                    rotational = await self.run_command(f"cat /sys/block/{disk_name}/queue/rotational 2>/dev/null || echo '1'")
                    if rotational.strip() == "0":
                        # Non-rotational device (SSD)
                        disk_spin_status[disk_name] = "active"

        # Count disk states
        result["disk_spin_status"] = disk_spin_status

        # Get SMART data for each disk
        smart_data = {}

        console.print(f"[cyan]➜[/cyan] Retrieving SMART data for {len(physical_disks)} physical disks...")

        # Create progress bar for SMART data collection
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
            transient=True
        ) as progress:
            smart_task = progress.add_task("Collecting SMART data...", total=len(physical_disks))

            for disk in physical_disks:
                if not disk:  # Skip empty strings
                    progress.update(smart_task, advance=1)
                    continue

                disk_name = os.path.basename(disk)
                progress.update(smart_task, description=f"Reading SMART data: {disk_name}")

                # Check if disk is spun down before running SMART commands
                is_spun_down = disk_spin_status.get(disk_name) == "spun_down"
                if is_spun_down:
                    smart_info = {
                        "device": disk,
                        "spun_down": True,
                        "note": "Disk is spun down. Limited SMART data available without spinning up."
                    }

                    # Get minimal information without spinning up the disk
                    basic_info = await self.run_command(f"smartctl -i -n standby {disk} 2>/dev/null || echo 'SMART not available'")
                    smart_info["basic_info"] = basic_info

                    for line in basic_info.splitlines():
                        if "Device Model:" in line:
                            smart_info["model"] = line.split("Device Model:")[1].strip()
                        elif "Serial Number:" in line:
                            smart_info["serial"] = line.split("Serial Number:")[1].strip()
                else:
                    # Get full SMART data (this will spin up the disk if it's spun down)
                    smart_raw = await self.run_command(f"smartctl -a {disk} || echo 'SMART not available'")

                    # Extract basic info
                    smart_info = {
                        "device": disk,
                        "spun_down": False,
                        "raw_data": smart_raw,
                    }

                    # Parse some basic SMART attributes
                    try:
                        # Extract model
                        for line in smart_raw.splitlines():
                            if "Device Model:" in line:
                                smart_info["model"] = line.split("Device Model:")[1].strip()
                            elif "Serial Number:" in line:
                                smart_info["serial"] = line.split("Serial Number:")[1].strip()
                            elif "User Capacity:" in line:
                                capacity_str = line.split("[")[1].split("]")[0]
                                smart_info["capacity"] = capacity_str
                            elif "Rotation Rate:" in line:
                                if "Solid State" in line:
                                    smart_info["rotation_rate"] = 0
                                else:
                                    try:
                                        smart_info["rotation_rate"] = int(line.split("Rotation Rate:")[1].strip().split()[0])
                                    except (ValueError, IndexError):
                                        pass
                    except (IndexError, ValueError) as e:
                        _LOGGER.warning(f"Error parsing SMART data for {disk}: {e}")

                smart_data[disk_name] = smart_info
                progress.update(smart_task, advance=1)

        # Show disk type summary
        ssd_count = sum(1 for disk in smart_data.values() if disk.get("rotation_rate") == 0)
        hdd_count = len(smart_data) - ssd_count
        spun_down_count = sum(1 for disk in smart_data.values() if disk.get("spun_down", False))

        if smart_data:
            console.print(f"  [green]✓[/green] Found {len(smart_data)} disks: [blue]{ssd_count} SSD/NVMe[/blue], [magenta]{hdd_count} HDD[/magenta], [yellow]{spun_down_count} spun down[/yellow]")

        result["smart_data"] = smart_data

        return result

    async def collect_emhttp_configs(self) -> Dict[str, Any]:
        """Collect Unraid emhttp configuration files."""
        _LOGGER.info("Collecting Unraid emhttp configuration files")

        result = {}

        # List all files in /var/local/emhttp
        emhttp_files_raw = await self.run_command("ls -la /var/local/emhttp/ 2>/dev/null || echo 'No emhttp files'")
        result["emhttp_files_list"] = emhttp_files_raw

        # Collect key emhttp files
        key_files = [
            "shares.ini",
            "network.ini",
            "users.ini",
            "unassigned.devices.ini",
            "sec.ini",
            "sec_nfs.ini",
            "nginx.ini",
            "monitor.ini",
            "flashbackup.ini"
        ]

        for file in key_files:
            file_content = await self.run_command(f"cat /var/local/emhttp/{file} 2>/dev/null || echo 'File not found or empty'")
            if "File not found or empty" not in file_content:
                result[file] = file_content

        # Get SMART data
        smart_files_raw = await self.run_command("ls -la /var/local/emhttp/smart/ 2>/dev/null || echo 'No SMART data'")
        if "No SMART data" not in smart_files_raw:
            result["smart_files_list"] = smart_files_raw

            # Get a sample of SMART data files (first 2 only to prevent too much data)
            smart_sample_raw = await self.run_command("ls -1 /var/local/emhttp/smart/ | head -2 | xargs -I {} cat /var/local/emhttp/smart/{} 2>/dev/null")
            result["smart_data_sample"] = smart_sample_raw

        return result

    async def collect_gpu_info(self) -> Dict[str, Any]:
        """Collect detailed GPU information."""
        _LOGGER.info("Collecting GPU information")

        result = {}

        # Check for NVIDIA GPUs
        nvidia_smi_available = await self.run_command("which nvidia-smi >/dev/null 2>&1 && echo 'available' || echo 'not available'")
        if nvidia_smi_available.strip() == "available":
            _LOGGER.info("NVIDIA GPU detected")
            result["has_nvidia"] = True

            # Get basic NVIDIA GPU info
            nvidia_info = await self.run_command("nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used --format=csv,noheader 2>/dev/null || echo 'No NVIDIA data'")
            if "No NVIDIA data" not in nvidia_info:
                result["nvidia_info"] = nvidia_info

            # Get more detailed NVIDIA GPU stats
            nvidia_full = await self.run_command("nvidia-smi -q 2>/dev/null || echo 'No NVIDIA data'")
            if "No NVIDIA data" not in nvidia_full:
                result["nvidia_full"] = nvidia_full
        else:
            result["has_nvidia"] = False

        # Check for AMD GPUs
        amdgpu_available = await self.run_command("ls -la /sys/class/drm/*/device/vendor | grep 0x1002 >/dev/null 2>&1 && echo 'available' || echo 'not available'")
        if amdgpu_available.strip() == "available":
            _LOGGER.info("AMD GPU detected")
            result["has_amd"] = True

            # Get AMD GPU details using sysfs
            amd_cards_raw = await self.run_command("find /sys/class/drm/ -type d -name 'card[0-9]' 2>/dev/null")
            amd_cards = amd_cards_raw.splitlines()

            amd_info = {}
            for card in amd_cards:
                if not card:
                    continue

                card_name = os.path.basename(card)
                card_info = {}

                # Check if it's an AMD card
                vendor_raw = await self.run_command(f"cat {card}/device/vendor 2>/dev/null || echo 'unknown'")
                if "0x1002" not in vendor_raw:  # AMD vendor ID
                    continue

                # Get device name
                name_raw = await self.run_command(f"cat {card}/device/uevent | grep DRIVER 2>/dev/null || echo 'unknown'")
                card_info["driver"] = name_raw

                # Get power info
                power_raw = await self.run_command(f"cat {card}/device/power_dpm_force_performance_level 2>/dev/null || echo 'unknown'")
                card_info["power_level"] = power_raw.strip()

                # Get temperature if available
                temp_raw = await self.run_command(f"cat {card}/device/hwmon/hwmon*/temp1_input 2>/dev/null || echo 'unknown'")
                try:
                    if "unknown" not in temp_raw:
                        card_info["temperature"] = int(temp_raw.strip()) / 1000.0
                except (ValueError, IndexError):
                    pass

                # Get clock speeds
                sclk_raw = await self.run_command(f"cat {card}/device/pp_dpm_sclk 2>/dev/null || echo 'unknown'")
                if "unknown" not in sclk_raw:
                    card_info["core_clocks"] = sclk_raw

                mclk_raw = await self.run_command(f"cat {card}/device/pp_dpm_mclk 2>/dev/null || echo 'unknown'")
                if "unknown" not in mclk_raw:
                    card_info["memory_clocks"] = mclk_raw

                amd_info[card_name] = card_info

            result["amd_info"] = amd_info
        else:
            result["has_amd"] = False

        # Check for Intel GPUs
        intel_available = await self.run_command("ls -la /sys/class/drm/*/device/vendor | grep 0x8086 >/dev/null 2>&1 && echo 'available' || echo 'not available'")
        if intel_available.strip() == "available":
            _LOGGER.info("Intel GPU detected")
            result["has_intel"] = True

            # Get Intel GPU info
            intel_gpu_top_available = await self.run_command("which intel_gpu_top >/dev/null 2>&1 && echo 'available' || echo 'not available'")
            if intel_gpu_top_available.strip() == "available":
                # Run intel_gpu_top briefly to collect stats
                intel_gpu_info = await self.run_command("timeout 2 intel_gpu_top -J 2>/dev/null || echo 'No Intel GPU data'")
                if "No Intel GPU data" not in intel_gpu_info:
                    try:
                        result["intel_gpu_top"] = json.loads(intel_gpu_info)
                    except json.JSONDecodeError:
                        result["intel_gpu_top_raw"] = intel_gpu_info

            # Fallback to basic i915 info from sysfs
            i915_info = {}

            # Get driver info
            i915_driver = await self.run_command("cat /sys/module/i915/version 2>/dev/null || echo 'unknown'")
            i915_info["driver_version"] = i915_driver.strip()

            # Get frequency info
            i915_freq = await self.run_command("cat /sys/class/drm/card0/gt_cur_freq_mhz 2>/dev/null || echo 'unknown'")
            if "unknown" not in i915_freq:
                try:
                    i915_info["current_freq_mhz"] = int(i915_freq.strip())
                except ValueError:
                    i915_info["current_freq_raw"] = i915_freq.strip()

            # Get client/encoders info
            i915_clients = await self.run_command("find /sys/kernel/debug/dri/ -name clients -exec cat {} \\; 2>/dev/null || echo 'unknown'")
            if "unknown" not in i915_clients:
                i915_info["clients"] = i915_clients

            result["i915_info"] = i915_info
        else:
            result["has_intel"] = False

        # Check for GPU passthrough configuration
        gpu_passthrough = await self.run_command("grep -i 'vfio\\|pci-stub\\|iommu' /proc/cmdline || echo 'No GPU passthrough'")
        if "No GPU passthrough" not in gpu_passthrough:
            result["gpu_passthrough_config"] = gpu_passthrough

        # Check loaded GPU drivers
        gpu_drivers = await self.run_command("lsmod | grep -E 'nvidia|amdgpu|radeon|i915|nouveau' || echo 'No GPU drivers detected'")
        if "No GPU drivers detected" not in gpu_drivers:
            result["gpu_drivers"] = gpu_drivers

        return result

    async def collect_zfs_info(self) -> Dict[str, Any]:
        """Collect ZFS filesystem information."""
        _LOGGER.info("Collecting ZFS information")

        result = {}

        # Check if ZFS is installed and running
        zfs_available = await self.run_command("which zpool >/dev/null 2>&1 && echo 'available' || echo 'not available'")
        result["zfs_available"] = zfs_available.strip() == "available"

        if not result["zfs_available"]:
            _LOGGER.info("ZFS not installed")
            return result

        # Get ZFS module status
        zfs_module = await self.run_command("lsmod | grep zfs || echo 'ZFS module not loaded'")
        result["zfs_module"] = zfs_module

        # Get ZFS pool status
        zpool_status = await self.run_command("zpool status 2>/dev/null || echo 'No ZFS pools'")
        if "No ZFS pools" not in zpool_status:
            result["zpool_status"] = zpool_status

            # Get pool list
            zpool_list = await self.run_command("zpool list -H 2>/dev/null || echo 'No ZFS pools'")
            if "No ZFS pools" not in zpool_list:
                result["zpool_list"] = zpool_list

                # Parse pool names
                pools = [line.split()[0] for line in zpool_list.splitlines() if line.strip()]

                # Get detailed info for each pool
                pool_details = {}
                for pool in pools:
                    pool_info = {}

                    # Get pool properties
                    props = await self.run_command(f"zpool get all {pool} 2>/dev/null || echo 'No properties'")
                    pool_info["properties"] = props

                    # Get pool health
                    health = await self.run_command(f"zpool status {pool} | grep state: | awk '{{print $2}}' 2>/dev/null || echo 'unknown'")
                    pool_info["health"] = health.strip()

                    # Get datasets in this pool
                    datasets = await self.run_command(f"zfs list -r {pool} 2>/dev/null || echo 'No datasets'")
                    pool_info["datasets"] = datasets

                    # Get detailed dataset properties (for first few datasets only)
                    dataset_names = [line.split()[0] for line in datasets.splitlines()[1:5] if line.strip()]  # Limit to first 4
                    dataset_details = {}

                    for ds in dataset_names:
                        ds_props = await self.run_command(f"zfs get all {ds} 2>/dev/null || echo 'No properties'")
                        dataset_details[ds] = ds_props

                    pool_info["dataset_details"] = dataset_details

                    # Get pool history (last few lines only)
                    history = await self.run_command(f"zpool history {pool} | tail -n 20 2>/dev/null || echo 'No history'")
                    pool_info["history"] = history

                    pool_details[pool] = pool_info

                result["pool_details"] = pool_details

        # Get ZFS configuration
        zfs_config = await self.run_command("cat /etc/modprobe.d/zfs.conf 2>/dev/null || echo 'No ZFS config'")
        if "No ZFS config" not in zfs_config:
            result["zfs_config"] = zfs_config

        # Get ZFS cache files
        zfs_cache = await self.run_command("ls -la /etc/zfs/ 2>/dev/null || echo 'No ZFS cache'")
        if "No ZFS cache" not in zfs_cache:
            result["zfs_cache_files"] = zfs_cache

        # Get ZFS performance stats
        zfs_stats = await self.run_command("cat /proc/spl/kstat/zfs/arcstats 2>/dev/null || echo 'No ZFS stats'")
        if "No ZFS stats" not in zfs_stats:
            result["zfs_arcstats"] = zfs_stats

        return result

    async def collect_network_info(self) -> Dict[str, Any]:
        """Collect network information."""
        _LOGGER.info("Collecting network information")

        result = {}

        # Get interface list
        interfaces_raw = await self.run_command("ls -1 /sys/class/net/ | grep -v 'lo'")
        interfaces = [iface.strip() for iface in interfaces_raw.splitlines()]
        result["interfaces"] = interfaces

        # Get detailed interface info
        interface_details = {}
        for iface in interfaces:
            iface_info = {}

            # Get MAC address
            mac_raw = await self.run_command(f"cat /sys/class/net/{iface}/address 2>/dev/null || echo 'unknown'")
            iface_info["mac"] = mac_raw.strip()

            # Get operstate
            state_raw = await self.run_command(f"cat /sys/class/net/{iface}/operstate 2>/dev/null || echo 'unknown'")
            iface_info["state"] = state_raw.strip()

            # Get IP addresses
            ip_raw = await self.run_command(f"ip addr show {iface} | grep 'inet ' | awk '{{print $2}}'")
            iface_info["ipv4_addresses"] = [ip.strip() for ip in ip_raw.splitlines() if ip.strip()]

            # Get statistics
            rx_bytes_raw = await self.run_command(f"cat /sys/class/net/{iface}/statistics/rx_bytes 2>/dev/null || echo '0'")
            tx_bytes_raw = await self.run_command(f"cat /sys/class/net/{iface}/statistics/tx_bytes 2>/dev/null || echo '0'")

            try:
                iface_info["rx_bytes"] = int(rx_bytes_raw.strip())
                iface_info["tx_bytes"] = int(tx_bytes_raw.strip())
            except ValueError:
                iface_info["rx_bytes"] = 0
                iface_info["tx_bytes"] = 0

            interface_details[iface] = iface_info

        result["interface_details"] = interface_details

        return result

    async def collect_docker_info(self) -> Dict[str, Any]:
        """Collect Docker container information."""
        _LOGGER.info("Collecting Docker container information.")

        result = {}

        # Check if Docker is running using Unraid-specific methods
        try:
            # Unraid doesn't use systemctl - check process directly
            docker_pgrep = await self.run_command("ps aux | grep -v grep | grep -c 'dockerd'")
            docker_pids = int(docker_pgrep.strip()) if docker_pgrep.strip().isdigit() else 0
            _LOGGER.info(f"Docker processes running: {docker_pids}")

            # Check if docker socket exists
            docker_socket = await self.run_command("test -S /var/run/docker.sock && echo 'exists' || echo 'missing'")
            _LOGGER.info(f"Docker socket: {docker_socket.strip()}")

            # Try to list containers as definitive test
            docker_ps = await self.run_command("docker ps 2>/dev/null | grep -v CONTAINER | wc -l || echo '0'")
            docker_containers = int(docker_ps.strip()) if docker_ps.strip().isdigit() else 0
            _LOGGER.info(f"Running docker containers: {docker_containers}")

            # Get Unraid-specific Docker config location
            docker_config = await self.run_command("cat /boot/config/docker.cfg 2>/dev/null || echo 'No docker config'")
            result["docker_config"] = docker_config

            # Check Unraid's Docker settings
            docker_settings = await self.run_command("cat /boot/config/plugins/dockerMan/settings.cfg 2>/dev/null || echo 'No Docker settings'")
            result["docker_settings"] = docker_settings

            # Get Docker service file specific to Unraid
            docker_service = await self.run_command("cat /etc/rc.d/rc.docker 2>/dev/null || echo 'No docker service file'")
            result["docker_service_file"] = docker_service

            # Set docker_running based on containers or socket existence
            result["docker_running"] = docker_containers > 0 or docker_socket.strip() == "exists"
            _LOGGER.info(f"Docker running status: {result['docker_running']}")
        except Exception as e:
            _LOGGER.error(f"Error checking Docker status: {e}")
            result["docker_running"] = False

        if not result["docker_running"]:
            _LOGGER.info("Docker is not running")
            return result

        # Get container list
        try:
            containers_raw = await self.run_command("docker ps -a --format '{{json .}}'")
            containers = []

            for line in containers_raw.splitlines():
                if not line.strip():
                    continue
                try:
                    container = json.loads(line)
                    containers.append(container)
                except json.JSONDecodeError as e:
                    _LOGGER.warning(f"Failed to parse container JSON: {e}")

            result["containers"] = containers

            # Get Unraid-specific template files for Docker containers
            docker_templates_raw = await self.run_command("ls -la /boot/config/plugins/dockerMan/templates-user 2>/dev/null || echo 'No templates'")
            result["docker_templates_raw"] = docker_templates_raw

            # If templates exist, get a sample to understand format
            if "No templates" not in docker_templates_raw:
                template_sample = await self.run_command("head -n 20 /boot/config/plugins/dockerMan/templates-user/*.xml 2>/dev/null | head -n 20")
                result["docker_template_sample"] = template_sample

            # Get Docker network config (specific to Unraid's implementation)
            docker_networks = await self.run_command("docker network ls --format '{{json .}}'")
            networks = []
            for line in docker_networks.splitlines():
                if not line.strip():
                    continue
                try:
                    network = json.loads(line)
                    networks.append(network)
                except json.JSONDecodeError:
                    pass
            result["docker_networks"] = networks

            # Get detailed info for each running container
            container_details = {}
            for container in containers:
                container_id = container.get("ID", "")
                if not container_id:
                    continue

                _LOGGER.info(f"Getting details for container {container_id}")

                # Get container stats
                stats_raw = await self.run_command(f"docker stats {container_id} --no-stream --format '{{json .}}'")
                try:
                    stats = json.loads(stats_raw)
                    container_details[container_id] = {"stats": stats}
                except json.JSONDecodeError:
                    _LOGGER.warning(f"Failed to parse container stats for {container_id}")

                # Get container inspect info
                inspect_raw = await self.run_command(f"docker inspect {container_id}")
                try:
                    inspect = json.loads(inspect_raw)
                    container_details[container_id]["inspect"] = inspect
                except json.JSONDecodeError:
                    _LOGGER.warning(f"Failed to parse container inspect for {container_id}")

                # Get container logs (last few lines)
                logs_raw = await self.run_command(f"docker logs --tail 10 {container_id} 2>&1 || echo 'No logs available'")
                container_details[container_id]["recent_logs"] = logs_raw

            result["container_details"] = container_details

            # Get Docker storage info (Unraid specific - typically on an SSD cache)
            docker_storage = await self.run_command("du -sh /var/lib/docker 2>/dev/null || echo 'No docker storage info'")
            result["docker_storage_size"] = docker_storage

        except Exception as e:
            _LOGGER.error(f"Error collecting Docker information: {e}")
            result["error"] = str(e)

        return result

    async def collect_vm_info(self) -> Dict[str, Any]:
        """Collect VM information."""
        _LOGGER.info("Collecting VM information")

        result = {}

        # Check if libvirt/VM service is running using Unraid-specific methods
        try:
            # Check for libvirt process directly
            libvirt_pgrep = await self.run_command("ps aux | grep -v grep | grep -c 'libvirtd\\|qemu\\|kvm'")
            libvirt_pids = int(libvirt_pgrep.strip()) if libvirt_pgrep.strip().isdigit() else 0
            _LOGGER.info(f"VM/libvirt processes running: {libvirt_pids}")

            # Check if virsh works
            virsh_test = await self.run_command("virsh list --all 2>/dev/null | grep -v 'Id' | grep -v '----' | wc -l || echo '0'")
            virsh_vms = int(virsh_test.strip()) if virsh_test.strip().isdigit() else 0
            _LOGGER.info(f"VMs detected by virsh: {virsh_vms}")

            # Check if VM socket exists
            vm_socket = await self.run_command("test -S /var/run/libvirt/libvirt-sock && echo 'exists' || echo 'missing'")
            _LOGGER.info(f"Libvirt socket: {vm_socket.strip()}")

            # Check for Unraid's specific VM config location
            unraid_vm_cfg = await self.run_command("ls -la /boot/config/domain.cfg 2>/dev/null || echo 'No VM config'")
            result["unraid_vm_config"] = unraid_vm_cfg

            # Get Unraid VM plugin settings if available
            vm_settings = await self.run_command("cat /boot/config/plugins/dynamix.vm.manager/vm.cfg 2>/dev/null || echo 'No VM settings'")
            result["vm_settings"] = vm_settings

            # Get Unraid VM service file
            vm_service = await self.run_command("cat /etc/rc.d/rc.libvirt 2>/dev/null || echo 'No VM service file'")
            result["vm_service_file"] = vm_service

            # Set libvirt_running based on any positive indicator
            result["libvirt_running"] = libvirt_pids > 0 or virsh_vms > 0 or vm_socket.strip() == "exists"
            _LOGGER.info(f"VM/libvirt running status: {result['libvirt_running']}")
        except Exception as e:
            _LOGGER.error(f"Error checking VM/libvirt status: {e}")
            result["libvirt_running"] = False

        if not result["libvirt_running"]:
            _LOGGER.info("VM service is not running")
            return result

        # Get VM list
        vms_raw = await self.run_command("virsh list --all")
        result["vms_raw"] = vms_raw

        # Get Unraid VM settings (XML files)
        vm_xmls_raw = await self.run_command("ls -la /etc/libvirt/qemu/*.xml 2>/dev/null || echo 'No VM XML files'")
        result["vm_xml_files"] = vm_xmls_raw

        # Get Unraid VM image paths
        vm_img_paths_raw = await self.run_command("ls -la /mnt/user/domains/* 2>/dev/null || echo 'No VM images'")
        result["vm_image_paths"] = vm_img_paths_raw

        # Get VM storage directories (typically on a cache pool)
        vm_storage = await self.run_command("du -sh /mnt/user/domains 2>/dev/null || echo 'No VM storage info'")
        result["vm_storage_size"] = vm_storage

        # Parse VM list
        vms = []
        lines = vms_raw.splitlines()[2:]  # Skip header lines

        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                vm_id = parts[0]
                vm_name = parts[1]
                vm_state = " ".join(parts[2:])

                vms.append({
                    "id": vm_id,
                    "name": vm_name,
                    "state": vm_state
                })

        result["vms"] = vms

        # Get detailed info for each VM
        vm_details = {}
        for vm in vms:
            vm_name = vm.get("name")
            if not vm_name:
                continue

            _LOGGER.info(f"Getting details for VM {vm_name}")

            # Get VM XML
            xml_raw = await self.run_command(f"virsh dumpxml {vm_name}")
            vm_details[vm_name] = {"xml": xml_raw}

            # Get Unraid-specific VM template if it exists
            vm_template = await self.run_command(f"cat /boot/config/plugins/dynamix.vm.manager/templates/{vm_name}.xml 2>/dev/null || echo 'No template'")
            if "No template" not in vm_template:
                vm_details[vm_name]["template"] = vm_template

            # Get VM info if running
            if "running" in vm.get("state", "").lower():
                info_raw = await self.run_command(f"virsh dominfo {vm_name}")
                vm_details[vm_name]["info"] = info_raw

                # Get VM stats
                stats_raw = await self.run_command(f"virsh domstats {vm_name}")
                vm_details[vm_name]["stats"] = stats_raw

                # Get VM block device info (disks)
                blkdevs_raw = await self.run_command(f"virsh domblklist {vm_name}")
                vm_details[vm_name]["block_devices"] = blkdevs_raw

                # Get VM network interfaces
                net_raw = await self.run_command(f"virsh domiflist {vm_name}")
                vm_details[vm_name]["network_interfaces"] = net_raw

                # Get VM memory info
                mem_raw = await self.run_command(f"virsh dommemstat {vm_name} 2>/dev/null || echo 'Memory stats not available'")
                vm_details[vm_name]["memory_stats"] = mem_raw

                # Get VM CPU info
                cpu_raw = await self.run_command(f"virsh vcpuinfo {vm_name}")
                vm_details[vm_name]["cpu_info"] = cpu_raw

            # Get VM disk paths and sizes (Unraid specific)
            vm_disks = await self.run_command(f"find /mnt/user/domains -name '{vm_name}*' -type f 2>/dev/null | xargs ls -lah 2>/dev/null || echo 'No disks found'")
            vm_details[vm_name]["disk_files"] = vm_disks

        result["vm_details"] = vm_details

        # Check for GPU passthrough configuration (Unraid specific)
        gpu_passthrough = await self.run_command("grep -i 'pcie_acs_override\\|vfio\\|iommu' /boot/config/syslinux/syslinux.cfg 2>/dev/null || echo 'No GPU passthrough'")
        result["gpu_passthrough_config"] = gpu_passthrough

        # Check for VM USB passthrough devices
        usb_devices = await self.run_command("lsusb")
        result["usb_devices"] = usb_devices

        return result

    async def collect_ups_info(self) -> Dict[str, Any]:
        """Collect UPS information."""
        _LOGGER.info("Collecting UPS information")

        result = {}

        # Check if UPS services are running using Unraid-specific methods
        try:
            # First check for APC UPS (apcupsd) which is commonly used in Unraid
            apc_status = await self.run_command("which apcaccess >/dev/null 2>&1 && echo 'available' || echo 'not available'")
            result["apcupsd_available"] = apc_status.strip() == "available"

            # Check if apcupsd service is running
            if result["apcupsd_available"]:
                apcupsd_running = await self.run_command("ps aux | grep -v grep | grep -c 'apcupsd'")
                apcupsd_running_count = int(apcupsd_running.strip()) if apcupsd_running.strip().isdigit() else 0
                result["apcupsd_running"] = apcupsd_running_count > 0
                _LOGGER.info(f"APC UPS service running: {result['apcupsd_running']}")

                # Check if apcupsd service is active using systemctl
                apcupsd_service = await self.run_command("systemctl is-active apcupsd 2>/dev/null || echo 'inactive'")
                result["apcupsd_service_active"] = apcupsd_service.strip() == "active"

                # Get APC UPS data
                if result["apcupsd_running"] or result["apcupsd_service_active"]:
                    # Use timeout to prevent hanging if UPS is not responding
                    apc_output = await self.run_command("timeout 5 apcaccess 2>/dev/null || echo 'No APC UPS data'")

                    if "No APC UPS data" not in apc_output:
                        result["apc_ups_data_raw"] = apc_output

                        # Parse APC UPS data into structured format
                        apc_data = {}
                        for line in apc_output.splitlines():
                            if ":" in line:
                                parts = line.split(":", 1)
                                key = parts[0].strip()
                                value = parts[1].strip()
                                apc_data[key] = value

                        result["apc_ups_data"] = apc_data

                        # Extract key metrics
                        ups_metrics = {}

                        # Battery charge percentage
                        if "BCHARGE" in apc_data:
                            try:
                                charge_str = apc_data["BCHARGE"].split()[0]
                                charge = float(charge_str)
                                ups_metrics["battery_charge"] = charge
                            except (ValueError, IndexError):
                                pass

                        # Load percentage
                        if "LOADPCT" in apc_data:
                            try:
                                load_str = apc_data["LOADPCT"].split()[0]
                                load = float(load_str)
                                ups_metrics["load_percent"] = load
                            except (ValueError, IndexError):
                                pass

                        # Time left on battery
                        if "TIMELEFT" in apc_data:
                            try:
                                time_str = apc_data["TIMELEFT"].split()[0]
                                time_left = float(time_str)
                                ups_metrics["runtime_left"] = time_left
                            except (ValueError, IndexError):
                                pass

                        # Line voltage
                        if "LINEV" in apc_data:
                            try:
                                voltage_str = apc_data["LINEV"].split()[0]
                                voltage = float(voltage_str)
                                ups_metrics["line_voltage"] = voltage
                            except (ValueError, IndexError):
                                pass

                        # Battery voltage
                        if "BATTV" in apc_data:
                            try:
                                batt_str = apc_data["BATTV"].split()[0]
                                batt_voltage = float(batt_str)
                                ups_metrics["battery_voltage"] = batt_voltage
                            except (ValueError, IndexError):
                                pass

                        # Nominal power
                        if "NOMPOWER" in apc_data:
                            try:
                                power_str = apc_data["NOMPOWER"].split()[0]
                                power = float(power_str)
                                ups_metrics["nominal_power"] = power
                            except (ValueError, IndexError):
                                pass

                        # UPS status
                        if "STATUS" in apc_data:
                            ups_metrics["status"] = apc_data["STATUS"]

                        # UPS model
                        if "MODEL" in apc_data:
                            ups_metrics["model"] = apc_data["MODEL"]

                        # UPS name/identifier
                        if "UPSNAME" in apc_data:
                            ups_metrics["name"] = apc_data["UPSNAME"]

                        # Last transfer reason
                        if "LASTXFER" in apc_data:
                            ups_metrics["last_transfer_reason"] = apc_data["LASTXFER"]

                        # Add metrics to result
                        result["ups_metrics"] = ups_metrics

                        # Set UPS as running if we have valid data
                        result["ups_running"] = True
                        result["ups_type"] = "apcupsd"
                        result["ups_count"] = 1

            # Also check for NUT UPS (as a fallback)
            if not result.get("ups_running", False):
                # Check for UPS processes directly
                ups_pgrep = await self.run_command("ps aux | grep -v grep | grep -c 'upsd\\|upsmon'")
                ups_pids = int(ups_pgrep.strip()) if ups_pgrep.strip().isdigit() else 0
                _LOGGER.info(f"NUT UPS processes running: {ups_pids}")

                # Try to execute upsc command
                upsc_available = await self.run_command("which upsc >/dev/null 2>&1 && echo 'available' || echo 'not available'")
                result["upsc_available"] = upsc_available.strip() == "available"

                if result["upsc_available"]:
                    upsc_test = await self.run_command("upsc -l 2>/dev/null | wc -l || echo '0'")
                    upsc_devices = int(upsc_test.strip()) if upsc_test.strip().isdigit() else 0
                    _LOGGER.info(f"NUT UPS devices detected: {upsc_devices}")

                    if upsc_devices > 0:
                        result["ups_running"] = True
                        result["ups_type"] = "nut"
                        result["ups_count"] = upsc_devices
                else:
                    upsc_devices = 0
                    _LOGGER.info("upsc command not available")

            # Check for Unraid's UPS configuration files
            ups_config = await self.run_command("cat /boot/config/ups.cfg 2>/dev/null || echo 'No UPS config'")
            if "No UPS config" not in ups_config:
                result["ups_config"] = ups_config

            # Check for NUT config specific to Unraid
            nut_config = await self.run_command("cat /etc/ups/ups.conf 2>/dev/null || echo 'No NUT config'")
            if "No NUT config" not in nut_config:
                result["nut_config"] = nut_config

            # Check for Unraid's UPS settings in emhttp
            ups_settings = await self.run_command("cat /var/local/emhttp/ups.ini 2>/dev/null || echo 'No UPS settings'")
            if "No UPS settings" not in ups_settings:
                result["ups_emhttp_settings"] = ups_settings

        except Exception as e:
            _LOGGER.error(f"Error checking UPS status: {e}")
            result["ups_running"] = False
            result["ups_error"] = str(e)

        if not result.get("ups_running", False):
            _LOGGER.info("No UPS service detected")
            result["ups_count"] = 0
            return result

        # If we're using NUT, get more detailed information
        try:
            if result.get("ups_type") == "nut" and result.get("upsc_available", False):
                ups_list_raw = await self.run_command("upsc -l 2>/dev/null || echo ''")
                ups_list = [ups.strip() for ups in ups_list_raw.splitlines() if ups.strip()]
                result["ups_list"] = ups_list

                # Get details for each UPS
                ups_details = {}
                for ups in ups_list:
                    _LOGGER.info(f"Getting details for UPS {ups}")

                    ups_data_raw = await self.run_command(f"upsc {ups} 2>/dev/null || echo 'No UPS data'")
                    ups_data = {}

                    for line in ups_data_raw.splitlines():
                        if ": " in line:
                            key, value = line.split(": ", 1)
                            ups_data[key] = value

                    ups_details[ups] = ups_data

                result["ups_details"] = ups_details

            # Check for Unraid UPS shutdown settings
            shutdown_settings = await self.run_command("cat /boot/config/plugins/dynamix/dynamix.cfg 2>/dev/null | grep -i 'ups'")
            if shutdown_settings.strip():
                result["ups_shutdown_settings"] = shutdown_settings

            # Get UPS logs
            ups_logs = await self.run_command("grep -i 'ups\\|battery\\|apc' /var/log/syslog 2>/dev/null | tail -n 100")
            if ups_logs.strip():
                result["ups_recent_logs"] = ups_logs

        except Exception as e:
            _LOGGER.error(f"Error collecting detailed UPS information: {e}")
            result["ups_detail_error"] = str(e)

        return result

    async def collect_parity_status(self) -> Dict[str, Any]:
        """Collect parity check status information."""
        _LOGGER.info("Collecting parity check status")

        result = {}

        # Check if a parity check is in progress
        parity_check_raw = await self.run_command("cat /proc/mdstat")
        result["mdstat_raw"] = parity_check_raw

        # Check parity history
        parity_history_raw = await self.run_command("cat /boot/config/parity-checks.log 2>/dev/null || echo 'No parity history'")
        result["parity_history_raw"] = parity_history_raw

        # Get parity check status from Unraid
        parity_status_raw = await self.run_command("cat /var/local/emhttp/var.ini 2>/dev/null | grep -E 'mdResync|mdResyncPos|mdResyncSize|mdResyncDt'")

        # Parse status
        result["parity_check_active"] = "resync" in parity_check_raw.lower() or "recovery" in parity_check_raw.lower()

        # Parse detailed status information
        parity_details = {}
        for line in parity_status_raw.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                parity_details[key.strip()] = value.strip()

        # Calculate progress percentage if possible
        if "mdResyncPos" in parity_details and "mdResyncSize" in parity_details:
            try:
                current = float(parity_details.get("mdResyncPos", "0"))
                total = float(parity_details.get("mdResyncSize", "1"))
                if total > 0:
                    parity_details["progress_percent"] = round((current / total) * 100, 2)
            except (ValueError, ZeroDivisionError):
                pass

        # Get estimated time remaining
        if "mdResyncDt" in parity_details and "mdResyncPos" in parity_details and "mdResyncSize" in parity_details:
            try:
                dt = float(parity_details.get("mdResyncDt", "0"))
                pos = float(parity_details.get("mdResyncPos", "0"))
                size = float(parity_details.get("mdResyncSize", "1"))

                if dt > 0 and pos > 0:
                    remaining_seconds = dt * (size - pos) / pos
                    parity_details["estimated_remaining_seconds"] = int(remaining_seconds)
                    parity_details["estimated_completion"] = str(datetime.timedelta(seconds=int(remaining_seconds)))
            except (ValueError, ZeroDivisionError):
                pass

        result["parity_details"] = parity_details

        # Get scheduled parity check configuration
        schedule_raw = await self.run_command("cat /boot/config/plugins/dynamix/dynamix.cfg 2>/dev/null | grep -E 'parity.schedule|parity.frequency'")
        schedule_data = {}

        for line in schedule_raw.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                schedule_data[key.strip()] = value.strip().strip('"')

        result["parity_schedule"] = schedule_data

        return result

    async def collect_plugin_info(self) -> Dict[str, Any]:
        """Collect information about installed plugins."""
        _LOGGER.info("Collecting plugin information")

        result = {}

        # Get list of installed plugins
        plugins_raw = await self.run_command("ls -la /boot/config/plugins/ | grep -E '\.plg$'")
        plugin_files = [line.split()[-1] for line in plugins_raw.splitlines() if line.endswith('.plg')]

        # Get details of each plugin
        plugin_details = {}
        for plugin_file in plugin_files:
            if not plugin_file:
                continue

            plugin_name = plugin_file.replace('.plg', '')
            plugin_data = {}

            # Get plugin version and description if available
            plugin_content = await self.run_command(f"cat /boot/config/plugins/{plugin_file} 2>/dev/null | grep -E 'NAME|VERSION|DESCRIPTION' | head -n 10")

            for line in plugin_content.splitlines():
                if "=" in line:
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        key = parts[0].strip().replace("<!ENTITY", "").strip()
                        value = parts[1].strip().replace('"', '').replace(">", "").strip()
                        plugin_data[key.lower()] = value

            # Check if plugin is enabled
            plugin_enabled_raw = await self.run_command(f"ls -la /var/log/plugins/{plugin_name}.plg 2>/dev/null || echo 'Not installed'")
            plugin_data["enabled"] = "Not installed" not in plugin_enabled_raw

            plugin_details[plugin_name] = plugin_data

        result["plugins"] = plugin_details
        result["plugin_count"] = len(plugin_details)

        return result

    async def collect_share_info(self) -> Dict[str, Any]:
        """Collect information about network shares."""
        _LOGGER.info("Collecting share information")

        result = {}

        # Get list of shares from Unraid configuration
        shares_raw = await self.run_command("cat /boot/config/shares/*.cfg 2>/dev/null || echo 'No shares found'")
        result["shares_raw"] = shares_raw

        # Get list of share directories
        share_dirs_raw = await self.run_command("ls -la /mnt/user/ | grep -v '\.$'")

        # Parse share directories
        shares = []
        for line in share_dirs_raw.splitlines():
            parts = line.split()
            if len(parts) >= 9 and "d" in parts[0][0]:  # Check if it's a directory
                share_name = parts[-1]
                if share_name in [".", ".."]:
                    continue

                # Skip the du command as it can timeout on large shares
                # Instead get basic info that's faster
                share_info = {
                    "name": share_name,
                    "path": f"/mnt/user/{share_name}",
                }

                # Get share settings
                share_cfg_raw = await self.run_command(f"cat /boot/config/shares/{share_name}.cfg 2>/dev/null || echo 'No config'")
                share_info["raw_config"] = share_cfg_raw

                # Parse share config
                share_config = {}
                for line in share_cfg_raw.splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        share_config[key.strip()] = value.strip().strip('"')

                share_info["config"] = share_config

                # Check if share is exported via SMB/NFS
                smb_status_raw = await self.run_command(f"cat /etc/samba/smb.conf 2>/dev/null | grep -A 10 '\\[{share_name}\\]' || echo 'Not shared'")
                share_info["smb_shared"] = "Not shared" not in smb_status_raw

                nfs_status_raw = await self.run_command("cat /etc/exports 2>/dev/null | grep -E '/mnt/user/.*'")
                share_info["nfs_shared"] = f"/mnt/user/{share_name}" in nfs_status_raw

                # Get number of files instead of size (much faster)
                try:
                    # Just count top-level items as a quick indicator
                    file_count_raw = await self.run_command(f"ls -1 /mnt/user/{share_name} 2>/dev/null | wc -l")
                    share_info["file_count"] = int(file_count_raw.strip())
                except (ValueError, asyncssh.Error):
                    share_info["file_count"] = 0

                shares.append(share_info)

        result["shares"] = shares
        result["share_count"] = len(shares)

        return result

    async def collect_user_info(self) -> Dict[str, Any]:
        """Collect information about user accounts and permissions."""
        _LOGGER.info("Collecting user account information")

        result = {}

        # Get user list (only real users, filter out system users)
        users_raw = await self.run_command("cat /etc/passwd | grep -E '/home/|/root:' | sort")

        # Parse user info
        users = []
        for line in users_raw.splitlines():
            if not line.strip():
                continue

            parts = line.split(":")
            if len(parts) >= 7:
                username = parts[0]
                uid = parts[2]
                home = parts[5]
                shell = parts[6]

                # Get groups for this user
                groups_raw = await self.run_command(f"groups {username} 2>/dev/null || echo 'No groups'")
                groups = groups_raw.replace(f"{username} : ", "").split() if "No groups" not in groups_raw else []

                user_info = {
                    "username": username,
                    "uid": uid,
                    "home": home,
                    "shell": shell,
                    "groups": groups
                }

                # Check if user is admin (member of wheel or admin group)
                user_info["is_admin"] = "wheel" in groups or "admin" in groups

                users.append(user_info)

        result["users"] = users
        result["user_count"] = len(users)

        return result

    async def collect_notifications(self) -> Dict[str, Any]:
        """Collect system notifications and alerts."""
        _LOGGER.info("Collecting system notifications and alerts")

        result = {}

        # Get system logs
        syslog_raw = await self.run_command("cat /var/log/syslog 2>/dev/null | tail -n 500 || echo 'No syslog available'")
        result["recent_syslog"] = syslog_raw

        # Get notifications from Unraid UI
        notifications_raw = await self.run_command("cat /var/local/emhttp/notice.json 2>/dev/null || echo '{}'")
        try:
            result["notifications"] = json.loads(notifications_raw)
        except json.JSONDecodeError:
            result["notifications_raw"] = notifications_raw

        # Get alerts history from logs
        alerts_raw = await self.run_command("grep -i 'alert' /var/log/syslog 2>/dev/null | tail -n 100")
        alerts = [line for line in alerts_raw.splitlines() if line.strip()]
        result["recent_alerts"] = alerts

        # Get SMART errors from logs
        smart_errors_raw = await self.run_command("grep -i 'smart' /var/log/syslog 2>/dev/null | grep -i 'error' | tail -n 100")
        smart_errors = [line for line in smart_errors_raw.splitlines() if line.strip()]
        result["recent_smart_errors"] = smart_errors

        # Get array status changes from logs
        array_changes_raw = await self.run_command("grep -i 'array' /var/log/syslog 2>/dev/null | grep -iE 'start|stop|mount|unmount' | tail -n 100")
        array_changes = [line for line in array_changes_raw.splitlines() if line.strip()]
        result["recent_array_changes"] = array_changes

        return result

    async def collect_array_status(self) -> Dict[str, Any]:
        """Collect array operation status and modes."""
        _LOGGER.info("Collecting array status information")

        result = {}

        # Get array status from Unraid-specific files
        array_status_raw = await self.run_command("cat /proc/mdstat")
        result["mdstat_raw"] = array_status_raw

        # Get Unraid's emhttp array status (more detailed than mdstat)
        emhttp_status_raw = await self.run_command("cat /var/local/emhttp/var.ini 2>/dev/null || echo 'No emhttp status'")
        result["emhttp_status_raw"] = emhttp_status_raw

        # Get array configuration
        array_cfg_raw = await self.run_command("cat /boot/config/disk.cfg 2>/dev/null || echo 'No disk config'")
        result["array_config_raw"] = array_cfg_raw

        # Get Unraid super.dat status (contains filesystem metadata)
        superdat_raw = await self.run_command("cat /config/super.dat 2>/dev/null || echo 'No super.dat data'")
        result["superdat_raw"] = superdat_raw

        # Check current Unraid operations (array operations, mover, etc.)
        current_ops_raw = await self.run_command("ps aux | grep -E 'mdcmd|mover|btrfs|mergerfs' | grep -v grep")
        result["current_operations_raw"] = current_ops_raw

        # Check if mover is active
        mover_active = "mover" in current_ops_raw.lower()
        result["mover_active"] = mover_active

        # Check if array is being started/stopped
        array_transitioning = "mdcmd" in current_ops_raw.lower() and ("start" in current_ops_raw.lower() or "stop" in current_ops_raw.lower())
        result["array_transitioning"] = array_transitioning

        # Check array operation mode
        array_mode_raw = await self.run_command("cat /var/local/emhttp/var.ini 2>/dev/null | grep -E '^mdState|^mdNumDisks|^mdNumProtected'")

        # Parse array state
        mode_details = {}
        for line in array_mode_raw.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                mode_details[key.strip()] = value.strip()

        result["array_mode"] = mode_details

        # Determine mode status
        if "mdState" in mode_details:
            state = mode_details["mdState"]
            result["array_started"] = state.lower() in ["started", "active"]
            result["array_stopping"] = state.lower() == "stopping"
            result["array_starting"] = state.lower() == "starting"
            result["array_maintenance_mode"] = state.lower() == "maintenance"

        # Get disk assignments and status from Unraid's disks.ini
        disk_assignments_raw = await self.run_command("cat /var/local/emhttp/disks.ini 2>/dev/null || echo 'No disk assignments'")
        result["disk_assignments_raw"] = disk_assignments_raw

        # Get information about cache pools (if any)
        cache_pools_raw = await self.run_command("ls -la /mnt/cache* 2>/dev/null || echo 'No cache pools'")
        result["cache_pools_raw"] = cache_pools_raw

        # Check if using cache pools and get their status
        if "No cache pools" not in cache_pools_raw:
            cache_status = {}
            cache_dirs = [line.split()[-1] for line in cache_pools_raw.splitlines() if line.startswith('d')]
            for cache_dir in cache_dirs:
                if not cache_dir or cache_dir in [".", ".."]:
                    continue
                cache_name = os.path.basename(cache_dir)
                # Get btrfs pool info for cache
                btrfs_info = await self.run_command(f"btrfs filesystem usage {cache_dir} 2>/dev/null || echo 'Not btrfs'")
                cache_status[cache_name] = btrfs_info
            result["cache_pool_status"] = cache_status

        # Parse disk assignments
        disk_assignments = {}
        current_disk = None

        for line in disk_assignments_raw.splitlines():
            if line.startswith('[') and line.endswith(']'):
                current_disk = line[1:-1]
                disk_assignments[current_disk] = {}
            elif current_disk and "=" in line:
                key, value = line.split("=", 1)
                disk_assignments[current_disk][key.strip()] = value.strip()

        result["disk_assignments"] = disk_assignments

        # Get Unraid-specific flash device info
        flash_info = await self.run_command("ls -la /boot 2>/dev/null")
        result["flash_device_info"] = flash_info

        return result

    async def collect_all(self) -> Dict[str, Any]:
        """Collect all data from the Unraid server."""
        try:
            await self.connect()

            _LOGGER.info("Starting data collection")
            start_time = time.time()

            # Collect data from all subsystems
            system_stats = await self.collect_system_stats()
            disk_info = await self.collect_disk_info()
            network_info = await self.collect_network_info()
            docker_info = await self.collect_docker_info()
            vm_info = await self.collect_vm_info()
            ups_info = await self.collect_ups_info()
            parity_status = await self.collect_parity_status()
            plugin_info = await self.collect_plugin_info()
            share_info = await self.collect_share_info()
            user_info = await self.collect_user_info()
            notifications = await self.collect_notifications()
            array_status = await self.collect_array_status()

            # Add new data collection
            emhttp_configs = await self.collect_emhttp_configs()
            gpu_info = await self.collect_gpu_info()
            zfs_info = await self.collect_zfs_info()

            # Aggregate all data
            self.data = {
                "collection_time": datetime.now().isoformat(),
                "host": self.host,
                "system_stats": system_stats,
                "disk_info": disk_info,
                "network_info": network_info,
                "docker_info": docker_info,
                "vm_info": vm_info,
                "ups_info": ups_info,
                "parity_status": parity_status,
                "plugin_info": plugin_info,
                "share_info": share_info,
                "user_info": user_info,
                "notifications": notifications,
                "array_status": array_status,
                "emhttp_configs": emhttp_configs,
                "gpu_info": gpu_info,
                "zfs_info": zfs_info,
            }

            elapsed_time = time.time() - start_time
            _LOGGER.info(f"Data collection completed in {elapsed_time:.2f} seconds")

            return self.data

        finally:
            await self.disconnect()

    def save_to_file(self, filename: str = None) -> str:
        """Save the collected data to a JSON file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"unraid_data_{self.host}_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(self.data, f, indent=2)

        _LOGGER.info(f"Data saved to {filename}")
        return filename


async def run_collector():
    """Run the collector."""
    # Initialize rich console
    console = Console()

    # Get connection parameters from environment or use defaults
    host = os.environ.get("UNRAID_HOST", "192.168.20.21")
    username = os.environ.get("UNRAID_USER", "root")
    password = os.environ.get("UNRAID_PASSWORD", "tasvyh-4Gehju-ridxic")
    port = int(os.environ.get("UNRAID_PORT", "22"))

    # Display welcome banner with more attractive formatting
    layout = Layout()
    layout.split_column(
        Layout(name="header"),
        Layout(name="body")
    )

    # Create a styled header
    header_text = Text()
    header_text.append("✨ ", style="bold yellow")
    header_text.append("UNRAID DATA COLLECTOR", style="bold white on blue")
    header_text.append(" ✨\n", style="bold yellow")

    # Version info with better styling
    version_text = Text()
    version_text.append("Version: ", style="dim")
    version_text.append("1.0.0", style="bold green")

    # Create an attractive panel for the banner
    banner = Panel.fit(
        f"[bold green]UNRAID SERVER DATA COLLECTOR[/bold green]\n\n"
        f"[yellow]Host:[/yellow] [white on blue]{host}[/white on blue]:[cyan]{port}[/cyan]\n"
        f"[yellow]User:[/yellow] [cyan]{username}[/cyan]\n\n"
        f"[dim italic]This tool will securely connect to your Unraid server\n"
        f"and collect system information for analysis.[/dim italic]",
        border_style="green",
        title="[white on green] 🖥️  UNRAID COLLECTOR [/white on green]",
        subtitle=f"[dim]v1.0.0 • {datetime.now().strftime('%Y-%m-%d')}[/dim]"
    )

    console.print(banner)
    console.print()

    collector = UnraidCollector(host, username, password, port)

    try:
        # Show progress while collecting data with enhanced styling
        with Progress(
            SpinnerColumn(style="green"),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40, complete_style="green", finished_style="bold green"),
            TaskProgressColumn(),
            TextColumn("[bold green]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            expand=True
        ) as progress:
            # Create a main task for overall progress
            main_task = progress.add_task("[bold yellow]📊 Collecting Unraid data...", total=16)

            # Connect
            progress.update(main_task, description="[bold blue]🔌 Connecting to Unraid server...")
            await collector.connect()
            progress.update(main_task, advance=1)

            # System stats
            progress.update(main_task, description="[bold blue]🖥️  Collecting system statistics...")
            collector.data["system_stats"] = await collector.collect_system_stats()
            progress.update(main_task, advance=1)

            # Disk info
            progress.update(main_task, description="[bold blue]💾 Collecting disk information...")
            collector.data["disk_info"] = await collector.collect_disk_info()
            progress.update(main_task, advance=1)

            # Network info
            progress.update(main_task, description="[bold blue]🌐 Collecting network information...")
            collector.data["network_info"] = await collector.collect_network_info()
            progress.update(main_task, advance=1)

            # Docker info
            progress.update(main_task, description="[bold blue]🐳 Collecting Docker container information...")
            collector.data["docker_info"] = await collector.collect_docker_info()
            progress.update(main_task, advance=1)

            # VM info
            progress.update(main_task, description="[bold blue]🖥️  Collecting VM information...")
            collector.data["vm_info"] = await collector.collect_vm_info()
            progress.update(main_task, advance=1)

            # UPS info
            progress.update(main_task, description="[bold blue]🔋 Collecting UPS information...")
            collector.data["ups_info"] = await collector.collect_ups_info()
            progress.update(main_task, advance=1)

            # Parity status
            progress.update(main_task, description="[bold blue]🔄 Collecting parity check information...")
            collector.data["parity_status"] = await collector.collect_parity_status()
            progress.update(main_task, advance=1)

            # Plugin info
            progress.update(main_task, description="[bold blue]🧩 Collecting plugin information...")
            collector.data["plugin_info"] = await collector.collect_plugin_info()
            progress.update(main_task, advance=1)

            # Share info
            progress.update(main_task, description="[bold blue]📂 Collecting share information...")
            collector.data["share_info"] = await collector.collect_share_info()
            progress.update(main_task, advance=1)

            # User info
            progress.update(main_task, description="[bold blue]👤 Collecting user information...")
            collector.data["user_info"] = await collector.collect_user_info()
            progress.update(main_task, advance=1)

            # Notifications
            progress.update(main_task, description="[bold blue]🔔 Collecting system notifications...")
            collector.data["notifications"] = await collector.collect_notifications()
            progress.update(main_task, advance=1)

            # Array status
            progress.update(main_task, description="[bold blue]🔢 Collecting array status...")
            collector.data["array_status"] = await collector.collect_array_status()
            progress.update(main_task, advance=1)

            # Emhttp configs
            progress.update(main_task, description="[bold blue]📝 Collecting emhttp configs...")
            collector.data["emhttp_configs"] = await collector.collect_emhttp_configs()
            progress.update(main_task, advance=1)

            # GPU info
            progress.update(main_task, description="[bold blue]🎮 Collecting GPU information...")
            collector.data["gpu_info"] = await collector.collect_gpu_info()
            progress.update(main_task, advance=1)

            # ZFS info
            progress.update(main_task, description="[bold blue]💾 Collecting ZFS information...")
            collector.data["zfs_info"] = await collector.collect_zfs_info()
            progress.update(main_task, advance=1)

            # Set meta info
            collector.data["collection_time"] = datetime.now().isoformat()
            collector.data["host"] = collector.host

            # Complete main task
            progress.update(main_task, description="[bold green]✅ Collection complete!")

        # Save the data
        console.print("[bold green]💾 Saving collected data...[/bold green]")
        filename = collector.save_to_file()

        # Create a summary table with enhanced styling
        table = Table(
            title="[bold white on blue] Collection Summary [/bold white on blue]",
            show_header=True,
            header_style="bold magenta",
            border_style="blue",
            box=box.ROUNDED
        )

        table.add_column("Component", style="cyan", width=20)
        table.add_column("Status", justify="center")
        table.add_column("Details", justify="right")

        # Add component rows with emojis
        table.add_row(
            "🖥️  System",
            "[green]✅[/green]",
            f"{collector.data['system_stats'].get('cpu_cores', '?')} cores, {collector.data['system_stats'].get('unraid_version', '?')}"
        )

        disk_count = len(collector.data['disk_info'].get('smart_data', {}))
        table.add_row("💾 Disks", "[green]✅[/green]", f"{disk_count} disks detected")

        net_ifaces = len(collector.data['network_info'].get('interfaces', []))
        table.add_row("🌐 Network", "[green]✅[/green]", f"{net_ifaces} interfaces")

        docker_running = collector.data['docker_info'].get('docker_running', False)
        docker_status = "[green]✅[/green]" if docker_running else "[yellow]⚠️ Not running[/yellow]"
        container_count = len(collector.data['docker_info'].get('containers', []))
        table.add_row("🐳 Docker", docker_status, f"{container_count} containers" if docker_running else "-")

        vm_running = collector.data['vm_info'].get('libvirt_running', False)
        vm_status = "[green]✅[/green]" if vm_running else "[yellow]⚠️ Not running[/yellow]"
        vm_count = len(collector.data['vm_info'].get('vms', []))
        table.add_row("🖥️  VMs", vm_status, f"{vm_count} VMs" if vm_running else "-")

        # UPS information with improved details
        ups_running = collector.data['ups_info'].get('ups_running', False)
        ups_status = "[green]✅[/green]" if ups_running else "[yellow]⚠️ Not detected[/yellow]"

        # Get UPS count and details
        ups_count = collector.data['ups_info'].get('ups_count', 0)
        ups_type = collector.data['ups_info'].get('ups_type', '')

        # Get battery charge if available
        ups_details = ""
        if ups_running:
            if ups_type == "apcupsd" and "ups_metrics" in collector.data['ups_info']:
                metrics = collector.data['ups_info']['ups_metrics']
                if "battery_charge" in metrics:
                    ups_details = f"{metrics['battery_charge']}% battery"
                elif "status" in metrics:
                    ups_details = f"Status: {metrics['status']}"
                elif "model" in metrics:
                    ups_details = f"Model: {metrics['model']}"
                else:
                    ups_details = f"APC UPS detected"
            else:
                ups_details = f"{ups_count} UPS device{'s' if ups_count != 1 else ''}"
        else:
            ups_details = "No UPS detected"

        table.add_row("🔋 UPS", ups_status, ups_details)

        # Add new components to summary table
        parity_active = collector.data['parity_status'].get('parity_check_active', False)
        parity_status_text = "[green]Active[/green]" if parity_active else "[blue]Inactive[/blue]"
        parity_progress = collector.data['parity_status'].get('parity_details', {}).get('progress_percent', 0)
        parity_details = f"{parity_progress}% complete" if parity_active else "No check running"
        table.add_row("🔄 Parity Check", parity_status_text, parity_details)

        plugin_count = collector.data['plugin_info'].get('plugin_count', 0)
        table.add_row("🧩 Plugins", "[green]✅[/green]", f"{plugin_count} plugins installed")

        share_count = collector.data['share_info'].get('share_count', 0)
        table.add_row("📂 Shares", "[green]✅[/green]", f"{share_count} shares configured")

        user_count = collector.data['user_info'].get('user_count', 0)
        table.add_row("👤 Users", "[green]✅[/green]", f"{user_count} users configured")

        alert_count = len(collector.data['notifications'].get('recent_alerts', []))
        table.add_row("🔔 Alerts", "[green]✅[/green]", f"{alert_count} recent alerts")

        array_started = collector.data['array_status'].get('array_started', False)
        array_state = "[green]Started[/green]" if array_started else "[yellow]Stopped[/yellow]"
        table.add_row("🔢 Array Status", array_state, collector.data['array_status'].get('array_mode', {}).get('mdState', 'Unknown'))

        # Print summary table
        console.print(table)

        # Print success message with more attractive formatting
        success_panel = Panel.fit(
            f"[bold green]✅ Data collection complete![/bold green]\n\n"
            f"[yellow]Results saved to:[/yellow] [white on blue]{filename}[/white on blue]\n\n"
            f"[dim italic]This file contains detailed information about your Unraid server\n"
            f"that can be used for analysis and troubleshooting.[/dim italic]",
            border_style="green",
            title="[white on green] SUCCESS [/white on green]",
            subtitle=f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
        )

        console.print(success_panel)

        return filename
    except Exception as e:
        # Enhanced error panel
        error_panel = Panel.fit(
            f"[bold red]❌ Error collecting data:[/bold red]\n\n"
            f"[white]{escape(str(e))}[/white]\n\n"
            f"[dim italic]Please check your connection parameters and try again.[/dim italic]",
            border_style="red",
            title="[white on red] ERROR [/white on red]",
            subtitle=f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
        )

        console.print(error_panel)
        _LOGGER.error(f"Collection failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Disconnect
        if collector.conn:
            await collector.disconnect()


if __name__ == "__main__":
    rich_console.print("[bold blue]🚀 Starting Unraid data collection...[/bold blue]")
    asyncio.run(run_collector())
