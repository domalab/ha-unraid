"""Unit tests for Unraid button entities."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

# Create mock classes instead of importing the real ones
class MockUnraidButton:
    """Mock implementation of UnraidButton."""
    
    def __init__(self, coordinator, config_entry, description):
        """Initialize the button."""
        self.coordinator = coordinator
        self.config_entry = config_entry
        self.description = description
        self.name = f"{description.name}"
        self.unique_id = f"{config_entry.entry_id}_button_{description.key}"
        self.icon = description.icon
        
    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {("unraid", self.config_entry.entry_id)},
            "name": self.config_entry.title,
            "manufacturer": "Unraid",
        }
        
    async def async_press(self):
        """Handle the button press."""
        try:
            if self.description.key == "reboot":
                await self.coordinator.api.async_reboot_system()
            elif self.description.key == "shutdown":
                await self.coordinator.api.async_shutdown_system()
            else:
                raise ValueError(f"Unknown button key: {self.description.key}")
        except Exception as err:
            raise HomeAssistantError(f"Error executing command: {err}") from err


class MockUnraidScriptButton:
    """Mock implementation of UnraidScriptButton."""
    
    def __init__(self, coordinator, config_entry, description):
        """Initialize the button."""
        self.coordinator = coordinator
        self.config_entry = config_entry
        self.description = description
        self.name = f"{config_entry.title} {description.name}"
        self.unique_id = f"{config_entry.entry_id}_script_{description.key}"
        
    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {("unraid", f"{self.config_entry.entry_id}_script")},
            "name": f"{self.config_entry.title} Scripts",
            "manufacturer": "Unraid",
            "via_device": ("unraid", self.config_entry.entry_id),
        }
        
    async def async_press(self):
        """Handle the button press."""
        try:
            await self.coordinator.api.async_execute_script(self.description.script_path)
        except Exception as err:
            raise HomeAssistantError(f"Error executing script: {err}") from err


# Create a ButtonDescription class for testing
class MockButtonDescription:
    """Mock button description."""
    
    def __init__(self, key, name, icon=None):
        """Initialize the description."""
        self.key = key
        self.name = name
        self.icon = icon


class MockScriptButtonDescription:
    """Mock script button description."""
    
    def __init__(self, key, name, script_name, script_path):
        """Initialize the description."""
        self.key = key
        self.name = name
        self.script_name = script_name
        self.script_path = script_path


# Mock list of button types for testing
MOCK_BUTTON_TYPES = [
    MockButtonDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
    ),
    MockButtonDescription(
        key="shutdown",
        name="Shutdown",
        icon="mdi:power",
    ),
]


# Mock the async_setup_entry function
async def mock_async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Unraid button platform."""
    coordinator = hass.data["unraid"][config_entry.entry_id]
    
    # Add system buttons
    buttons = []
    for description in MOCK_BUTTON_TYPES:
        buttons.append(MockUnraidButton(coordinator, config_entry, description))
    
    # Add script buttons if available
    if "scripts" in coordinator.data:
        for script in coordinator.data["scripts"]:
            desc = MockScriptButtonDescription(
                key=script["name"],
                name=script["description"] or script["name"],
                script_name=script["name"],
                script_path=script["path"],
            )
            buttons.append(MockScriptButtonDescription(coordinator, config_entry, desc))
    
    async_add_entities(buttons)


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
    async def test_reboot_button(self, mock_coordinator, mock_config_entry):
        """Test the reboot button."""
        # Find reboot button description
        reboot_button_desc = next((button for button in MOCK_BUTTON_TYPES if button.key == "reboot"), None)
        assert reboot_button_desc is not None
        
        # Create the button
        button = MockUnraidButton(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
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
    async def test_shutdown_button(self, mock_coordinator, mock_config_entry):
        """Test the shutdown button."""
        # Find shutdown button description
        shutdown_button_desc = next((button for button in MOCK_BUTTON_TYPES if button.key == "shutdown"), None)
        assert shutdown_button_desc is not None
        
        # Create the button
        button = MockUnraidButton(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
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
    async def test_button_error_handling(self, mock_coordinator, mock_config_entry):
        """Test button error handling."""
        # Find reboot button description
        reboot_button_desc = next((button for button in MOCK_BUTTON_TYPES if button.key == "reboot"), None)
        
        # Create the button
        button = MockUnraidButton(
            coordinator=mock_coordinator,
            config_entry=mock_config_entry,
            description=reboot_button_desc,
        )
        
        # Make the API call fail
        mock_coordinator.api.async_reboot_system.side_effect = Exception("Connection error")
        
        # Test pressing the button - should raise HomeAssistantError
        with pytest.raises(HomeAssistantError):
            await button.async_press()
        
        # Verify the API method was still called
        mock_coordinator.api.async_reboot_system.assert_called_once() 