"""Tests for the Unraid switch platform."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.unraid.switch import (
    async_setup_entry,
    UnraidDockerContainerSwitch,
    UnraidVMSwitch,
)
from custom_components.unraid.const import DOMAIN


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.hostname = "unraid"
    coordinator.entry = MagicMock()
    coordinator.entry.entry_id = "test_entry_id"
    coordinator.data = {
        "docker_containers": [
            {
                "name": "test-container",
                "id": "123abc",
                "state": "running",
                "status": "Up 2 days",
                "image": "test/image:latest"
            },
            {
                "name": "stopped-container",
                "id": "456def",
                "state": "exited",
                "status": "Exited (0) 1 day ago",
                "image": "test/stopped:latest"
            }
        ],
        "vms": [
            {
                "name": "Windows VM",
                "status": "running",
                "os_type": "windows"
            },
            {
                "name": "Linux VM",
                "status": "shutoff",
                "os_type": "linux"
            }
        ]
    }
    coordinator.api = MagicMock()
    coordinator.api.start_container = AsyncMock()
    coordinator.api.stop_container = AsyncMock()
    coordinator.api.start_vm = AsyncMock()
    coordinator.api.stop_vm = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.last_update_success = True
    return coordinator


@pytest.mark.asyncio
async def test_switch_setup_entry(hass: HomeAssistant, mock_coordinator):
    """Test setting up the switch platform."""
    hass.data = {DOMAIN: {"test_entry_id": mock_coordinator}}
    
    # Create a mock entry and callback
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    
    # Track added entities
    added_entities = []
    
    # Define add_entities function
    async def async_add_entities(entities):
        added_entities.extend(entities)
    
    # Call the setup entry function
    await async_setup_entry(hass, entry, async_add_entities)
    
    # Check that entities were added
    assert len(added_entities) == 4  # 2 docker containers + 2 VMs
    
    # Check entity types
    docker_entities = [e for e in added_entities if isinstance(e, UnraidDockerContainerSwitch)]
    vm_entities = [e for e in added_entities if isinstance(e, UnraidVMSwitch)]
    
    assert len(docker_entities) == 2
    assert len(vm_entities) == 2


@pytest.mark.asyncio
async def test_docker_container_switch(mock_coordinator):
    """Test the Docker container switch."""
    # Create the switch
    switch = UnraidDockerContainerSwitch(
        coordinator=mock_coordinator,
        container_name="test-container"
    )
    
    # Test switch properties
    assert switch.name == "test-container"
    assert switch.available is True
    assert switch.is_on is True
    
    # Test extra attributes
    attrs = switch.extra_state_attributes
    assert attrs["container_id"] == "123abc"
    assert attrs["status"] == "Up 2 days"
    assert attrs["image"] == "test/image:latest"
    
    # Test turning off
    await switch.async_turn_off()
    mock_coordinator.api.stop_container.assert_called_once_with("test-container")
    mock_coordinator.async_request_refresh.assert_called_once()
    
    # Reset mocks for next test
    mock_coordinator.api.stop_container.reset_mock()
    mock_coordinator.async_request_refresh.reset_mock()
    
    # Test turning on
    await switch.async_turn_on()
    mock_coordinator.api.start_container.assert_called_once_with("test-container")
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_docker_container_switch_stopped(mock_coordinator):
    """Test the Docker container switch with a stopped container."""
    # Create the switch
    switch = UnraidDockerContainerSwitch(
        coordinator=mock_coordinator,
        container_name="stopped-container"
    )
    
    # Test switch properties
    assert switch.name == "stopped-container"
    assert switch.available is True
    assert switch.is_on is False


@pytest.mark.asyncio
async def test_vm_switch_running(mock_coordinator):
    """Test the VM switch with a running VM."""
    # Create the switch
    switch = UnraidVMSwitch(
        coordinator=mock_coordinator,
        vm_name="Windows VM"
    )
    
    # Test switch properties
    assert switch.name == "Windows VM"
    assert switch.available is True
    assert switch.is_on is True
    assert switch.icon == "mdi:microsoft-windows"
    
    # Test extra attributes
    attrs = switch.extra_state_attributes
    assert attrs["status"] == "running"
    assert attrs["os_type"] == "windows"
    
    # Test turning off
    await switch.async_turn_off()
    mock_coordinator.api.stop_vm.assert_called_once_with("Windows VM")
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_vm_switch_stopped(mock_coordinator):
    """Test the VM switch with a stopped VM."""
    # Create the switch
    switch = UnraidVMSwitch(
        coordinator=mock_coordinator,
        vm_name="Linux VM"
    )
    
    # Test switch properties
    assert switch.name == "Linux VM"
    assert switch.available is True
    assert switch.is_on is False
    assert switch.icon == "mdi:linux"
    
    # Test extra attributes
    attrs = switch.extra_state_attributes
    assert attrs["status"] == "shutoff"
    assert attrs["os_type"] == "linux"
    
    # Test turning on
    await switch.async_turn_on()
    mock_coordinator.api.start_vm.assert_called_once_with("Linux VM")
    mock_coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_vm_switch_unavailable(mock_coordinator):
    """Test VM switch availability when VM is not in the data."""
    # Create the switch with a non-existent VM
    switch = UnraidVMSwitch(
        coordinator=mock_coordinator,
        vm_name="NonExistent VM"
    )
    
    # Should not be available since VM doesn't exist in data
    assert switch.available is False
    
    # Extra attributes should have default values
    attrs = switch.extra_state_attributes
    assert attrs["status"] == "unknown"
    assert attrs["os_type"] == "unknown"


@pytest.mark.asyncio
async def test_vm_switch_coordinator_error(mock_coordinator):
    """Test VM switch when coordinator has error."""
    # Create the switch
    switch = UnraidVMSwitch(
        coordinator=mock_coordinator,
        vm_name="Windows VM"
    )
    
    # Set coordinator update to failed
    mock_coordinator.last_update_success = False
    
    # Check that switch is unavailable
    assert switch.available is False 