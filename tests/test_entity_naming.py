# tests/test_entity_naming.py
"""Tests for the Unraid entity naming helper."""

import pytest

from custom_components.unraid.const import DOMAIN
from custom_components.unraid.entity_naming import EntityNaming

@pytest.fixture
def naming_helper():
    """Fixture for EntityNaming."""
    return EntityNaming(DOMAIN, "TestHost", "TestComponent")

def test_entity_naming_init(naming_helper):
    """Test the initialization of the EntityNaming class."""
    assert naming_helper.domain == DOMAIN
    assert naming_helper.hostname == "testhost"  # Should be lowercased
    assert naming_helper.component == "TestComponent"
    assert naming_helper.entity_format == 2 # Default format

def test_get_entity_name(naming_helper):
    """Test the get_entity_name method."""
    assert naming_helper.get_entity_name("my_entity") == "TestComponent_my_entity"
    assert naming_helper.get_entity_name("another_entity", "CustomComponent") == "CustomComponent_another_entity"

def test_get_entity_id(naming_helper):
    """Test the get_entity_id method."""
    # Test basic ID generation
    assert naming_helper.get_entity_id("my_entity") == "unraid_testhost_my_entity"

    # Test with component_type override (should not affect ID based on current implementation)
    assert naming_helper.get_entity_id("another_entity", "CustomComponent") == "unraid_testhost_another_entity"

    # Test hostname prefix removal (lowercase)
    assert naming_helper.get_entity_id("testhost_my_entity") == "unraid_testhost_my_entity"

    # Test hostname prefix removal (capitalized)
    assert naming_helper.get_entity_id("TestHost_my_entity") == "unraid_testhost_my_entity"

    # Test hostname prefix removal (uppercase)
    assert naming_helper.get_entity_id("TESTHOST_my_entity") == "unraid_testhost_my_entity"

    # Test ID that doesn't start with hostname
    assert naming_helper.get_entity_id("some_other_entity") == "unraid_testhost_some_other_entity"

def test_clean_hostname(naming_helper):
    """Test the clean_hostname method."""
    # Test with a simple hostname
    assert naming_helper.clean_hostname() == "Testhost"

    # Test with underscores
    naming_helper_underscore = EntityNaming(DOMAIN, "test_host_name", "TestComponent")
    assert naming_helper_underscore.clean_hostname() == "Test Host Name"

    # Test with already clean hostname (should remain title case)
    naming_helper_clean = EntityNaming(DOMAIN, "CleanHost", "TestComponent")
    assert naming_helper_clean.clean_hostname() == "Cleanhost" # Note: .title() makes subsequent chars lowercase
