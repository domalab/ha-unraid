# Changelog

All notable changes to the Unraid integration will be documented in this file.

## [Unreleased]

### Fixed
- **Issue #69**: Fixed date parsing errors for parity history by adding support for multiple date formats including those without year information
- **Issue #64**: Corrected disk health usage reporting by using POSIX output format for the df command
- **Issue #56**: Fixed "Command failed: open failed" errors in network operations with retry mechanism and improved error handling
- **Issue #35**: Improved system fan detection with more flexible pattern matching and better error handling
