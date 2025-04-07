"""User script operations for Unraid."""
from __future__ import annotations

import logging
from typing import Dict, List, Any
import asyncio
import asyncssh # type: ignore

_LOGGER = logging.getLogger(__name__)

class UserScriptOperationsMixin:
    """Mixin for user script related operations."""

    async def get_user_scripts(self) -> List[Dict[str, Any]]:
        """Fetch information about user scripts using a batched command."""
        try:
            _LOGGER.debug("Fetching user scripts with batched command")
            # Use a single command to check if plugin is installed and get script information
            cmd = (
                "if [ -d /boot/config/plugins/user.scripts/scripts ]; then "
                "  for script in $(ls -1 /boot/config/plugins/user.scripts/scripts 2>/dev/null); do "
                "    name=$(cat /boot/config/plugins/user.scripts/scripts/$script/name 2>/dev/null || echo $script); "
                "    desc=$(cat /boot/config/plugins/user.scripts/scripts/$script/description 2>/dev/null || echo ''); "
                "    echo \"$script|$name|$desc\"; "
                "  done; "
                "else "
                "  echo 'not_installed'; "
                "fi"
            )

            result = await self.execute_command(cmd)

            if result.exit_status != 0 or result.stdout.strip() == 'not_installed':
                _LOGGER.debug("User scripts plugin not installed")
                return []

            scripts = []
            for line in result.stdout.splitlines():
                if not line.strip() or '|' not in line:
                    continue

                try:
                    parts = line.split('|')
                    if len(parts) >= 3:
                        script_id = parts[0].strip()
                        name = parts[1].strip()
                        description = parts[2].strip()

                        scripts.append({
                            "id": script_id,
                            "name": name,
                            "description": description
                        })
                except Exception as err:
                    _LOGGER.warning("Error parsing user script line '%s': %s", line, err)

            return scripts

        except Exception as err:
            _LOGGER.debug("Error getting user scripts (plugin might not be installed): %s", str(err))
            # Fallback to original implementation
            try:
                return await self._get_user_scripts_original()
            except Exception as fallback_err:
                _LOGGER.error("Fallback user scripts method also failed: %s", fallback_err)
                return []

    async def _get_user_scripts_original(self) -> List[Dict[str, Any]]:
        """Original implementation of user scripts collection as fallback."""
        try:
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
        except Exception as err:
            _LOGGER.debug("Error in original user scripts method: %s", str(err))
            return []

    async def execute_user_script(self, script_name: str, background: bool = False) -> str:
        """Execute a user script."""
        try:
            _LOGGER.debug("Executing user script: %s", script_name)

            # Build proper script paths
            script_dir = f"/boot/config/plugins/user.scripts/scripts/{script_name}"
            script_path = f"{script_dir}/script"

            # Check if script exists first
            check_result = await self.execute_command(f'test -f "{script_path}" && echo "exists"')
            if check_result.exit_status != 0 or "exists" not in check_result.stdout:
                _LOGGER.error("Script %s not found at %s", script_name, script_path)
                return ""

            # First try direct execution
            try:
                _LOGGER.debug("Attempting direct script execution: %s", script_path)
                result = await self.execute_command(f'bash "{script_path}"')
                if result.exit_status == 0:
                    return result.stdout
            except Exception as err:
                _LOGGER.debug("Direct execution failed, trying PHP conversion: %s", err)

            # If direct execution fails, try PHP conversion
            php_cmd = (
                f'php -r \'$_POST["action"]="convertScript"; '
                f'$_POST["path"]="{script_path}"; '
                f'include("/usr/local/emhttp/plugins/user.scripts/exec.php");\''
            )

            _LOGGER.debug("Running PHP convert command: %s", php_cmd)
            convert_result = await self.execute_command(php_cmd)

            if convert_result.exit_status != 0:
                _LOGGER.error(
                    "Failed to convert script %s: %s",
                    script_name,
                    convert_result.stderr or convert_result.stdout
                )
                return ""

            _LOGGER.debug("Script conversion output: %s", convert_result.stdout)

            # Execute the script
            if background:
                result = await self.execute_command(f'nohup "{script_path}" > /dev/null 2>&1 &')
            else:
                result = await self.execute_command(f'bash "{script_path}"')

            if result.exit_status != 0:
                _LOGGER.error(
                    "Script %s failed with exit status %d: %s",
                    script_name,
                    result.exit_status,
                    result.stderr or result.stdout
                )
                return ""

            return result.stdout

        except Exception as e:
            _LOGGER.error("Error executing user script %s: %s", script_name, str(e))
            return ""

    async def stop_user_script(self, script_name: str) -> str:
        """Stop a user script."""
        try:
            _LOGGER.debug("Stopping user script: %s", script_name)
            result = await self.execute_command(f"pkill -f '{script_name}'")
            if result.exit_status != 0:
                _LOGGER.error(
                    "Stopping user script %s failed with exit status %d",
                    script_name,
                    result.exit_status
                )
                return ""
            return result.stdout
        except (asyncssh.Error, asyncio.TimeoutError, OSError, ValueError) as e:
            _LOGGER.error("Error stopping user script %s: %s", script_name, str(e))
            return ""