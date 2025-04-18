"""Unit tests for command cancellation in the Unraid integration."""
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call, PropertyMock

from custom_components.unraid.api.ssh_client import UnraidSSHClient


@pytest.fixture
def mock_ssh_connection():
    """Create a mock SSH connection."""
    mock_connection = AsyncMock()
    mock_connection.is_connected = True
    mock_connection.run = AsyncMock()
    mock_connection.close = AsyncMock()
    mock_connection.wait_closed = AsyncMock()
    
    return mock_connection


@pytest.fixture
def mock_asyncssh(mock_ssh_connection):
    """Create a mock asyncssh module."""
    with patch("custom_components.unraid.api.ssh_client.asyncssh") as mock_asyncssh:
        # Make the connect method return the mock connection
        mock_asyncssh.connect = AsyncMock(return_value=mock_ssh_connection)
        
        # Create a mock result with success status
        result = MagicMock()
        result.exit_status = 0
        result.stdout = "Command output"
        result.stderr = ""
        mock_ssh_connection.run.return_value = result
        
        yield mock_asyncssh


@pytest.fixture
def ssh_client(mock_asyncssh):
    """Create an SSH client for testing."""
    client = UnraidSSHClient(
        host="192.168.1.10",
        username="root",
        password="password",
        port=22
    )
    return client


class TestCommandCancellation:
    """Test cancellation of long-running commands."""
    
    @pytest.mark.asyncio
    async def test_command_cancellation(self, ssh_client, mock_ssh_connection):
        """Test cancellation of a long-running command."""
        # Connect to the server
        await ssh_client.connect()
        
        # Configure the run method to take a long time to complete
        async def slow_run(*args, **kwargs):
            # Wait for a long time, simulating a slow command
            await asyncio.sleep(10)
            
            # We'd normally return a result here, but the task will be cancelled
            # before this is reached
            mock_result = MagicMock()
            mock_result.exit_status = 0
            mock_result.stdout = "Command completed"
            return mock_result
        
        # Replace the run method with our slow implementation
        mock_ssh_connection.run = AsyncMock(side_effect=slow_run)
        
        # Start a long-running command in a separate task
        task = asyncio.create_task(ssh_client.run_command("long-running-command"))
        
        # Wait a short time to ensure the task has started
        await asyncio.sleep(0.1)
        
        # Cancel the task
        task.cancel()
        
        # Verify the task was cancelled
        with pytest.raises(asyncio.CancelledError):
            await task
    
    @pytest.mark.asyncio
    async def test_timeout_cancellation(self, ssh_client, mock_ssh_connection):
        """Test that commands are automatically cancelled when they time out."""
        # Connect to the server
        await ssh_client.connect()
        
        # Configure the run method to take longer than the timeout
        async def slow_run(*args, **kwargs):
            await asyncio.sleep(5)  # Longer than our timeout
            
            mock_result = MagicMock()
            mock_result.exit_status = 0
            mock_result.stdout = "Command completed"
            return mock_result
        
        # Replace the run method with our slow implementation
        mock_ssh_connection.run = AsyncMock(side_effect=slow_run)
        
        # Run command with a short timeout
        with pytest.raises(asyncio.TimeoutError):
            await ssh_client.run_command("long-running-command", timeout=0.1)
    
    @pytest.mark.asyncio
    async def test_command_graceful_cancellation(self, ssh_client, mock_ssh_connection):
        """Test graceful cancellation of a command with cleanup."""
        # Connect to the server
        await ssh_client.connect()
        
        # Flag to track if cleanup was called
        cleanup_called = False
        
        # Configure the run method to take a long time and track cleanup
        async def slow_run_with_cleanup(*args, **kwargs):
            nonlocal cleanup_called
            try:
                await asyncio.sleep(10)
                
                mock_result = MagicMock()
                mock_result.exit_status = 0
                mock_result.stdout = "Command completed"
                return mock_result
            except asyncio.CancelledError:
                # Do cleanup tasks before re-raising
                cleanup_called = True
                raise
        
        # Replace the run method with our implementation
        mock_ssh_connection.run = AsyncMock(side_effect=slow_run_with_cleanup)
        
        # Start a long-running command in a separate task
        task = asyncio.create_task(ssh_client.run_command("long-running-command"))
        
        # Wait a short time to ensure the task has started
        await asyncio.sleep(0.1)
        
        # Cancel the task
        task.cancel()
        
        # Verify the task was cancelled
        with pytest.raises(asyncio.CancelledError):
            await task
        
        # Verify cleanup was called
        assert cleanup_called is True
    
    @pytest.mark.asyncio
    async def test_multiple_command_cancellation(self, ssh_client, mock_ssh_connection):
        """Test cancellation of multiple commands running in parallel."""
        # Connect to the server
        await ssh_client.connect()
        
        # Command counter to track which commands have been run
        command_counter = 0
        
        # Configure the run method to increment the counter and wait
        async def slow_run(*args, **kwargs):
            nonlocal command_counter
            command_number = command_counter
            command_counter += 1
            
            # Wait, simulating a slow command
            try:
                await asyncio.sleep(10)
                
                mock_result = MagicMock()
                mock_result.exit_status = 0
                mock_result.stdout = f"Command {command_number} completed"
                return mock_result
            except asyncio.CancelledError:
                print(f"Command {command_number} was cancelled")
                raise
        
        # Replace the run method with our implementation
        mock_ssh_connection.run = AsyncMock(side_effect=slow_run)
        
        # Start multiple commands in separate tasks
        tasks = [
            asyncio.create_task(ssh_client.run_command(f"command-{i}"))
            for i in range(3)
        ]
        
        # Wait a short time to ensure the tasks have started
        await asyncio.sleep(0.1)
        
        # Cancel all tasks
        for task in tasks:
            task.cancel()
        
        # Verify all tasks were cancelled
        for task in tasks:
            with pytest.raises(asyncio.CancelledError):
                await task
        
        # Verify the command counter was incremented for each command
        assert command_counter == 3
    
    @pytest.mark.asyncio
    async def test_context_manager_cancellation(self, mock_asyncssh):
        """Test command cancellation when used with context manager."""
        # Create a client using a context manager
        client = UnraidSSHClient(
            host="192.168.1.10",
            username="root",
            password="password",
            port=22
        )
        
        # Configure the run method to take a long time
        mock_connection = mock_asyncssh.connect.return_value
        
        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            
            mock_result = MagicMock()
            mock_result.exit_status = 0
            mock_result.stdout = "Command completed"
            return mock_result
        
        mock_connection.run = AsyncMock(side_effect=slow_run)
        
        # Use the client in a context manager with a timeout
        async with asyncio.timeout(0.5):
            try:
                async with client:
                    # This should timeout and the context manager should be exited
                    await client.run_command("long-running-command")
            except asyncio.TimeoutError:
                # Expected exception
                pass
        
        # Verify the client was disconnected
        assert client._connected is False
        assert mock_connection.close.called 