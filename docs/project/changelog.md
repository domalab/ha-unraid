# Changelog

This page documents all notable changes to the Unraid Integration for Home Assistant.

## [Unreleased]

### Added
- Documentation in MkDocs with Material theme
- Added GitHub Pages site for documentation hosting

## [2024.04.15]

### Added
- Power consumption monitoring for supported UPS devices
- New UPS metrics: input voltage, power load
- Support for environment variables in user scripts

### Fixed
- Issue with executing commands containing special characters
- VM status detection improvements for all Unraid versions
- Fixed Docker container execution timeout issues

### Changed
- Increased default disk update interval for better performance
- Improved error messages for authentication failures

## [2024.03.22]

### Added
- System services: reboot, shutdown, and array stop
- Improved diagnostics information for troubleshooting
- Support for VM hibernation and force stop operations

### Fixed
- Fixed issues with disk spin-down detection
- Improved error handling for SSH connection failures
- Resolved entity duplication in some configurations

### Changed
- Enhanced configuration flow with better validation
- Improved documentation for service parameters

## [2024.02.10]

### Added
- Docker container pause and resume services
- VM pause and resume capabilities
- User script buttons (optional feature)
- Command execution with background process support

### Fixed
- Fixed issues with Docker container status reporting
- Improved error handling for unavailable services
- Better handling of special characters in entity names

### Changed
- Refactored code for better maintainability
- Improved sensor update logic for better performance

## [2024.01.08]

### Initial Release

- System monitoring (CPU, memory, disk usage)
- Temperature sensors for CPU and motherboard
- System fan RPM monitoring
- Docker container management
- VM control
- Command execution capabilities
- User script management
- UPS monitoring
- Automatic repair flows
- Config flow validation
- Comprehensive diagnostics

[Unreleased]: https://github.com/domalab/ha-unraid/compare/v2024.04.15...HEAD
[2024.04.15]: https://github.com/domalab/ha-unraid/compare/v2024.03.22...v2024.04.15
[2024.03.22]: https://github.com/domalab/ha-unraid/compare/v2024.02.10...v2024.03.22
[2024.02.10]: https://github.com/domalab/ha-unraid/compare/v2024.01.08...v2024.02.10
[2024.01.08]: https://github.com/domalab/ha-unraid/releases/tag/v2024.01.08