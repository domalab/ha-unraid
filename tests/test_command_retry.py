"""Unit tests for command retry and error recovery in the Unraid integration."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call, PropertyMock

from custom_components.unraid.api.ssh_client import UnraidSSHClient
from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator


@pytest.fixture
def mock_asyncssh():
    """Create a mock asyncssh module."""
    with patch("custom_components.unraid.api.ssh_client.asyncssh") as mock_asyncssh:
        # Create a mock connection
        mock_connection = AsyncMock()
        mock_connection.is_connected = True
        mock_connection.run = AsyncMock()
        mock_connection.close = AsyncMock()
        mock_connection.wait_closed = AsyncMock()
        
        # Make the connect method return the mock connection
        mock_asyncssh.connect = AsyncMock(return_value=mock_connection)
        
        # Create a mock result with success status
        result = MagicMock()
        result.exit_status = 0
        result.stdout = "Command output"
        result.stderr = ""
        mock_connection.run.return_value = result
        
        yield mock_asyncssh


@pytest.fixture
def ssh_client(mock_asyncssh):
    """Create an SSH client with retry capabilities."""
    class RetryableSSHClient(UnraidSSHClient):
        """SSH client with retry capabilities for testing."""
        
        async def run_command_with_retry(self, command, max_retries=3, retry_delay=0.1, timeout=60):
            """Run a command with retry logic."""
            retries = 0
            while True:
                try:
                    result = await self.run_command(command, timeout=timeout)
                    return result
                except Exception as e:
                    retries += 1
                    if retries > max_retries:
                        raise
                    await asyncio.sleep(retry_delay)
    
    client = RetryableSSHClient(
        host="192.168.1.10",
        username="root",
        password="password",
        port=22
    )
    return client


class TestCommandRetry:
    """Test automatic retry of failed commands."""
    
    @pytest.mark.asyncio
    async def test_command_retry_success(self, ssh_client, mock_asyncssh):
        """Test that commands are retried upon transient failures."""
        # Connect
        await ssh_client.connect()
        
        # Setup mock connection and results
        mock_connection = mock_asyncssh.connect.return_value
        
        # First call fails with a transient error, second succeeds
        error = mock_asyncssh.Error("Temporary network error")
        
        success_result = MagicMock()
        success_result.exit_status = 0
        success_result.stdout = "Success after retry"
        
        # Configure the side effect to first raise an error, then return a success result
        mock_connection.run.side_effect = [error, success_result]
        
        # Run command with retry
        result = await ssh_client.run_command_with_retry("ls -la", max_retries=3, retry_delay=0.01)
        
        # Verify command was called twice (first fails, second succeeds)
        assert mock_connection.run.call_count == 2
        assert result.stdout == "Success after retry"
    
    @pytest.mark.asyncio
    async def test_command_retry_failure(self, ssh_client, mock_asyncssh):
        """Test that command retry gives up after max retries."""
        # Connect
        await ssh_client.connect()
        
        # Setup mock connection and results
        mock_connection = mock_asyncssh.connect.return_value
        
        # All calls fail with an error
        error = mock_asyncssh.Error("Persistent error")
        mock_connection.run.side_effect = error
        
        # Run command with retry - should fail after max retries
        with pytest.raises(mock_asyncssh.Error) as excinfo:
            await ssh_client.run_command_with_retry("ls -la", max_retries=3, retry_delay=0.01)
        
        # Verify command was called expected number of times (1 initial + 3 retries)
        assert mock_connection.run.call_count == 4
        assert str(excinfo.value) == "Persistent error"
    
    @pytest.mark.asyncio
    async def test_command_retry_partial_failures(self, ssh_client, mock_asyncssh):
        """Test command retry with some failures but eventual success."""
        # Connect
        await ssh_client.connect()
        
        # Setup mock connection and results
        mock_connection = mock_asyncssh.connect.return_value
        
        # Create error and success results
        error1 = mock_asyncssh.Error("Temporary error 1")
        error2 = mock_asyncssh.Error("Temporary error 2")
        
        success_result = MagicMock()
        success_result.exit_status = 0
        success_result.stdout = "Success after multiple retries"
        
        # Configure failures on first two attempts, success on third
        mock_connection.run.side_effect = [error1, error2, success_result]
        
        # Run command with retry
        result = await ssh_client.run_command_with_retry("ls -la", max_retries=5, retry_delay=0.01)
        
        # Verify command was called three times
        assert mock_connection.run.call_count == 3
        assert result.stdout == "Success after multiple retries"
    
    @pytest.mark.asyncio
    async def test_command_retry_exit_status_failure(self, ssh_client, mock_asyncssh):
        """Test command retry with command failure (non-zero exit status)."""
        # Connect
        await ssh_client.connect()
        
        # Setup mock connection and results
        mock_connection = mock_asyncssh.connect.return_value
        
        # Create failure result with non-zero exit status
        failure_result = MagicMock()
        failure_result.exit_status = 1
        failure_result.stdout = ""
        failure_result.stderr = "Command failed"
        
        # Create success result
        success_result = MagicMock()
        success_result.exit_status = 0
        success_result.stdout = "Command succeeded"
        success_result.stderr = ""
        
        # Configure command to fail first then succeed
        mock_connection.run.side_effect = [failure_result, success_result]
        
        # For this test we'll need to create a custom retryable client that retries on non-zero exit status
        class ExitStatusRetryClient(UnraidSSHClient):
            """SSH client that retries on non-zero exit status."""
            
            async def run_command_with_exit_status_retry(self, command, max_retries=3, retry_delay=0.1, timeout=60):
                """Run a command with retry logic for non-zero exit status."""
                retries = 0
                while True:
                    result = await self.run_command(command, timeout=timeout)
                    if result.exit_status == 0:
                        return result
                    
                    retries += 1
                    if retries > max_retries:
                        return result  # Return the failed result if max retries exceeded
                    
                    await asyncio.sleep(retry_delay)
        
        # Create the client and connect
        exit_status_client = ExitStatusRetryClient(
            host="192.168.1.10",
            username="root",
            password="password",
            port=22
        )
        exit_status_client.conn = mock_connection
        exit_status_client._connected = True
        
        # Run command with retry
        result = await exit_status_client.run_command_with_exit_status_retry("ls -la", max_retries=3, retry_delay=0.01)
        
        # Verify command was called twice
        assert mock_connection.run.call_count == 2
        assert result.exit_status == 0
        assert result.stdout == "Command succeeded"


class TestCoordinatorRetryBehavior:
    """Test retry behavior in the UnraidDataUpdateCoordinator."""
    
    @pytest.mark.asyncio
    async def test_coordinator_update_retry(self):
        """Test that the coordinator retries updates upon transient failures."""
        # Create a mock API client that fails occasionally
        api_client = MagicMock()
        
        # Create success and error responses
        success_data = {"system_stats": {"uptime": 12345}}
        
        # Configure update_data to fail twice then succeed
        api_client.update_data = AsyncMock()
        api_client.update_data.side_effect = [
            RuntimeError("First failure"),
            RuntimeError("Second failure"),
            success_data
        ]
        
        # Create a coordinator with retry behavior
        with patch("custom_components.unraid.coordinator.UPDATE_INTERVAL", 30):
            coordinator = UnraidDataUpdateCoordinator(
                hass=MagicMock(),
                api=api_client,
                entry=MagicMock(),
                update_interval=30
            )
            
            # Add a property to track retry attempts
            coordinator.retry_count = 0
            original_async_refresh = coordinator.async_refresh
            
            async def async_refresh_with_tracking():
                coordinator.retry_count += 1
                await original_async_refresh()
            
            coordinator.async_refresh = async_refresh_with_tracking
            
            # Perform the first update
            await coordinator.async_refresh()
            
            # After the failures, should eventually get success
            assert coordinator.data == success_data
            assert api_client.update_data.call_count == 3
            assert coordinator.retry_count == 3
    
    @pytest.mark.asyncio
    async def test_coordinator_error_recovery(self):
        """Test that the coordinator recovers from errors between updates."""
        # Create a mock API client
        api_client = MagicMock()
        
        # First update succeeds, second fails, third succeeds
        api_client.update_data = AsyncMock()
        api_client.update_data.side_effect = [
            {"system_stats": {"uptime": 12345}},
            RuntimeError("Temporary failure"),
            {"system_stats": {"uptime": 12400}}
        ]
        
        # Create a coordinator
        with patch("custom_components.unraid.coordinator.UPDATE_INTERVAL", 30):
            coordinator = UnraidDataUpdateCoordinator(
                hass=MagicMock(),
                api=api_client,
                entry=MagicMock(),
                update_interval=30
            )
            
            # First update should succeed
            await coordinator.async_refresh()
            assert coordinator.last_update_success is True
            assert coordinator.data == {"system_stats": {"uptime": 12345}}
            
            # Second update should fail
            await coordinator.async_refresh()
            assert coordinator.last_update_success is False
            
            # But data should be preserved from last successful update
            assert coordinator.data == {"system_stats": {"uptime": 12345}}
            
            # Third update should succeed
            await coordinator.async_refresh()
            assert coordinator.last_update_success is True
            assert coordinator.data == {"system_stats": {"uptime": 12400}} 