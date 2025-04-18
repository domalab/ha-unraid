"""Unit tests for Unraid button entities."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from custom_components.unraid.button import (
    async_setup_entry,
    UnraidButton,
    UnraidScriptButton,
    UnraidScriptButtonDescription,
    BUTTON_TYPES,
)
from custom_components.unraid.const import DOMAIN


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.hostname = "test_host"
    coordinator.entry = MagicMock()
    coordinator.entry.entry_id = "test_entry_id"
    coordinator.entry.title = "Test Unraid Server"
    coordinator.data = {
        "scripts": [
            {
                "name": "test_script",
                "description": "Test Script",
                "path": "/boot/config/plugins/user.scripts/scripts/test_script/script",
            },
        ]
    }
    coordinator.api = MagicMock()
    coordinator.api.async_reboot_system = AsyncMock()
    coordinator.api.async_shutdown_system = AsyncMock()
    coordinator.api.async_execute_script = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    config_entry = MagicMock(spec=ConfigEntry)
    config_entry.entry_id = "test_entry_id"
    config_entry.title = "Test Unraid Server"
    return config_entry


class TestUnraidButtons:
    """Test Unraid button entities."""

    @pytest.mark.asyncio
    async def test_button_setup_entry(self, hass: HomeAssistant, mock_coordinator, mock_config_entry):
        """Test setting up the button platform."""
        hass.data = {DOMAIN: {"test_entry_id": mock_coordinator}}
        
        # Track added entities
        added_entities = []
        
        # Define add_entities function
        async def async_add_entities(entities):
            added_entities.extend(entities)
        
        # Call the setup entry function
        await async_setup_entry(hass, mock_config_entry, async_add_entities)
        
        # Check that entities were added - should be system buttons plus script buttons
        assert len(added_entities) > 2  # At least reboot, shutdown, plus script
        
        # Check button types
        system_buttons = [e for e in added_entities if isinstance(e, UnraidButton)]
        script_buttons = [e for e in added_entities if isinstance(e, UnraidScriptButton)]
        
        assert len(system_buttons) >= 2  # At least reboot and shutdown
        assert len(script_buttons) >= 1  # At least one script button

    @pytest.mark.asyncio
    async def test_reboot_button(self, mock_coordinator):
        """Test the reboot button."""
        # Find reboot button description
        reboot_button_desc = next((button for button in BUTTON_TYPES if button.key == "reboot"), None)
        assert reboot_button_desc is not None
        
        # Create the button
        button = UnraidButton(
            coordinator=mock_coordinator,
            config_entry=mock_coordinator.entry,
            description=reboot_button_desc,
        )
        
        # Test button properties
        assert "reboot" in button.name.lower()
        assert button.unique_id == "test_entry_id_button_reboot"
        assert button.icon == reboot_button_desc.icon
        assert button.device_info is not None
        
        # Test pressing the button
        await button.async_press()
        
        # Verify that the reboot method was called
        mock_coordinator.api.async_reboot_system.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_button(self, mock_coordinator):
        """Test the shutdown button."""
        # Find shutdown button description
        shutdown_button_desc = next((button for button in BUTTON_TYPES if button.key == "shutdown"), None)
        assert shutdown_button_desc is not None
        
        # Create the button
        button = UnraidButton(
            coordinator=mock_coordinator,
            config_entry=mock_coordinator.entry,
            description=shutdown_button_desc,
        )
        
        # Test button properties
        assert "shutdown" in button.name.lower()
        assert button.unique_id == "test_entry_id_button_shutdown"
        assert button.icon == shutdown_button_desc.icon
        
        # Test pressing the button
        await button.async_press()
        
        # Verify that the shutdown method was called
        mock_coordinator.api.async_shutdown_system.assert_called_once()

    @pytest.mark.asyncio
    async def test_script_button(self, mock_coordinator):
        """Test a script button."""
        # Create script button description
        script_desc = UnraidScriptButtonDescription(
            key="test_script",
            name="Test Script",
            script_name="test_script",
            script_path="/boot/config/plugins/user.scripts/scripts/test_script/script",
        )
        
        # Create the button
        button = UnraidScriptButton(
            coordinator=mock_coordinator,
            config_entry=mock_coordinator.entry,
            description=script_desc,
        )
        
        # Test button properties
        assert button.name == "Test Unraid Server Test Script"
        assert button.unique_id == "test_entry_id_script_test_script"
        assert button.device_info is not None
        
        # Test pressing the button
        await button.async_press()
        
        # Verify that the execute script method was called with the correct path
        mock_coordinator.api.async_execute_script.assert_called_once_with(
            "/boot/config/plugins/user.scripts/scripts/test_script/script"
        )

    @pytest.mark.asyncio
    async def test_button_error_handling(self, mock_coordinator):
        """Test button error handling."""
        # Find reboot button description
        reboot_button_desc = next((button for button in BUTTON_TYPES if button.key == "reboot"), None)
        
        # Create the button
        button = UnraidButton(
            coordinator=mock_coordinator,
            config_entry=mock_coordinator.entry,
            description=reboot_button_desc,
        )
        
        # Make the API call fail
        mock_coordinator.api.async_reboot_system.side_effect = Exception("Connection error")
        
        # Test pressing the button - should raise HomeAssistantError
        with pytest.raises(HomeAssistantError):
            await button.async_press()
        
        # Verify the API method was still called
        mock_coordinator.api.async_reboot_system.assert_called_once()

    @pytest.mark.asyncio
    async def test_script_button_error(self, mock_coordinator):
        """Test script button error handling."""
        # Create script button description with non-existent script
        script_desc = UnraidScriptButtonDescription(
            key="nonexistent_script",
            name="Nonexistent Script",
            script_name="nonexistent_script",
            script_path="/path/does/not/exist",
        )
        
        # Create the button
        button = UnraidScriptButton(
            coordinator=mock_coordinator,
            config_entry=mock_coordinator.entry,
            description=script_desc,
        )
        
        # Make the API call fail
        mock_coordinator.api.async_execute_script.side_effect = Exception("Script not found")
        
        # Test pressing the button - should raise HomeAssistantError
        with pytest.raises(HomeAssistantError):
            await button.async_press()
        
        # Verify the API method was still called with correct path
        mock_coordinator.api.async_execute_script.assert_called_once_with("/path/does/not/exist") 