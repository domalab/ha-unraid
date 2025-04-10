# Technical Context: Unraid Integration for Home Assistant

## Technology Stack

### Core Technologies
- **Python 3.11+**: Primary programming language
- **Home Assistant Core**: Framework for integration development
- **AsyncSSH**: Asynchronous SSH client library for Python
- **MkDocs**: Documentation site generator with Material theme

### Development Environment
- **Git**: Version control
- **GitHub**: Repository hosting and CI/CD
- **HACS**: Home Assistant Community Store for distribution
- **Python Virtual Environment**: For isolated development

## Technical Requirements

### Home Assistant Compatibility
- Compatible with Home Assistant Core 2023.1.0 and newer
- Follows Home Assistant integration quality guidelines
- Supports Home Assistant's repair and diagnostics frameworks

### Unraid Compatibility
- Works with Unraid 6.9.0 and newer
- Requires SSH access to be enabled on the Unraid server
- Handles various hardware configurations

### Performance Considerations
- Configurable update intervals to balance freshness vs. server load
- Efficient data caching to minimize SSH connections
- Asynchronous operations to prevent Home Assistant blocking

## Technical Constraints

### SSH-based Communication
- Reliance on SSH means the integration requires:
  - SSH to be enabled on the Unraid server
  - Valid credentials with appropriate permissions
  - Network connectivity between Home Assistant and Unraid

### Command Parsing Limitations
- Data is extracted by parsing command outputs
- Changes to Unraid's command output format could require updates
- Some advanced metrics may be unavailable or inconsistent

### Security Considerations
- SSH credentials stored in Home Assistant configuration
- No support for SSH key-based authentication (password only)
- Limited to features accessible via SSH commands

## Dependencies

### External Libraries
- `asyncssh`: Asynchronous SSH client library
- `voluptuous`: Schema validation library used by Home Assistant

### Home Assistant Core Dependencies
- `DataUpdateCoordinator`: For efficient data updates
- `ConfigFlow`: For configuration UI
- `EntityComponent`: For entity management
- `RepairsFlow`: For automatic repair flows

## Development Tools

### Testing
- `pytest`: For unit testing
- `Home Assistant Dev Tools`: For integration testing
- Manual testing on various Unraid configurations

### Documentation
- MkDocs with Material theme
- Automated documentation deployment via GitHub Actions

### Quality Control
- Pylint for code quality
- Black for code formatting
- isort for import sorting
- HACS validation

## Deployment Channels

### Primary Distribution
- HACS (Home Assistant Community Store)
- Direct GitHub installation

### Documentation Hosting
- GitHub Pages 