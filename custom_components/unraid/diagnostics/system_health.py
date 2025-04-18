"""System health diagnostics for Unraid."""
from __future__ import annotations

from typing import Dict, Any
from datetime import datetime, timedelta, timezone

from ..coordinator import UnraidDataUpdateCoordinator
from ..helpers import format_bytes, get_cpu_info, get_memory_info

# _LOGGER = logging.getLogger(__name__)

class SystemHealthDiagnostics:
    """System health diagnostics for Unraid."""

    def __init__(self, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the system health diagnostics."""
        self.coordinator = coordinator
        self._last_check = datetime.now(timezone.utc) - timedelta(hours=1)
        self._health_data: Dict[str, Any] = {}
        self._thresholds = {
            "cpu_usage": 90,  # CPU usage threshold (%)
            "memory_usage": 90,  # Memory usage threshold (%)
            "disk_usage": 90,  # Disk usage threshold (%)
            "temperature": 80,  # Temperature threshold (°C)
            "uptime": 90,  # Uptime threshold (days)
            "load_average": 10,  # Load average threshold
        }

    async def check_system_health(self) -> Dict[str, Any]:
        """Check system health and return diagnostics data."""
        now = datetime.now(timezone.utc)

        # Only run a full check every 15 minutes
        if (now - self._last_check).total_seconds() < 900:
            return self._health_data

        self._last_check = now
        health_data = {
            "timestamp": now.isoformat(),
            "cpu": self._check_cpu_health(),
            "memory": self._check_memory_health(),
            "storage": self._check_storage_health(),
            "network": self._check_network_health(),
            "temperature": self._check_temperature_health(),
            "services": self._check_services_health(),
            "uptime": self._check_uptime(),
            "issues": [],
            "recommendations": [],
        }

        # Aggregate issues and recommendations
        for category in ["cpu", "memory", "storage", "network", "temperature", "services", "uptime"]:
            if category_data := health_data.get(category):
                if issues := category_data.get("issues"):
                    health_data["issues"].extend(issues)
                if recommendations := category_data.get("recommendations"):
                    health_data["recommendations"].extend(recommendations)

        # Store health data
        self._health_data = health_data
        return health_data

    def _check_cpu_health(self) -> Dict[str, Any]:
        """Check CPU health."""
        system_stats = self.coordinator.data.get("system_stats", {})
        cpu_info = get_cpu_info(system_stats)

        result = {
            "usage": cpu_info.get("usage", 0),
            "load_average": system_stats.get("load_average", [0, 0, 0]),
            "cores": cpu_info.get("cores", 0),
            "model": cpu_info.get("model", "Unknown"),
            "issues": [],
            "recommendations": [],
        }

        # Check CPU usage
        if result["usage"] > self._thresholds["cpu_usage"]:
            result["issues"].append(f"CPU usage is high: {result['usage']}%")
            result["recommendations"].append("Check for resource-intensive processes")

        # Check load average
        if result["load_average"] and result["load_average"][0] > self._thresholds["load_average"]:
            result["issues"].append(f"Load average is high: {result['load_average'][0]}")
            result["recommendations"].append("Check for system bottlenecks")

        return result

    def _check_memory_health(self) -> Dict[str, Any]:
        """Check memory health."""
        system_stats = self.coordinator.data.get("system_stats", {})
        memory_info = get_memory_info(system_stats)

        result = {
            "total": memory_info.get("total", 0),
            "used": memory_info.get("used", 0),
            "free": memory_info.get("free", 0),
            "percentage": memory_info.get("percentage", 0),
            "issues": [],
            "recommendations": [],
        }

        # Check memory usage
        if result["percentage"] > self._thresholds["memory_usage"]:
            result["issues"].append(f"Memory usage is high: {result['percentage']}%")
            result["recommendations"].append("Check for memory leaks or increase memory")

        # Check for low memory
        if result["free"] < 1024 * 1024 * 1024:  # Less than 1GB free
            result["issues"].append(f"Low free memory: {format_bytes(result['free'])}")
            result["recommendations"].append("Consider adding more RAM or reducing VM/Docker memory allocations")

        return result

    def _check_storage_health(self) -> Dict[str, Any]:
        """Check storage health."""
        system_stats = self.coordinator.data.get("system_stats", {})
        array_usage = system_stats.get("array_usage", {})
        individual_disks = system_stats.get("individual_disks", [])

        result = {
            "array": {
                "total": array_usage.get("total", 0),
                "used": array_usage.get("used", 0),
                "free": array_usage.get("free", 0),
                "percentage": array_usage.get("percentage", 0),
            },
            "disks": [],
            "issues": [],
            "recommendations": [],
        }

        # Check array usage
        if result["array"]["percentage"] > self._thresholds["disk_usage"]:
            result["issues"].append(f"Array usage is high: {result['array']['percentage']}%")
            result["recommendations"].append("Consider adding more storage or cleaning up unused files")

        # Check individual disks
        for disk in individual_disks:
            disk_data = {
                "name": disk.get("name", "unknown"),
                "total": disk.get("total", 0),
                "used": disk.get("used", 0),
                "free": disk.get("free", 0),
                "percentage": disk.get("percentage", 0),
                "filesystem": disk.get("filesystem", "unknown"),
                "mount_point": disk.get("mount_point", "unknown"),
            }

            # Check disk usage
            if disk_data["percentage"] > self._thresholds["disk_usage"]:
                result["issues"].append(f"Disk {disk_data['name']} usage is high: {disk_data['percentage']}%")
                result["recommendations"].append(f"Consider cleaning up {disk_data['name']} or moving data to another disk")

            result["disks"].append(disk_data)

        return result

    def _check_network_health(self) -> Dict[str, Any]:
        """Check network health."""
        system_stats = self.coordinator.data.get("system_stats", {})
        network_stats = system_stats.get("network_stats", {})

        result = {
            "interfaces": [],
            "issues": [],
            "recommendations": [],
        }

        # Check network interfaces
        for interface, stats in network_stats.items():
            interface_data = {
                "name": interface,
                "rx_bytes": stats.get("rx_bytes", 0),
                "tx_bytes": stats.get("tx_bytes", 0),
                "rx_rate": stats.get("rx_rate", 0),
                "tx_rate": stats.get("tx_rate", 0),
                "connected": stats.get("connected", False),
                "speed": stats.get("speed", "unknown"),
                "duplex": stats.get("duplex", "unknown"),
            }

            # Check connection status
            if not interface_data["connected"]:
                result["issues"].append(f"Network interface {interface} is disconnected")
                result["recommendations"].append(f"Check network cable for {interface}")

            # Check for half-duplex
            if interface_data["duplex"] == "half":
                result["issues"].append(f"Network interface {interface} is running in half-duplex mode")
                result["recommendations"].append(f"Check network switch settings for {interface}")

            result["interfaces"].append(interface_data)

        return result

    def _check_temperature_health(self) -> Dict[str, Any]:
        """Check temperature health."""
        system_stats = self.coordinator.data.get("system_stats", {})
        temperature_data = system_stats.get("temperature_data", {})
        sensors = temperature_data.get("sensors", {})

        result = {
            "cpu": None,
            "motherboard": None,
            "disks": [],
            "issues": [],
            "recommendations": [],
        }

        # Check CPU temperature
        for sensor, data in sensors.items():
            if "coretemp" in sensor.lower() or "cpu" in sensor.lower():
                for key, value in data.items():
                    if "core" in key.lower() and isinstance(value, (int, float)):
                        if result["cpu"] is None or value > result["cpu"]:
                            result["cpu"] = value

            if "motherboard" in sensor.lower() or "system" in sensor.lower():
                for key, value in data.items():
                    if "temp" in key.lower() and isinstance(value, (int, float)):
                        if result["motherboard"] is None or value > result["motherboard"]:
                            result["motherboard"] = value

        # Check disk temperatures
        for disk in system_stats.get("individual_disks", []):
            if temp := disk.get("temperature"):
                disk_data = {
                    "name": disk.get("name", "unknown"),
                    "temperature": temp,
                }
                result["disks"].append(disk_data)

                # Check for high temperature
                if temp > self._thresholds["temperature"]:
                    result["issues"].append(f"Disk {disk_data['name']} temperature is high: {temp}°C")
                    result["recommendations"].append(f"Check cooling for disk {disk_data['name']}")

        # Check CPU temperature
        if result["cpu"] and result["cpu"] > self._thresholds["temperature"]:
            result["issues"].append(f"CPU temperature is high: {result['cpu']}°C")
            result["recommendations"].append("Check CPU cooling and airflow")

        # Check motherboard temperature
        if result["motherboard"] and result["motherboard"] > self._thresholds["temperature"]:
            result["issues"].append(f"Motherboard temperature is high: {result['motherboard']}°C")
            result["recommendations"].append("Check case airflow and fan operation")

        return result

    def _check_services_health(self) -> Dict[str, Any]:
        """Check services health."""
        docker_containers = self.coordinator.data.get("docker_containers", [])
        vms = self.coordinator.data.get("vms", [])

        result = {
            "docker": {
                "running": sum(1 for c in docker_containers if c.get("status") == "running"),
                "total": len(docker_containers),
                "containers": [
                    {
                        "name": c.get("name", "unknown"),
                        "status": c.get("status", "unknown"),
                        "state": c.get("state", "unknown"),
                    }
                    for c in docker_containers
                ],
            },
            "vms": {
                "running": sum(1 for vm in vms if vm.get("status") == "running"),
                "total": len(vms),
                "vms": [
                    {
                        "name": vm.get("name", "unknown"),
                        "status": vm.get("status", "unknown"),
                    }
                    for vm in vms
                ],
            },
            "issues": [],
            "recommendations": [],
        }

        # Check for stopped containers that should be running
        for container in docker_containers:
            if container.get("status") != "running" and container.get("autostart", False):
                result["issues"].append(f"Docker container {container.get('name')} is not running but set to autostart")
                result["recommendations"].append(f"Check logs for {container.get('name')}")

        # Check for stopped VMs that should be running
        for vm in vms:
            if vm.get("status") != "running" and vm.get("autostart", False):
                result["issues"].append(f"VM {vm.get('name')} is not running but set to autostart")
                result["recommendations"].append(f"Check VM logs for {vm.get('name')}")

        return result

    def _check_uptime(self) -> Dict[str, Any]:
        """Check system uptime."""
        system_stats = self.coordinator.data.get("system_stats", {})
        uptime_seconds = system_stats.get("uptime", 0)

        # Convert to days
        uptime_days = uptime_seconds / 86400

        result = {
            "seconds": uptime_seconds,
            "days": uptime_days,
            "formatted": self._format_uptime(uptime_seconds),
            "issues": [],
            "recommendations": [],
        }

        # Check for excessive uptime
        if uptime_days > self._thresholds["uptime"]:
            result["issues"].append(f"System uptime is high: {result['formatted']}")
            result["recommendations"].append("Consider scheduling a reboot to apply updates")

        return result

    def _format_uptime(self, seconds: int) -> str:
        """Format uptime in a human-readable format."""
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        if days > 0:
            return f"{int(days)} days, {int(hours)} hours, {int(minutes)} minutes"
        elif hours > 0:
            return f"{int(hours)} hours, {int(minutes)} minutes"
        else:
            return f"{int(minutes)} minutes, {int(seconds)} seconds"
