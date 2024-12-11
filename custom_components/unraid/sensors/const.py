"""Constants for Unraid sensors."""
from __future__ import annotations

import re
from typing import Final, Callable, Any, Pattern, Set
from dataclasses import dataclass, field

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import ( # type: ignore
    UnitOfTemperature,
    UnitOfPower,
    UnitOfFrequency,
)

DOMAIN: Final = "unraid"

# Unit constants for clarity and consistency
UNIT_WATTS: Final = UnitOfPower.WATT
UNIT_HERTZ: Final = UnitOfFrequency.HERTZ
UNIT_CELSIUS: Final = UnitOfTemperature.CELSIUS

# Sensor update intervals
FAST_POLL_INTERVAL: Final = 30  # seconds
STANDARD_POLL_INTERVAL: Final = 60  # seconds
SLOW_POLL_INTERVAL: Final = 300  # seconds

# Storage Constants
DISK_NUMBER_PATTERN: Pattern = re.compile(r'disk(\d+)$')
MOUNT_POINT_PATTERN: Pattern = re.compile(r'/mnt/disk(\d+)$')

# Network Constants
VALID_INTERFACE_PATTERN: Pattern = re.compile(r'^[a-zA-Z0-9]+$')
EXCLUDED_INTERFACES: Set[str] = {'lo', 'tunl0', 'sit0'}

# Docker Constants
DOCKER_CONTAINER_METRICS: tuple[str, ...] = (
    "cpu_percentage",
    "memory_usage",
    "memory_percentage",
    "network_speed_up",
    "network_speed_down",
)

# Temperature thresholds
TEMP_WARN_THRESHOLD: Final = 60  # °C
TEMP_CRIT_THRESHOLD: Final = 80  # °C

@dataclass
class UnraidSensorEntityDescription(SensorEntityDescription):
    """Describes Unraid sensor entity."""

    key: str
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    name: str | None = None
    native_unit_of_measurement: str | None = None
    icon: str | None = None
    entity_category: str | None = None
    value_fn: Callable[[dict[str, Any]], Any] = field(default=lambda _: None)
    should_poll: bool = field(default=False)
    available_fn: Callable[[dict[str, Any]], bool] = field(default=lambda _: True)
    suggested_unit_of_measurement: str | None = field(default=None)
    suggested_display_precision: int | None = field(default=None)
    translation_key: str | None = field(default=None)

    def __post_init__(self) -> None:
        """Post initialization hook."""
        super().__init__(
            key=self.key,
            device_class=self.device_class,
            state_class=self.state_class,
            name=self.name,
            native_unit_of_measurement=self.native_unit_of_measurement,
            icon=self.icon,
            entity_category=self.entity_category,
        )