"""Unit tests for SSH connectivity and command execution in the Unraid integration."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call, PropertyMock

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.unraid.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid.const import DOMAIN
from custom_components.unraid.api.ssh_client import UnraidSSHClient


@pytest.fixture
def mock_ssh_connection():
    """Create a mock SSH connection."""
    connection = AsyncMock()
    connection.is_connected = True
    connection.run = AsyncMock()
    connection.close = AsyncMock()
    connection.wait_closed = AsyncMock()
    
    # Mock a successful command result
    result = MagicMock()
    result.exit_status = 0
    result.stdout = "Command output"
    result.stderr = ""
    connection.run.return_value = result
    
    return connection


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
    """Create an SSH client with the mock asyncssh."""
    client = UnraidSSHClient(
        host="192.168.1.10",
        username="root",
        password="password",
        port=22
    )
    return client


class TestSSHConnection:
    """Test SSH connection functionality."""

    @pytest.mark.asyncio
    async def test_connect(self, ssh_client, mock_asyncssh):
        """Test connecting to the server."""
        # Test connection
        await ssh_client.connect()
        
        # Verify asyncssh.connect was called with the correct parameters
        mock_asyncssh.connect.assert_called_once_with(
            host="192.168.1.10",
            port=22,
            username="root",
            password="password",
            known_hosts=None
        )
        
        # Verify client is connected
        assert ssh_client.is_connected

    @pytest.mark.asyncio
    async def test_connection_timeout(self, ssh_client, mock_asyncssh):
        """Test handling of connection timeout."""
        # Make connect raise a timeout error
        mock_asyncssh.connect.side_effect = asyncio.TimeoutError("Connection timeout")
        
        # Attempt to connect
        with pytest.raises(asyncio.TimeoutError):
            await ssh_client.connect()
        
        # Verify client is not connected
        assert not ssh_client.is_connected

    @pytest.mark.asyncio
    async def test_connection_error(self, ssh_client, mock_asyncssh):
        """Test handling of connection error."""
        # Make connect raise an error
        error = mock_asyncssh.Error("Connection failed")
        mock_asyncssh.connect.side_effect = error
        
        # Attempt to connect
        with pytest.raises(Exception) as excinfo:
            await ssh_client.connect()
        
        # Verify client is not connected
        assert not ssh_client.is_connected
        assert str(excinfo.value) == "Connection failed"

    @pytest.mark.asyncio
    async def test_disconnect(self, ssh_client, mock_asyncssh):
        """Test disconnecting from the server."""
        # First connect
        await ssh_client.connect()
        
        # Now disconnect
        await ssh_client.disconnect()
        
        # Verify the connection was closed
        mock_connection = mock_asyncssh.connect.return_value
        mock_connection.close.assert_called_once()
        mock_connection.wait_closed.assert_called_once()
        
        # Verify client is disconnected
        assert not ssh_client.is_connected

    @pytest.mark.asyncio
    async def test_run_command(self, ssh_client, mock_asyncssh):
        """Test running a command."""
        # First connect
        await ssh_client.connect()
        
        # Run a command
        result = await ssh_client.run_command("ls -la")
        
        # Verify the command was run
        mock_connection = mock_asyncssh.connect.return_value
        mock_connection.run.assert_called_once_with("ls -la", timeout=60)
        
        # Verify result is as expected
        assert result.stdout == "Command output"
        assert result.exit_status == 0

    @pytest.mark.asyncio
    async def test_run_command_with_timeout(self, ssh_client, mock_asyncssh):
        """Test running a command with a custom timeout."""
        # First connect
        await ssh_client.connect()
        
        # Run a command with a custom timeout
        await ssh_client.run_command("sleep 10", timeout=30)
        
        # Verify the command was run with the correct timeout
        mock_connection = mock_asyncssh.connect.return_value
        mock_connection.run.assert_called_once_with("sleep 10", timeout=30)

    @pytest.mark.asyncio
    async def test_run_command_timeout(self, ssh_client, mock_asyncssh):
        """Test handling of command timeout."""
        # First connect
        await ssh_client.connect()
        
        # Make run raise a timeout error
        mock_connection = mock_asyncssh.connect.return_value
        mock_connection.run.side_effect = asyncio.TimeoutError("Command timeout")
        
        # Attempt to run a command
        with pytest.raises(asyncio.TimeoutError):
            await ssh_client.run_command("sleep 100")

    @pytest.mark.asyncio
    async def test_run_command_error(self, ssh_client, mock_asyncssh):
        """Test handling of command error."""
        # First connect
        await ssh_client.connect()
        
        # Make run raise an error
        mock_connection = mock_asyncssh.connect.return_value
        error = mock_asyncssh.Error("Command failed")
        mock_connection.run.side_effect = error
        
        # Attempt to run a command
        with pytest.raises(Exception) as excinfo:
            await ssh_client.run_command("invalid-command")
        
        assert str(excinfo.value) == "Command failed"

    @pytest.mark.asyncio
    async def test_run_command_not_connected(self, ssh_client):
        """Test running a command when not connected."""
        # Attempt to run a command without connecting first
        with pytest.raises(RuntimeError) as excinfo:
            await ssh_client.run_command("ls -la")
        
        assert "Not connected" in str(excinfo.value)


class TestBatchCommands:
    """Test batch command execution."""

    @pytest.mark.asyncio
    async def test_batch_command_execution(self, ssh_client, mock_asyncssh):
        """Test executing multiple commands in batch."""
        # First connect
        await ssh_client.connect()
        
        # Setup mock connection and results
        mock_connection = mock_asyncssh.connect.return_value
        
        result1 = MagicMock()
        result1.exit_status = 0
        result1.stdout = "Result 1"
        
        result2 = MagicMock()
        result2.exit_status = 0
        result2.stdout = "Result 2"
        
        result3 = MagicMock()
        result3.exit_status = 0
        result3.stdout = "Result 3"
        
        # Set up the run method to return different results for different commands
        async def mock_run(command, timeout=60):
            if command == "command1":
                return result1
            elif command == "command2":
                return result2
            elif command == "command3":
                return result3
            return None
        
        mock_connection.run.side_effect = mock_run
        
        # Run batch commands
        commands = ["command1", "command2", "command3"]
        results = await asyncio.gather(*[ssh_client.run_command(cmd) for cmd in commands])
        
        # Verify all commands were run
        assert mock_connection.run.call_count == 3
        mock_connection.run.assert_has_calls([
            call("command1", timeout=60),
            call("command2", timeout=60),
            call("command3", timeout=60)
        ])
        
        # Verify all results are as expected
        assert results[0].stdout == "Result 1"
        assert results[1].stdout == "Result 2"
        assert results[2].stdout == "Result 3"

    @pytest.mark.asyncio
    async def test_batch_command_with_error(self, ssh_client, mock_asyncssh):
        """Test batch command execution with one command failing."""
        # First connect
        await ssh_client.connect()
        
        # Setup mock connection and results
        mock_connection = mock_asyncssh.connect.return_value
        
        result1 = MagicMock()
        result1.exit_status = 0
        result1.stdout = "Result 1"
        
        # Second command will fail
        result2 = MagicMock()
        result2.exit_status = 1
        result2.stdout = ""
        result2.stderr = "Command 2 failed"
        
        result3 = MagicMock()
        result3.exit_status = 0
        result3.stdout = "Result 3"
        
        # Set up the run method to return different results for different commands
        async def mock_run(command, timeout=60):
            if command == "command1":
                return result1
            elif command == "command2":
                return result2
            elif command == "command3":
                return result3
            return None
        
        mock_connection.run.side_effect = mock_run
        
        # Run batch commands
        commands = ["command1", "command2", "command3"]
        results = await asyncio.gather(*[ssh_client.run_command(cmd) for cmd in commands])
        
        # Verify all commands were run
        assert mock_connection.run.call_count == 3
        
        # Verify all results are as expected
        assert results[0].stdout == "Result 1"
        assert results[1].exit_status == 1
        assert results[1].stderr == "Command 2 failed"
        assert results[2].stdout == "Result 3"


class TestConnectionPooling:
    """Test SSH connection pooling."""

    @pytest.mark.asyncio
    async def test_connection_reuse(self, ssh_client, mock_asyncssh):
        """Test that the SSH connection is reused for multiple commands."""
        # First connect
        await ssh_client.connect()
        
        # Run multiple commands
        await ssh_client.run_command("command1")
        await ssh_client.run_command("command2")
        await ssh_client.run_command("command3")
        
        # Verify connect was only called once
        assert mock_asyncssh.connect.call_count == 1
        
        # Verify the same connection was used for all commands
        mock_connection = mock_asyncssh.connect.return_value
        assert mock_connection.run.call_count == 3

    @pytest.mark.asyncio
    async def test_reconnect_after_disconnect(self, ssh_client, mock_asyncssh):
        """Test reconnecting after disconnecting."""
        # First connect
        await ssh_client.connect()
        
        # Run a command
        await ssh_client.run_command("command1")
        
        # Disconnect
        await ssh_client.disconnect()
        
        # Verify not connected
        assert not ssh_client.is_connected
        
        # Connect again
        await ssh_client.connect()
        
        # Verify connected
        assert ssh_client.is_connected
        
        # Run another command
        await ssh_client.run_command("command2")
        
        # Verify connect was called twice
        assert mock_asyncssh.connect.call_count == 2

    @pytest.mark.asyncio
    async def test_auto_reconnect(self, ssh_client, mock_asyncssh):
        """Test automatic reconnection when connection is lost."""
        # First connect
        await ssh_client.connect()
        
        # Run a command
        await ssh_client.run_command("command1")
        
        # Simulate connection lost
        mock_connection = mock_asyncssh.connect.return_value
        
        # Create a property mock for is_connected
        type(mock_connection).is_connected = PropertyMock(return_value=False)
        
        # Run another command (should trigger reconnect)
        await ssh_client.run_command("command2")
        
        # Verify connect was called twice
        assert mock_asyncssh.connect.call_count == 2

    @pytest.mark.asyncio
    async def test_connection_error_recovery(self, ssh_client, mock_asyncssh):
        """Test recovery from connection errors."""
        # First connect
        await ssh_client.connect()
        
        # Run a command
        await ssh_client.run_command("command1")
        
        # Make the next run command fail with a connection error
        mock_connection = mock_asyncssh.connect.return_value
        mock_connection.run.side_effect = mock_asyncssh.Error("Connection lost")
        
        # Set up a new mock connection for reconnect
        new_connection = AsyncMock()
        new_connection.is_connected = True
        
        new_result = MagicMock()
        new_result.exit_status = 0
        new_result.stdout = "New connection result"
        new_connection.run.return_value = new_result
        
        # Make the second connect call return the new connection
        mock_asyncssh.connect.return_value = new_connection
        
        # Run another command (should handle error and reconnect)
        with pytest.raises(Exception):
            await ssh_client.run_command("command2")
            
        # The client should mark itself as disconnected
        assert not ssh_client.is_connected
        
        # Now explicitly reconnect
        await ssh_client.connect()
        
        # Run a command on the new connection
        result = await ssh_client.run_command("command3")
        
        # Verify the second connection was used
        assert result.stdout == "New connection result"
        assert mock_asyncssh.connect.call_count == 2 