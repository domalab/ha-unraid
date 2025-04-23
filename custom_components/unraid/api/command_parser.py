"""Command output parsing for Unraid integration."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Union

_LOGGER = logging.getLogger(__name__)


def parse_disk_info(output: str, output_type: str = "lsblk") -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse disk information from command output."""
    if output_type == "lsblk":
        return _parse_lsblk_output(output)
    elif output_type == "df":
        return _parse_df_output(output)
    elif output_type == "smart":
        return _parse_smart_output(output)
    else:
        _LOGGER.warning("Unknown output type: %s", output_type)
        return []


def _parse_lsblk_output(output: str) -> List[Dict[str, Any]]:
    """Parse lsblk command output."""
    lines = output.strip().split("\n")
    if not lines:
        return []

    # Get headers
    headers = lines[0].split()

    # Parse each line
    disks = []
    for line in lines[1:]:
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) < len(headers):
            continue

        disk = {}
        for i, header in enumerate(headers):
            header_lower = header.lower()
            if i < len(parts):
                disk[header_lower] = parts[i]

        disks.append(disk)

    return disks


def _parse_df_output(output: str) -> List[Dict[str, Any]]:
    """Parse df command output."""
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []

    # Skip header
    disks = []
    for line in lines[1:]:
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) < 6:
            continue

        disk = {
            "device": parts[0],
            "size": parts[1],
            "used": parts[2],
            "available": parts[3],
            "use_percent": parts[4],
            "mount_point": parts[5]
        }

        disks.append(disk)

    return disks


def _parse_smart_output(output: str) -> Dict[str, Any]:
    """Parse smartctl command output."""
    result = {
        "smart_attributes": {}
    }

    # Extract model
    model_match = re.search(r"Device Model:\s+(.+)", output)
    if model_match:
        result["model"] = model_match.group(1).strip()

    # Extract serial
    serial_match = re.search(r"Serial Number:\s+(.+)", output)
    if serial_match:
        result["serial"] = serial_match.group(1).strip()

    # Extract capacity
    capacity_match = re.search(r"User Capacity:\s+(.+)", output)
    if capacity_match:
        result["capacity"] = capacity_match.group(1).strip()

    # Extract health status
    health_match = re.search(r"SMART overall-health self-assessment test result:\s+(.+)", output)
    if health_match:
        result["health"] = health_match.group(1).strip()

    # Extract temperature
    temp_match = re.search(r"194 Temperature_Celsius.+?(\d+)$", output, re.MULTILINE)
    if temp_match:
        result["temperature"] = int(temp_match.group(1))

    # Extract power on hours
    hours_match = re.search(r"9 Power_On_Hours.+?(\d+)$", output, re.MULTILINE)
    if hours_match:
        result["power_on_hours"] = int(hours_match.group(1))

    # Extract SMART attributes
    for line in output.split("\n"):
        if re.match(r"^\s*\d+\s+\w+", line):
            parts = re.split(r"\s+", line.strip())
            if len(parts) >= 10:
                attr_name = parts[1]
                raw_value = parts[9]
                try:
                    result["smart_attributes"][attr_name] = int(raw_value)
                except ValueError:
                    result["smart_attributes"][attr_name] = raw_value



    return result


def parse_temperature_data(output: str) -> Dict[str, float]:
    """Parse temperature data from sensors command output."""
    result = {}

    try:
        # Try to parse as JSON
        data = json.loads(output)

        # Extract CPU temperature
        for adapter, adapter_data in data.items():
            if "coretemp" in adapter:
                for sensor, sensor_data in adapter_data.items():
                    if "Package id" in sensor:
                        if "temp1_input" in sensor_data:
                            result["cpu"] = sensor_data["temp1_input"]
                    elif "Core" in sensor:
                        core_num = sensor.split()[1]
                        if "temp2_input" in sensor_data:
                            result[f"core{core_num}"] = sensor_data["temp2_input"]
                        elif "temp3_input" in sensor_data:
                            result[f"core{core_num}"] = sensor_data["temp3_input"]
            elif "nvme" in adapter:
                for sensor, sensor_data in adapter_data.items():
                    if sensor == "Composite" and "temp1_input" in sensor_data:
                        result["nvme"] = sensor_data["temp1_input"]
    except json.JSONDecodeError:
        _LOGGER.warning("Failed to parse temperature data as JSON")

    return result


