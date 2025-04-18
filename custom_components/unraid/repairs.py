"""Repair flows for Unraid integration.

This module provides repair flows for common issues with the Unraid integration.
It includes:
- Connection issue detection and repair
- Authentication issue detection and repair
- Disk health issue detection and notification
- Array problem detection and notification
- Parity check failure detection and notification

These repair flows help users identify and fix issues with their Unraid server
connection and hardware, improving the overall reliability and user experience.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Set, Final

try:
    from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow # type: ignore
except ImportError:
    # Define fallback classes if repairs component is not available
    from homeassistant.data_entry_flow import FlowHandler # type: ignore

    class RepairsFlow(FlowHandler):
        """Fallback class for RepairsFlow."""

        async def async_step_init(self, _=None):
            """Handle the first step of the flow."""
            return await self.async_step_confirm()

        async def async_step_confirm(self, user_input=None):
            """Handle the confirm step of the flow."""
            if user_input is not None:
                return self.async_create_entry(title="", data={})

            return self.async_show_form(step_id="confirm")

    class ConfirmRepairFlow(RepairsFlow):
        """Fallback class for ConfirmRepairFlow."""

        async def async_confirm_fix(self):
            """Confirm the fix."""
            pass
from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.data_entry_flow import FlowResult # type: ignore
# from homeassistant.config_entries import ConfigEntry # type: ignore
# from homeassistant.exceptions import HomeAssistantError # type: ignore
from homeassistant.helpers import issue_registry as ir # type: ignore
# from homeassistant.helpers.selector import ( # type: ignore
#     TextSelector,
#     TextSelectorConfig,
#     TextSelectorType,
# )

from .const import DOMAIN
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Issue IDs
ISSUE_CONNECTION_FAILED: Final = "connection_failed"
ISSUE_AUTHENTICATION_FAILED: Final = "authentication_failed"
ISSUE_DISK_HEALTH: Final = "disk_health"
ISSUE_ARRAY_PROBLEM: Final = "array_problem"
ISSUE_MISSING_DEPENDENCY: Final = "missing_dependency"
ISSUE_PARITY_CHECK_FAILED: Final = "parity_check_failed"

# Issue domains
DOMAIN_CONFIG_ENTRY: Final = "config_entry"
DOMAIN_SYSTEM: Final = "system"
DOMAIN_STORAGE: Final = "storage"
DOMAIN_MAINTENANCE: Final = "maintenance"

# Issue severities
SEVERITY_CRITICAL: Final = "critical"
SEVERITY_WARNING: Final = "warning"
SEVERITY_INFO: Final = "info"


class UnraidRepairManager:
    """Manager for Unraid repair issues."""

    def __init__(self, hass: HomeAssistant, coordinator: UnraidDataUpdateCoordinator) -> None:
        """Initialize the repair manager."""
        self.hass = hass
        self.coordinator = coordinator
        self.hostname = coordinator.hostname
        self.entry_id = coordinator.entry.entry_id
        self._active_issues: Set[str] = set()
        self._disk_health_issues: Dict[str, Dict[str, Any]] = {}
        self._array_issues: Dict[str, Dict[str, Any]] = {}
        self._connection_issues: Dict[str, Dict[str, Any]] = {}
        self._parity_issues: Dict[str, Dict[str, Any]] = {}

    async def async_check_for_issues(self) -> None:
        """Check for issues that need repair."""
        # Skip if coordinator is not initialized or has no data
        if not self.coordinator or not self.coordinator.data:
            return

        # Check for connection issues
        await self._check_connection_issues()

        # Check for disk health issues
        await self._check_disk_health_issues()

        # Check for array issues
        await self._check_array_issues()

        # Check for parity issues
        await self._check_parity_issues()

    async def _check_connection_issues(self) -> None:
        """Check for connection issues."""
        # Check if the coordinator has failed updates
        if self.coordinator.last_update_success:
            # Connection is working, clear any connection issues
            self._clear_issue(f"{ISSUE_CONNECTION_FAILED}_{self.entry_id}")
            self._clear_issue(f"{ISSUE_AUTHENTICATION_FAILED}_{self.entry_id}")
            return

        # Check if the error is an authentication issue
        if hasattr(self.coordinator, "last_exception"):
            last_error = self.coordinator.last_exception
            if last_error and "Authentication" in str(last_error):
                # Create authentication issue
                self._create_issue(
                    issue_id=f"{ISSUE_AUTHENTICATION_FAILED}_{self.entry_id}",
                    domain=DOMAIN_CONFIG_ENTRY,
                    issue_domain=DOMAIN,
                    translation_key=ISSUE_AUTHENTICATION_FAILED,
                    severity=SEVERITY_CRITICAL,
                    data={
                        "entry_id": self.entry_id,
                        "hostname": self.hostname,
                        "error": str(last_error),
                    },
                )
                return

        # Create general connection issue
        self._create_issue(
            issue_id=f"{ISSUE_CONNECTION_FAILED}_{self.entry_id}",
            domain=DOMAIN_CONFIG_ENTRY,
            issue_domain=DOMAIN,
            translation_key=ISSUE_CONNECTION_FAILED,
            severity=SEVERITY_CRITICAL,
            data={
                "entry_id": self.entry_id,
                "hostname": self.hostname,
                "error": str(getattr(self.coordinator, "last_exception", "Unknown error")),
            },
        )

    async def _check_disk_health_issues(self) -> None:
        """Check for disk health issues."""
        # Skip if no data available
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return

        system_stats = self.coordinator.data.get("system_stats", {})
        individual_disks = system_stats.get("individual_disks", [])

        # Track current issues to clean up resolved ones
        current_issues = set()

        for disk in individual_disks:
            disk_name = disk.get("name", "unknown")
            smart_status = disk.get("smart_status", "")
            temperature = disk.get("temperature", 0)

            # Check for actual disk problems instead of just SMART status
            # Get the disk's smart_data if available
            smart_data = disk.get("smart_data", {})
            has_problem = False
            problem_details = {}

            # Check for critical SMART attributes
            if smart_data and "ata_smart_attributes" in smart_data:
                for attr in smart_data.get("ata_smart_attributes", {}).get("table", []):
                    name = attr.get("name")
                    if not name:
                        continue

                    # Skip Command_Timeout and UDMA_CRC_Error_Count attributes
                    # These often have high raw values but are not indicative of actual problems
                    # as long as the normalized values are above threshold
                    if name in ["Command_Timeout", "UDMA_CRC_Error_Count"]:
                        continue

                    # Check if this attribute has failed according to SMART
                    when_failed = attr.get("when_failed", "")
                    if when_failed and when_failed != "-":
                        has_problem = True
                        problem_details[name.lower()] = "failed"

                    # Check if normalized value is below threshold
                    normalized_value = attr.get("value", 100)  # Default to 100 (good)
                    threshold_value = attr.get("thresh", 0)    # Default to 0 (minimum threshold)
                    if normalized_value < threshold_value:
                        has_problem = True
                        problem_details[name.lower()] = f"{normalized_value} < {threshold_value}"

            # Only create issue if there are actual problems
            # For SMART status, only consider it a problem if it's explicitly failed
            # Many disks report "Unknown" or other statuses that aren't actual problems
            smart_status_problem = smart_status and smart_status.lower() == "failed"

            if has_problem or smart_status_problem:
                issue_id = f"{ISSUE_DISK_HEALTH}_{self.entry_id}_{disk_name}_smart"
                current_issues.add(issue_id)
                self._create_issue(
                    issue_id=issue_id,
                    domain=DOMAIN_STORAGE,
                    issue_domain=DOMAIN,
                    translation_key=ISSUE_DISK_HEALTH,
                    severity=SEVERITY_WARNING,
                    data={
                        "entry_id": self.entry_id,
                        "hostname": self.hostname,
                        "disk_name": disk_name,
                        "issue_type": "smart",
                        "smart_status": smart_status,
                        "problem_details": problem_details,
                    },
                )

            # Check for temperature issues (over 60°C is concerning)
            if temperature and temperature > 60:
                issue_id = f"{ISSUE_DISK_HEALTH}_{self.entry_id}_{disk_name}_temp"
                current_issues.add(issue_id)
                self._create_issue(
                    issue_id=issue_id,
                    domain=DOMAIN_STORAGE,
                    issue_domain=DOMAIN,
                    translation_key=ISSUE_DISK_HEALTH,
                    severity=SEVERITY_WARNING if temperature < 70 else SEVERITY_CRITICAL,
                    data={
                        "entry_id": self.entry_id,
                        "hostname": self.hostname,
                        "disk_name": disk_name,
                        "issue_type": "temperature",
                        "temperature": temperature,
                    },
                )

        # Clean up resolved issues
        for issue_id in list(self._disk_health_issues.keys()):
            if issue_id not in current_issues:
                self._clear_issue(issue_id)

    async def _check_array_issues(self) -> None:
        """Check for array issues."""
        # Skip if no data available
        if not self.coordinator.data or "system_stats" not in self.coordinator.data:
            return

        system_stats = self.coordinator.data.get("system_stats", {})
        array_usage = system_stats.get("array_usage", {})
        array_status = array_usage.get("status", "").lower()

        # Track current issues to clean up resolved ones
        current_issues = set()

        # Check array status
        # Valid statuses include normal, active, started, syncing_* (case insensitive)
        if array_status and not (array_status in ["normal", "active", "started"] or array_status.startswith("syncing_")):
            issue_id = f"{ISSUE_ARRAY_PROBLEM}_{self.entry_id}_status"
            current_issues.add(issue_id)
            self._create_issue(
                issue_id=issue_id,
                domain=DOMAIN_STORAGE,
                issue_domain=DOMAIN,
                translation_key=ISSUE_ARRAY_PROBLEM,
                severity=SEVERITY_CRITICAL,
                data={
                    "entry_id": self.entry_id,
                    "hostname": self.hostname,
                    "issue_type": "status",
                    "array_status": array_status,
                },
            )

        # Check array usage (over 90% is concerning)
        array_percentage = array_usage.get("percentage", 0)
        if array_percentage and array_percentage > 90:
            issue_id = f"{ISSUE_ARRAY_PROBLEM}_{self.entry_id}_space"
            current_issues.add(issue_id)
            self._create_issue(
                issue_id=issue_id,
                domain=DOMAIN_STORAGE,
                issue_domain=DOMAIN,
                translation_key=ISSUE_ARRAY_PROBLEM,
                severity=SEVERITY_WARNING,
                data={
                    "entry_id": self.entry_id,
                    "hostname": self.hostname,
                    "issue_type": "space",
                    "array_percentage": array_percentage,
                },
            )

        # Clean up resolved issues
        for issue_id in list(self._array_issues.keys()):
            if issue_id not in current_issues:
                self._clear_issue(issue_id)

    async def _check_parity_issues(self) -> None:
        """Check for parity check issues."""
        # Skip if no data available
        if not self.coordinator.data or "parity_info" not in self.coordinator.data:
            return

        parity_info = self.coordinator.data.get("parity_info", {})
        last_status = parity_info.get("last_status", "").lower()
        errors = parity_info.get("errors", 0)

        # Track current issues to clean up resolved ones
        current_issues = set()

        # Check for parity check errors
        if last_status and last_status != "success" and last_status != "completed":
            issue_id = f"{ISSUE_PARITY_CHECK_FAILED}_{self.entry_id}_status"
            current_issues.add(issue_id)
            self._create_issue(
                issue_id=issue_id,
                domain=DOMAIN_MAINTENANCE,
                issue_domain=DOMAIN,
                translation_key=ISSUE_PARITY_CHECK_FAILED,
                severity=SEVERITY_WARNING,
                data={
                    "entry_id": self.entry_id,
                    "hostname": self.hostname,
                    "issue_type": "status",
                    "parity_status": last_status,
                },
            )

        # Check for parity errors
        if errors and errors > 0:
            issue_id = f"{ISSUE_PARITY_CHECK_FAILED}_{self.entry_id}_errors"
            current_issues.add(issue_id)
            self._create_issue(
                issue_id=issue_id,
                domain=DOMAIN_MAINTENANCE,
                issue_domain=DOMAIN,
                translation_key=ISSUE_PARITY_CHECK_FAILED,
                severity=SEVERITY_WARNING if errors < 10 else SEVERITY_CRITICAL,
                data={
                    "entry_id": self.entry_id,
                    "hostname": self.hostname,
                    "issue_type": "errors",
                    "error_count": errors,
                },
            )

        # Clean up resolved issues
        for issue_id in list(self._parity_issues.keys()):
            if issue_id not in current_issues:
                self._clear_issue(issue_id)

    def _create_issue(
        self,
        issue_id: str,
        domain: str,
        issue_domain: str,
        translation_key: str,
        severity: str,
        data: Dict[str, Any],
    ) -> None:
        """Create a repair issue."""
        # Skip if issue already exists
        if issue_id in self._active_issues:
            return

        # Create the issue
        ir.async_create_issue(
            self.hass,
            issue_domain,
            issue_id,
            is_fixable=True,
            severity=severity,
            translation_key=translation_key,
            translation_placeholders={
                "hostname": self.hostname,
                **{k: str(v) for k, v in data.items()},
            },
            data={
                "domain": domain,
                **data,
            },
        )

        # Track the issue
        self._active_issues.add(issue_id)

        # Store issue data based on type
        if ISSUE_DISK_HEALTH in issue_id:
            self._disk_health_issues[issue_id] = data
        elif ISSUE_ARRAY_PROBLEM in issue_id:
            self._array_issues[issue_id] = data
        elif ISSUE_CONNECTION_FAILED in issue_id or ISSUE_AUTHENTICATION_FAILED in issue_id:
            self._connection_issues[issue_id] = data
        elif ISSUE_PARITY_CHECK_FAILED in issue_id:
            self._parity_issues[issue_id] = data

        _LOGGER.debug("Created repair issue: %s", issue_id)

    def _clear_issue(self, issue_id: str) -> None:
        """Clear a repair issue."""
        # Skip if issue doesn't exist
        if issue_id not in self._active_issues:
            return

        # Remove the issue
        ir.async_delete_issue(self.hass, DOMAIN, issue_id)

        # Remove from tracking
        self._active_issues.remove(issue_id)

        # Remove from issue data
        if issue_id in self._disk_health_issues:
            del self._disk_health_issues[issue_id]
        elif issue_id in self._array_issues:
            del self._array_issues[issue_id]
        elif issue_id in self._connection_issues:
            del self._connection_issues[issue_id]
        elif issue_id in self._parity_issues:
            del self._parity_issues[issue_id]

        _LOGGER.debug("Cleared repair issue: %s", issue_id)


class UnraidConnectionRepairFlow(RepairsFlow):
    """Handler for connection repair flow."""

    def __init__(
        self,
        issue_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Initialize the repair flow."""
        super().__init__()
        self.issue_id = issue_id
        self.data = data
        self.entry_id = data.get("entry_id")
        self.hostname = data.get("hostname")
        self.error = data.get("error", "Unknown error")

    async def async_step_init(
        self, _: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the first step of the repair flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the confirm step of the repair flow."""
        if user_input is not None:
            # User confirmed, proceed to reconfigure
            return await self.async_step_reconfigure()

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "hostname": self.hostname,
                "error": self.error,
            },
        )

    async def async_step_reconfigure(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the reconfigure step of the repair flow."""
        if user_input is not None:
            # Get the config entry
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if not entry:
                return self.async_abort(reason="config_entry_not_found")

            # Update the config entry with new data
            new_data = dict(entry.data)
            if "host" in user_input:
                new_data["host"] = user_input["host"]
            if "username" in user_input:
                new_data["username"] = user_input["username"]
            if "password" in user_input:
                new_data["password"] = user_input["password"]
            if "port" in user_input:
                new_data["port"] = user_input["port"]

            # Update the entry
            self.hass.config_entries.async_update_entry(entry, data=new_data)

            # Reload the entry
            await self.hass.config_entries.async_reload(self.entry_id)

            # Mark the issue as fixed
            return self.async_create_entry(title="", data={})

        # Show the form
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._get_reconfigure_schema(),
            description_placeholders={
                "hostname": self.hostname,
                "error": self.error,
            },
        )

    def _get_reconfigure_schema(self):
        """Get the schema for the reconfigure step."""
        # from homeassistant.helpers import config_validation as cv # type: ignore
        import voluptuous as vol # type: ignore

        # Get the config entry
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if not entry:
            return vol.Schema({})

        # Create schema based on issue type
        if ISSUE_AUTHENTICATION_FAILED in self.issue_id:
            # Authentication issue - show username and password fields
            return vol.Schema({
                vol.Required("username", default=entry.data.get("username", "")): str,
                vol.Required("password"): str,
            })
        else:
            # Connection issue - show host and port fields
            return vol.Schema({
                vol.Required("host", default=entry.data.get("host", "")): str,
                vol.Optional("port", default=entry.data.get("port", 22)): int,
            })


