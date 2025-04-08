"""Constants for Unraid diagnostic sensors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any
from enum import Enum

from homeassistant.components.binary_sensor import (  # type: ignore
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory  # type: ignore

# Parity Check Status Constants
PARITY_STATUS_IDLE = "Success"
PARITY_STATUS_UNKNOWN = "Unknown"
PARITY_STATUS_CHECKING = "Running"

# Parity History Date Formats
PARITY_HISTORY_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
PARITY_TIME_FORMAT = "%H:%M"
PARITY_FULL_DATE_FORMAT = "%b %d %Y %H:%M"

# Default Parity Attributes
DEFAULT_PARITY_ATTRIBUTES = {
    "status": PARITY_STATUS_IDLE,
    "progress": 0,
    "speed": "N/A",
    "errors": 0,
    "last_check": "N/A",
    "next_check": "Unknown",
    "duration": "N/A",
    "last_status": "N/A"
}

# Speed Units
class SpeedUnit(Enum):
    """Speed units with their multipliers."""
    BYTES = (1, "B")
    KILOBYTES = (1024, "KB")
    MEGABYTES = (1024 * 1024, "MB")
    GIGABYTES = (1024 * 1024 * 1024, "GB")

    # Decimal Units
    DECIMAL_KILOBYTES = (1000, "kB")
    DECIMAL_MEGABYTES = (1_000_000, "MB")
    DECIMAL_GIGABYTES = (1_000_000_000, "GB")

    def __init__(self, multiplier: int, symbol: str):
        self.multiplier = multiplier
        self.symbol = symbol

    @staticmethod
    def from_symbol(symbol: str):
        """Retrieve SpeedUnit based on symbol."""
        symbol = symbol.upper()
        for unit in SpeedUnit:
            if unit.symbol == symbol:
                return unit
        raise ValueError(f"Unknown speed unit: {symbol}")

@dataclass
class UnraidBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Unraid binary sensor entity."""

    key: str
    name: str | None = None
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None
    value_fn: Callable[[dict[str, Any]], bool | None] = field(default=lambda x: None)
    has_warning_threshold: bool = False
    warning_threshold: float | None = None

SENSOR_DESCRIPTIONS: tuple[UnraidBinarySensorEntityDescription, ...] = (
    UnraidBinarySensorEntityDescription(
        key="ssh_connectivity",
        name="Server Connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("system_stats") is not None,
        icon="mdi:server-network",
    ),
    UnraidBinarySensorEntityDescription(
        key="docker_service",
        name="Docker Service",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("docker_containers")),
        icon="mdi:docker",
    ),
    UnraidBinarySensorEntityDescription(
        key="vm_service",
        name="VM Service",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.get("vms")),
        icon="mdi:desktop-tower",
    ),
)

__all__ = [
    "UnraidBinarySensorEntityDescription",
    "SENSOR_DESCRIPTIONS",
    "SpeedUnit",
    "PARITY_STATUS_IDLE",
    "PARITY_STATUS_UNKNOWN",
    "PARITY_STATUS_CHECKING",
    "PARITY_HISTORY_DATE_FORMAT",
    "PARITY_TIME_FORMAT",
    "PARITY_FULL_DATE_FORMAT",
    "DEFAULT_PARITY_ATTRIBUTES",
]
