"""User script operations for Unraid."""
from __future__ import annotations

import logging
from typing import Dict, List, Any
import asyncio
import asyncssh

_LOGGER = logging.getLogger(__name__)

class UserScriptOperationsMixin:
    """Mixin for user script related operations."""

    async def get_user_scripts(self) -> List[Dict[str, Any]]:
        """Fetch information about user scripts."""
        try:
            _LOGGER.debug("Fetching user scripts")
            # Check if user scripts plugin is installed first
            check_result = await self.execute_command(
                "[ -d /boot/config/plugins/user.scripts/scripts ] && echo 'exists'"
            )

            if check_result.exit_status == 0 and "exists" in check_result.stdout:
                result = await self.execute_command(
                    "ls -1 /boot/config/plugins/user.scripts/scripts 2>/dev/null"
                )
                if result.exit_status == 0:
                    return [{"name": script.strip()} for script in result.stdout.splitlines()]

            # If not installed or no scripts, return empty list without error
            return []
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.debug("Error getting user scripts (plugin might not be installed): %s", str(e))
            return []

    async def execute_user_script(self, script_name: str, background: bool = False) -> str:
        """Execute a user script."""
        try:
            _LOGGER.debug("Executing user script: %s", script_name)
            command = f"/usr/local/emhttp/plugins/user.scripts/scripts/{script_name}"
            if background:
                command += " & > /dev/null 2>&1"
            result = await self.execute_command(command)
            if result.exit_status != 0:
                _LOGGER.error("User script %s failed with exit status %d", script_name, result.exit_status)
                return ""
            return result.stdout
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error executing user script %s: %s", script_name, str(e))
            return ""

    async def stop_user_script(self, script_name: str) -> str:
        """Stop a user script."""
        try:
            _LOGGER.debug("Stopping user script: %s", script_name)
            result = await self.execute_command(f"pkill -f '{script_name}'")
            if result.exit_status != 0:
                _LOGGER.error("Stopping user script %s failed with exit status %d", script_name, result.exit_status)
                return ""
            return result.stdout
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error stopping user script %s: %s", script_name, str(e))
            return ""