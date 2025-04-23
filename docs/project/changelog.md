# Changelog

This page documents all notable changes to the Unraid Integration for Home Assistant.

## [Unreleased]

### Added
- Documentation in MkDocs with Material theme
- Added GitHub Pages site for documentation hosting

## [2025.01.08]

### Fixed
- Fix for issue #36 regarding missing VM and Container switches on Unraid versions 6.12.x
- Fix for issue #38 regarding Parity Check Status Sensor not detecting all fields in /boot/config/parity-check.log
- Fix for issue #37 regarding SpinDownDelay error from HA logs
- Fix for issue #51 regarding Error checking disk state for /dev/nvme0n1p1
- Fix for issue #43 regarding CPU Temp not working on certain chipsets
- Fix for issue #37 regarding pool device named temp from being detected

### Changed
- Changed naming on UPS sensors to now display UPS Current Consumption, UPS Current Load and UPS Total Consumption
- Removed Docker Insights (Beta) feature due to causing HA instability issues

## [2024.12.28]

### Added
- System Fan Sensors for monitoring cooling performance
- Parity Health Monitoring
- Pool Usage & Custom Pool Disk Names
- Docker Insights (Beta) - requires Dockersocket container

### Fixed
- Entity Naming Schema & Unique IDs issues
- Inaccuracies in network traffic calculations

### Changed
- Improved disk mappings logic
- Reduced SSH calls for better performance

## [2024.11.15]

### Added
- Configurable update intervals for sensors
- UPS power monitoring
- Network traffic monitoring
- Parity check sensor
- Disk health monitoring

### Fixed
- Issues with executing service commands
- Improved support for CPU and motherboard sensors
- Fixed UPS sensor functionality
- Fixed special characters with VMs not being recognised

### Changed
- Refined naming conventions
- Updated versioning style to align with Home Assistant standards

## [v0.1.5] - 2024-10-25

### Added
- Diagnostic sensors and ability to download diagnostics file for troubleshooting

## [v0.1.4] - 2024-10-22

### Added
- Improved Docker container state tracking with detailed status information
- Enhanced VM state detection with better OS type recognition
- Dynamic icons for VMs based on OS type
- Additional container and VM attributes

### Fixed
- VM state tracking when turned off from Unraid
- Docker container state synchronization issues
- JSON parsing errors in container information retrieval
- State attribute errors in entity updates

### Changed
- Improved Docker container start/stop operations reliability
- Enhanced state synchronization
- Better error handling and logging
- More robust parsing of container and VM states

## [v0.1.3] - 2024-10-21

### Added
- Option to specify if UPS is connected to Unraid during setup
- Feature to re-configure the integration after initial setup

### Fixed
- Stability improvements with SSH connection
- Removed ping check that caused Home Assistant to hang

### Changed
- Removed Docker Container Update Sensor due to conflicts with Unraid's Auto Update

## [v0.1.2] - 2024-10-18

### Added
- Docker Container Update Sensor

### Changed
- Stability improvements with SSH connection to Unraid

## [v0.1.1] - 2024-10-16

### Added
- Docker vDisk sensor
- Docker Log Sensor

## [v0.1.0] - 2024-10-15

### Initial Release
- Monitor CPU, RAM, Boot, Cache, Array Disks, and Array usage
- Monitor UPS connected to Unraid
- Control Docker containers (start/stop)
- Manage VMs (start/stop)
- Execute shell commands on Unraid server
- Manage user scripts

[Unreleased]: https://github.com/domalab/ha-unraid/compare/v2025.01.08...HEAD
[2025.01.08]: https://github.com/domalab/ha-unraid/compare/v2024.12.28...v2025.01.08
[2024.12.28]: https://github.com/domalab/ha-unraid/compare/v2024.11.15...v2024.12.28
[2024.11.15]: https://github.com/domalab/ha-unraid/compare/v0.1.5...v2024.11.15
[v0.1.5]: https://github.com/domalab/ha-unraid/compare/v0.1.4...v0.1.5
[v0.1.4]: https://github.com/domalab/ha-unraid/compare/v0.1.3...v0.1.4
[v0.1.3]: https://github.com/domalab/ha-unraid/compare/v0.1.2...v0.1.3
[v0.1.2]: https://github.com/domalab/ha-unraid/compare/v0.1.1...v0.1.2
[v0.1.1]: https://github.com/domalab/ha-unraid/compare/v0.1.0...v0.1.1
[v0.1.0]: https://github.com/domalab/ha-unraid/releases/tag/v0.1.0