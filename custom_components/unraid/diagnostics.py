"""Diagnostics support for Unraid."""
from __future__ import annotations

import json
from typing import Any

from homeassistant.components.diagnostics import async_redact_data # type: ignore
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.const import ( # type: ignore
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant # type: ignore

from .const import DOMAIN

TO_REDACT = {
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_PORT,
    "UPSNAME",  # UPS identifier
    "SERIALNO",  # UPS serial number
    "HOSTNAME",  # Server hostname
    "identifiers",  # Device identifiers
}

def format_bytes(bytes_value: int) -> str:
    """Format bytes into human readable sizes."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, 
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Get system stats data
    system_stats = coordinator.data.get("system_stats", {})
    
    # Process disk data with formatted sizes
    processed_disks = []
    for disk in system_stats.get("individual_disks", []):
        if not isinstance(disk, dict):
            continue
        processed_disks.append({
            "name": disk.get("name", "unknown"),
            "percentage": f"{disk.get('percentage', 0):.1f}%",
            "total_size": format_bytes(disk.get("total", 0)),
            "used_space": format_bytes(disk.get("used", 0)),
            "free_space": format_bytes(disk.get("free", 0)),
            "mount_point": disk.get("mount_point", "unknown"),
        })

    # Process temperature data
    temp_data = system_stats.get("temperature_data", {}).get("sensors", {})
    processed_temps = {}
    for sensor, data in temp_data.items():
        processed_temps[sensor] = {k: v for k, v in data.items() if isinstance(v, (str, int, float))}

    # Create diagnostics data structure
    diagnostics_data = {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "integration_type": entry.domain,
        },
        "system_status": {
            "array_usage": {
                "percentage": f"{system_stats.get('array_usage', {}).get('percentage', 0):.1f}%",
                "total_size": format_bytes(system_stats.get('array_usage', {}).get('total', 0)),
                "used_space": format_bytes(system_stats.get('array_usage', {}).get('used', 0)),
                "free_space": format_bytes(system_stats.get('array_usage', {}).get('free', 0)),
            },
            "memory_usage": {
                "percentage": f"{system_stats.get('memory_usage', {}).get('percentage', 0):.1f}%",
            },
            "individual_disks": processed_disks,
            "temperatures": processed_temps,
            "docker_info": {
                "container_count": len(coordinator.data.get("docker_containers", [])),
                "containers": [
                    {"name": container.get("name"), "status": container.get("status")}
                    for container in coordinator.data.get("docker_containers", [])
                ],
            },
            "vm_info": {
                "vm_count": len(coordinator.data.get("vms", [])),
                "vms": [
                    {"name": vm.get("name"), "status": vm.get("status")}
                    for vm in coordinator.data.get("vms", [])
                ],
            },
        },
    }

    # Add UPS info if available
    if coordinator.has_ups and "ups_info" in system_stats:
        ups_info = system_stats["ups_info"]
        diagnostics_data["system_status"]["ups_info"] = async_redact_data({
            "status": ups_info.get("STATUS"),
            "battery_charge": ups_info.get("BCHARGE"),
            "load_percentage": ups_info.get("LOADPCT"),
            "runtime_left": ups_info.get("TIMELEFT"),
            "nominal_power": ups_info.get("NOMPOWER"),
            "battery_voltage": ups_info.get("BATTV"),
            "line_voltage": ups_info.get("LINEV"),
        }, TO_REDACT)

    # Add cache info if available
    cache_usage = system_stats.get("cache_usage")
    if cache_usage:
        diagnostics_data["system_status"]["cache_usage"] = {
            "percentage": f"{cache_usage.get('percentage', 0):.1f}%",
            "total_size": format_bytes(cache_usage.get('total', 0)),
            "used_space": format_bytes(cache_usage.get('used', 0)),
            "free_space": format_bytes(cache_usage.get('free', 0)),
        }

    # Ensure all values are JSON serializable
    return json.loads(json.dumps(diagnostics_data))