def parse_docker_containers(output: str) -> List[Dict[str, Any]]:
    """Parse Docker container information from docker ps command output."""


    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []

    # For real-world parsing, use a simpler approach
    containers = []
    for line in lines[1:]:
        if not line.strip():
            continue

        # Split by whitespace and handle special cases
        parts = line.split()
        if len(parts) < 5:
            continue

        # Extract container ID, image, and name
        container_id = parts[0]

        # Find the name (last part)
        name = parts[-1]

        # Find the status part (usually contains "Up" or "Exited")
        status_idx = -1
        for i, part in enumerate(parts):
            if "Up" in part or "Exited" in part:
                status_idx = i
                break

        # Default status if not found
        status = "unknown"
        if status_idx >= 0:
            # Combine status parts
            status = " ".join(parts[status_idx:status_idx+3 if status_idx+3 < len(parts) else len(parts)-1])

        # Extract image (everything between ID and status)
        image_end = status_idx if status_idx > 0 else len(parts) - 2
        image = parts[1]
        if image_end > 1:
            image = " ".join(parts[1:image_end])

        # Find command (usually in quotes)
        command = ""
        for i, part in enumerate(parts):
            if part.startswith('"/') or part.startswith('\"/') or part == '"/init"':
                command = part.strip('"')
                break

        # Find created time (usually contains "ago")
        created = ""
        for i in range(len(parts)):
            if i+1 < len(parts) and "ago" in parts[i+1]:
                created = parts[i] + " " + parts[i+1]
                break

        container = {
            "id": container_id,
            "image": image,
            "command": command,
            "created": created,
            "status": status,
            "name": name
        }

        # Determine state from status
        status_lower = status.lower()
        if "up" in status_lower:
            container["state"] = "running"
        elif "exited" in status_lower:
            container["state"] = "exited"
        elif "created" in status_lower:
            container["state"] = "created"
        elif "restarting" in status_lower:
            container["state"] = "restarting"
        elif "paused" in status_lower:
            container["state"] = "paused"
        elif "dead" in status_lower:
            container["state"] = "dead"
        else:
            container["state"] = "unknown"

        containers.append(container)

    return containers


def parse_vm_list(output: str) -> List[Dict[str, Any]]:
    """Parse VM information from virsh list command output."""
    lines = output.strip().split("\n")
    if len(lines) < 3:  # Header, separator, and at least one VM
        return []

    # Skip header and separator
    vms = []
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

        vms.append(vm)

    return vms


def parse_network_info(output: str) -> List[Dict[str, Any]]:
    """Parse network interface information from ip addr command output."""
    interfaces = []
    current_interface = None

    for line in output.split("\n"):
        # New interface
        if line.strip() and not line.startswith(" "):
            if current_interface:
                interfaces.append(current_interface)

            # Extract interface name and state
            match = re.search(r"^\d+: ([^:]+): .* state (\w+)", line)
            if match:
                name = match.group(1)
                state = match.group(2)
                current_interface = {
                    "name": name,
                    "state": state
                }

        # Interface details
        elif current_interface and line.strip():
            # MAC address
            mac_match = re.search(r"link/\w+ ([0-9a-f:]+)", line)
            if mac_match:
                current_interface["mac"] = mac_match.group(1)

            # IPv4 address
            ipv4_match = re.search(r"inet ([0-9.]+/\d+)", line)
            if ipv4_match:
                current_interface["ipv4"] = ipv4_match.group(1)

            # IPv6 address
            ipv6_match = re.search(r"inet6 ([0-9a-f:]+/\d+)", line)
            if ipv6_match:
                current_interface["ipv6"] = ipv6_match.group(1)

    # Add the last interface
    if current_interface:
        interfaces.append(current_interface)

    return interfaces


