"""Data processor for Unraid integration."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger(__name__)


class DataProcessor:
    """Process data from Unraid server."""

    def __init__(self, client):
        """Initialize the data processor."""
        self.client = client

    def _parse_cpu_usage(self, output: str) -> float:
        """Parse CPU usage from /proc/stat output."""
        lines = output.strip().split("\n")
        for line in lines:
            if line.startswith("cpu "):
                parts = line.split()
                if len(parts) < 5:
                    continue

                # Extract CPU time values
                user = int(parts[1])
                nice = int(parts[2])
                system = int(parts[3])
                idle = int(parts[4])

                # Calculate CPU usage
                total = user + nice + system + idle
                if total == 0:
                    return 0.0

                return 100.0 * (1.0 - (idle / total))

        return 0.0

    def _parse_memory_info(self, output: str) -> Dict[str, int]:
        """Parse memory information from /proc/meminfo output."""
        result = {
            "total": 0,
            "free": 0,
            "available": 0,
            "used": 0,
            "cached": 0,
            "buffers": 0,
        }

        lines = output.strip().split("\n")
        for line in lines:
            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            key = key.strip()
            value_parts = value.strip().split()

            if len(value_parts) < 1:
                continue

            try:
                value_kb = int(value_parts[0])

                if key == "MemTotal":
                    result["total"] = value_kb
                elif key == "MemFree":
                    result["free"] = value_kb
                elif key == "MemAvailable":
                    result["available"] = value_kb
                elif key == "Cached":
                    result["cached"] = value_kb
                elif key == "Buffers":
                    result["buffers"] = value_kb
            except ValueError:
                pass

        # Calculate used memory
        result["used"] = result["total"] - result["free"]

        return result

    def _parse_disk_info(self, output: str) -> Dict[str, Dict[str, str]]:
        """Parse disk information from df -h output."""
        result = {}

        lines = output.strip().split("\n")
        if len(lines) < 2:
            return result

        # Skip header
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue

            device = parts[0]
            result[device] = {
                "size": parts[1],
                "used": parts[2],
                "avail": parts[3],
                "use_percentage": parts[4],
                "mounted_on": parts[5],
            }

        return result

    def _extract_temperature(self, line: str) -> Optional[float]:
        """Extract temperature value from a line of output."""
        # Match patterns like "+45.0°C" or "45.0°C" or "45.0 C"
        temp_match = re.search(r"[+]?(\d+\.\d+|\d+)°?C", line)
        if temp_match:
            try:
                return float(temp_match.group(1))
            except ValueError:
                pass
        return None

    def _parse_docker_containers(self, output: str) -> List[Dict[str, str]]:
        """Parse Docker container information from docker ps output."""


        result = []

        lines = output.strip().split("\n")
        if len(lines) < 2:
            return result

        # Get header line and determine column positions
        header = lines[0]
        container_id_pos = header.find("CONTAINER ID")
        image_pos = header.find("IMAGE")
        command_pos = header.find("COMMAND")
        created_pos = header.find("CREATED")
        status_pos = header.find("STATUS")
        ports_pos = header.find("PORTS")
        names_pos = header.find("NAMES")

        # Parse each container line
        for line in lines[1:]:
            if not line.strip():
                continue

            container = {
                "container_id": line[container_id_pos:image_pos].strip(),
                "image": line[image_pos:command_pos].strip(),
                "command": line[command_pos:created_pos].strip(),
                "created": line[created_pos:status_pos].strip(),
                "status": line[status_pos:ports_pos].strip(),
                "name": line[names_pos:].strip()
            }

            # Add ports if available
            if ports_pos >= 0 and names_pos > ports_pos:
                container["ports"] = line[ports_pos:names_pos].strip()

            result.append(container)

        return result

    def _parse_vm_info(self, output: str) -> List[Dict[str, str]]:
        """Parse VM information from virsh list output."""
        result = []

        lines = output.strip().split("\n")
        if len(lines) < 3:  # Header, separator, and at least one VM
            return result

        # Skip header and separator
        for line in lines[2:]:
            if not line.strip():
                continue

            # Split by whitespace and filter out empty strings
            parts = [part for part in line.split() if part]
            if len(parts) < 3:
                continue

            vm = {
                "id": parts[0],
                "name": parts[1],
                "state": " ".join(parts[2:])
            }

            result.append(vm)

        return result

    def _parse_ups_info(self, output: str) -> Dict[str, str]:
        """Parse UPS information from upsc output."""
        result = {}

        for line in output.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                result[key] = value

        return result

    def _parse_gpu_info(self, output: str) -> List[Dict[str, str]]:
        """Parse GPU information from nvidia-smi output."""
        result = []

        lines = output.strip().split("\n")
        if len(lines) < 2:  # Header and at least one GPU
            return result

        # Get header line
        header = lines[0]
        headers = [h.strip() for h in header.split(",")]

        # Parse each GPU line
        for line in lines[1:]:
            if not line.strip():
                continue

            values = [v.strip() for v in line.split(",")]
            if len(values) != len(headers):
                continue

            gpu = {}
            for i, header in enumerate(headers):
                gpu[header] = values[i]

            result.append(gpu)

        return result

    def _parse_zfs_pools(self, output: str) -> List[Dict[str, str]]:
        """Parse ZFS pool information from zpool list output."""
        result = []

        lines = output.strip().split("\n")
        if len(lines) < 2:  # Header and at least one pool
            return result

        # Get header line
        header = lines[0]
        headers = [h.strip().lower() for h in header.split()]

        # Parse each pool line
        for line in lines[1:]:
            if not line.strip():
                continue

            values = line.split()
            if len(values) < len(headers):
                continue

            pool = {}
            for i, header in enumerate(headers):
                pool[header] = values[i]

            result.append(pool)

        return result

    def _parse_zfs_status(self, output: str) -> Dict[str, Any]:
        """Parse ZFS pool status from zpool status output."""


        result = {
            "pool": "",
            "state": "",
            "scan": "",
            "devices": []
        }

        lines = output.strip().split("\n")
        if not lines:
            return result

        # Extract pool name and state
        for line in lines:
            if line.startswith("pool:"):
                result["pool"] = line.split(":", 1)[1].strip()
            elif line.startswith("state:"):
                result["state"] = line.split(":", 1)[1].strip()
            elif line.startswith("scan:"):
                result["scan"] = line.split(":", 1)[1].strip()

        # Find the devices section
        devices_start = -1
        for i, line in enumerate(lines):
            if "NAME" in line and "STATE" in line:
                devices_start = i + 1
                break

        if devices_start >= 0:
            # Parse devices
            for line in lines[devices_start:]:
                if not line.strip():
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                device = {
                    "name": parts[0].strip(),
                    "state": parts[1].strip()
                }

                result["devices"].append(device)

        return result
