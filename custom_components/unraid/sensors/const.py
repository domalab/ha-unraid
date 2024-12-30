"""Constants for Unraid sensors."""
from __future__ import annotations

import re
from typing import Final, Callable, Any, Pattern, Set, List, Dict
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

# Temperature thresholds
TEMP_WARN_THRESHOLD: Final = 60  # °C
TEMP_CRIT_THRESHOLD: Final = 80  # °C

@dataclass
class ChipsetFanPattern:
    """Pattern definition for chipset fan detection."""
    patterns: List[str]
    rpm_keys: List[str]
    description: str

# Chipset-specific fan patterns
CHIPSET_FAN_PATTERNS: Dict[str, ChipsetFanPattern] = {
    "nct67": ChipsetFanPattern(
        patterns=["fan", "sys_fan", "chassis_fan", "array_fan"],
        rpm_keys=["fan{}_input", "fan_input"],
        description="Nuvoton NCT67xx series"
    ),
    "it87": ChipsetFanPattern(
        patterns=["fan", "system_fan", "power_fan", "cpu_fan"],
        rpm_keys=["fan{}_input", "speed"],
        description="ITE IT87xx series"
    ),
    "w83795": ChipsetFanPattern(
        patterns=["fan", "fanin", "sys_fan"],
        rpm_keys=["fan{}_input", "speed"],
        description="Winbond W83795G/ADG"
    ),
    "f71882": ChipsetFanPattern(
        patterns=["fan", "fan_in"],
        rpm_keys=["fan{}_input"],
        description="Fintek F71882FG"
    ),
    "nzxt": ChipsetFanPattern(
        patterns=["fan", "channel"],
        rpm_keys=["fan{}_input", "speed"],
        description="NZXT Smart Device"
    ),
    "k10temp": ChipsetFanPattern(
        patterns=["fan", "cpu_fan"],
        rpm_keys=["fan{}_input"],
        description="AMD K10 temperature sensor"
    ),
    "coretemp": ChipsetFanPattern(
        patterns=["fan", "cpu_fan"],
        rpm_keys=["fan{}_input"],
        description="Intel Core temperature sensor"
    )
}

# Common fan number extraction patterns
FAN_NUMBER_PATTERNS: List[str] = [
    r'fan(\d+)',
    r'#(\d+)',
    r'\s(\d+)',
    r'channel\s*(\d+)',
    r'(\d+)$'
]

# Default patterns for unknown chipsets
DEFAULT_FAN_PATTERNS: List[str] = ["fan", "sys_fan", "chassis_fan"]
DEFAULT_RPM_KEYS: List[str] = ["fan{}_input", "fan_input", "speed"]

# RPM validation constants
MIN_VALID_RPM: int = 0
MAX_VALID_RPM: int = 10000

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