def parse_ups_status(output: str) -> Dict[str, Any]:
    """Parse UPS status information from upsc command output."""
    result = {}

    for line in output.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            # Convert to snake_case
            key = key.replace(".", "_")

            # Convert numeric values
            try:
                if "." in value:
                    value = float(value)
                else:
                    value = int(value)
            except ValueError:
                pass

            # Map common keys to standardized names
            if key == "battery_charge":
                result["battery_charge"] = value
            elif key == "battery_runtime":
                result["battery_runtime"] = value
            elif key == "device_model":
                result["model"] = value
            elif key == "device_serial":
                result["serial"] = value
            elif key == "ups_load":
                result["load"] = value
            elif key == "ups_status":
                result["status"] = value
            elif key == "ups_temperature":
                result["temperature"] = value
            elif key == "input_voltage":
                result["input_voltage"] = value
            else:
                result[key] = value

    return result


def parse_parity_check_status(output: str, output_type: str = "mdstat") -> Dict[str, Any]:
    """Parse parity check status information."""
    if output_type == "mdstat":
        return _parse_mdstat_output(output)
    elif output_type == "log":
        return _parse_parity_log_output(output)
    else:
        _LOGGER.warning("Unknown output type: %s", output_type)
        return {}


def _parse_mdstat_output(output: str) -> Dict[str, Any]:
    """Parse /proc/mdstat output for parity check status."""
    result = {
        "active": False,
        "progress": 0,
        "speed": "",
        "finish": "",
        "device": ""
    }

    # Check if parity check is active
    if "check" in output:
        result["active"] = True

        # Extract device
        device_match = re.search(r"^(md\d+) :", output, re.MULTILINE)
        if device_match:
            result["device"] = device_match.group(1)

        # Extract progress
        progress_match = re.search(r"check = (\d+\.\d+)%", output)
        if progress_match:
            result["progress"] = float(progress_match.group(1))

        # Extract speed
        speed_match = re.search(r"speed=(\d+K/sec)", output)
        if speed_match:
            result["speed"] = speed_match.group(1)

        # Extract finish time
        finish_match = re.search(r"finish=(\d+\.\d+min|\d+:\d+)", output)
        if finish_match:
            result["finish"] = finish_match.group(1)

    return result


def _parse_parity_log_output(output: str) -> Dict[str, Any]:
    """Parse parity check log output."""
    result = {
        "last_check": "",
        "last_status": "",
        "last_duration": 0,
        "previous_check": "",
        "previous_status": "",
        "previous_duration": 0
    }



    # Find completed or aborted checks
    completed_matches = re.finditer(r"([\w]+ \d+ \d+:\d+:\d+) .* data-check completed .* in (\d+) seconds", output)
    aborted_matches = re.finditer(r"([\w]+ \d+ \d+:\d+:\d+) .* data-check aborted after (\d+) seconds", output)

    # Combine and sort by date
    checks = []
    for match in completed_matches:
        checks.append({
            "date": match.group(1),
            "status": "completed",
            "duration": int(match.group(2))
        })

    for match in aborted_matches:
        checks.append({
            "date": match.group(1),
            "status": "aborted",
            "duration": int(match.group(2))
        })

    # Sort by date (most recent first)
    checks.sort(key=lambda x: x["date"], reverse=True)

    # Get last and previous check
    if len(checks) > 0:
        result["last_check"] = checks[0]["date"]
        result["last_status"] = checks[0]["status"]
        result["last_duration"] = checks[0]["duration"]

        if len(checks) > 1:
            result["previous_check"] = checks[1]["date"]
            result["previous_status"] = checks[1]["status"]
            result["previous_duration"] = checks[1]["duration"]

    return result