class UnraidDiskHealthRepairFlow(ConfirmRepairFlow):
    """Handler for disk health repair flow."""

    def __init__(
        self,
        issue_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Initialize the repair flow."""
        super().__init__()
        self.issue_id = issue_id
        self.data = data
        self.entry_id = data.get("entry_id")
        self.hostname = data.get("hostname")
        self.disk_name = data.get("disk_name", "unknown")
        self.issue_type = data.get("issue_type", "unknown")
        self.smart_status = data.get("smart_status", "unknown")
        self.temperature = data.get("temperature", 0)

    async def async_confirm_fix(self) -> None:
        """Confirm the fix."""
        # This is a notification-only issue, so we just mark it as fixed
        # The issue will be recreated if the problem persists
        pass


class UnraidArrayProblemRepairFlow(ConfirmRepairFlow):
    """Handler for array problem repair flow."""

    def __init__(
        self,
        issue_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Initialize the repair flow."""
        super().__init__()
        self.issue_id = issue_id
        self.data = data
        self.entry_id = data.get("entry_id")
        self.hostname = data.get("hostname")
        self.issue_type = data.get("issue_type", "unknown")
        self.array_status = data.get("array_status", "unknown")
        self.array_percentage = data.get("array_percentage", 0)

    async def async_confirm_fix(self) -> None:
        """Confirm the fix."""
        # This is a notification-only issue, so we just mark it as fixed
        # The issue will be recreated if the problem persists
        pass


class UnraidParityCheckFailedRepairFlow(ConfirmRepairFlow):
    """Handler for parity check failed repair flow."""

    def __init__(
        self,
        issue_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Initialize the repair flow."""
        super().__init__()
        self.issue_id = issue_id
        self.data = data
        self.entry_id = data.get("entry_id")
        self.hostname = data.get("hostname")
        self.issue_type = data.get("issue_type", "unknown")
        self.parity_status = data.get("parity_status", "unknown")
        self.error_count = data.get("error_count", 0)

    async def async_confirm_fix(self) -> None:
        """Confirm the fix."""
        # This is a notification-only issue, so we just mark it as fixed
        # The issue will be recreated if the problem persists
        pass


# This function is required by the repairs platform
async def async_create_fix_flow(
    _: HomeAssistant, issue_id: str, data: Dict[str, Any]
) -> RepairsFlow:
    """Create a repair flow for an issue."""
    if ISSUE_CONNECTION_FAILED in issue_id or ISSUE_AUTHENTICATION_FAILED in issue_id:
        return UnraidConnectionRepairFlow(issue_id, data)
    elif ISSUE_DISK_HEALTH in issue_id:
        return UnraidDiskHealthRepairFlow(issue_id, data)
    elif ISSUE_ARRAY_PROBLEM in issue_id:
        return UnraidArrayProblemRepairFlow(issue_id, data)
    elif ISSUE_PARITY_CHECK_FAILED in issue_id:
        return UnraidParityCheckFailedRepairFlow(issue_id, data)
    else:
        # Default to a confirm repair flow
        return ConfirmRepairFlow()
