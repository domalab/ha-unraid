"""Constants for Unraid diagnostic sensors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any

from homeassistant.components.binary_sensor import ( # type: ignore
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory # type: ignore

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

__all__ = ["UnraidBinarySensorEntityDescription", "SENSOR_DESCRIPTIONS"]