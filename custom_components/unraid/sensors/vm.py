"""VM sensors for Unraid integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN, DEVICE_ID_SERVER, DEVICE_INFO_SERVER
from ..coordinator import UnraidDataUpdateCoordinator
from .test_base import UnraidTestSensor

_LOGGER = logging.getLogger(__name__)


class UnraidVMCountSensor(UnraidTestSensor):
    """Sensor for Unraid VM count."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"unraid_vm_count"
        self._attr_name = "VMs"
        self._attr_icon = "mdi:server"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[int]:
        """Return the number of VMs."""
        if not self.coordinator.data or "vm_info" not in self.coordinator.data:
            return None

        vm_info = self.coordinator.data.get("vm_info", {})
        return vm_info.get("vm_count", None)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes about VMs."""
        attrs = {}

        if not self.coordinator.data or "vm_info" not in self.coordinator.data:
            return attrs

        vm_info = self.coordinator.data.get("vm_info", {})
        vms = vm_info.get("vms", [])

        # Count running and stopped VMs
        running_count = 0
        stopped_count = 0

        for vm in vms:
            status = vm.get("status", "").lower()
            if status == "running":
                running_count += 1
            elif status in ["shutoff", "stopped"]:
                stopped_count += 1

        attrs["running_vms"] = running_count
        attrs["stopped_vms"] = stopped_count

        return attrs


class UnraidVMStatusSensor(UnraidTestSensor):
    """Sensor for Unraid VM service status."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"unraid_vm_status"
        self._attr_name = "VM Status"
        self._attr_icon = "mdi:server"

    @property
    def native_value(self) -> str:
        """Return the VM service status."""
        if not self.coordinator.data or "vm_info" not in self.coordinator.data:
            return "not_detected"

        vm_info = self.coordinator.data.get("vm_info", {})
        if not vm_info:
            return "not_detected"

        vms_running = vm_info.get("vms_running", False)
        libvirt_running = vm_info.get("libvirt_running", False)

        if vms_running:
            return "running"
        elif libvirt_running:
            return "idle"
        else:
            return "stopped"
