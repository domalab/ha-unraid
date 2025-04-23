# Contributing to the Project

Thank you for your interest in contributing to the Unraid Integration for Home Assistant! This guide will help you get started with contributing to the project.

## Ways to Contribute

There are many ways to contribute to the project:

- **Bug Reports**: Reporting issues you encounter
- **Feature Requests**: Suggesting new features or improvements
- **Documentation**: Improving or expanding documentation
- **Code Contributions**: Fixing bugs or implementing new features
- **Testing**: Testing the integration in different environments
- **Helping Others**: Helping users in GitHub discussions or Home Assistant community

## Development Setup

### Prerequisites

To develop for this integration, you'll need:

1. A working Home Assistant development environment
2. An Unraid server for testing
3. Basic knowledge of Python
4. Familiarity with Home Assistant custom component development

### Setting Up a Development Environment

1. **Fork the Repository**: Fork [domalab/ha-unraid](https://github.com/domalab/ha-unraid) on GitHub
2. **Clone Your Fork**:

   ```bash
   git clone https://github.com/your-username/ha-unraid.git
   cd ha-unraid
   ```

3. **Set Up a Development Home Assistant Instance**:
   - Use [the Home Assistant development container](https://developers.home-assistant.io/docs/development_environment)
   - Or set up a dedicated test instance
4. **Install Development Dependencies**:

   ```bash
   python -m pip install -r requirements_dev.txt
   ```

### Development Workflow

1. **Create a Branch**: Create a branch for your feature or bug fix

   ```bash
   git checkout -b your-feature-name
   ```

2. **Make Changes**: Implement your changes following the code style and conventions
3. **Write Tests**: Add tests for your changes to ensure they work correctly
4. **Run Tests Locally**: Ensure all tests pass before submitting

   ```bash
   pytest
   ```

5. **Lint Your Code**: Ensure your code passes all linting checks

   ```bash
   pylint custom_components/unraid
   ```

6. **Commit Your Changes**: Write clear, concise commit messages
7. **Push to Your Fork**:

   ```bash
   git push origin your-feature-name
   ```

8. **Create a Pull Request**: Submit a pull request from your fork to the main repository

## Code Style and Conventions

The project follows the [Home Assistant Development Guidelines](https://developers.home-assistant.io/docs/development_guidelines). Key points include:

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code style
- Use [typing](https://docs.python.org/3/library/typing.html) for type hints
- Write [docstrings](https://www.python.org/dev/peps/pep-0257/) for functions and classes
- Format strings using [f-strings](https://www.python.org/dev/peps/pep-0498/) where appropriate
- Follow existing patterns and conventions in the codebase

## Testing

### Unit Tests

- Write unit tests for all new code
- Make sure existing tests still pass with your changes
- Test both expected behavior and edge cases
- Use appropriate mocking for external dependencies

### Integration Tests

- Test the integration with a real Unraid server when possible
- Test with different Unraid versions if available
- Verify that your changes work in different environments

## Pull Request Process

1. **Describe Your Changes**: Provide a clear description of what your PR does
2. **Link Related Issues**: Reference any related issues using the `#issue-number` syntax
3. **Pass CI Checks**: Ensure your PR passes all CI checks
4. **Review Process**: Respond to any feedback or suggestions during review
5. **Merge**: Once approved, your PR will be merged into the main codebase

## Bug Reports and Feature Requests

### Reporting Bugs

When reporting bugs, please include:

1. Steps to reproduce the issue
2. Expected behavior
3. Actual behavior
4. Home Assistant version
5. Unraid version
6. Integration version
7. Relevant logs or error messages
8. Any other context that might be helpful

### Requesting Features

When requesting a feature, please include:

1. A clear description of the feature
2. The problem it solves or benefit it provides
3. Any implementation ideas you have
4. Whether you're willing to help implement it

## Documentation Contributions

Documentation improvements are always welcome! To contribute to documentation:

1. Follow the same pull request process as for code changes
2. Preview documentation changes locally using [MkDocs](https://www.mkdocs.org/)

   ```bash
   mkdocs serve
   ```

3. Ensure your changes are accurate and well-written

## Getting Help

If you need help with contributing:

- Check the [project's GitHub issues](https://github.com/domalab/ha-unraid/issues) for similar questions
- Ask in the [Home Assistant Community](https://community.home-assistant.io/)
- Open a [GitHub discussion](https://github.com/domalab/ha-unraid/discussions) with your question

## Code of Conduct

Please follow these guidelines when contributing:

- Be respectful and inclusive toward other contributors
- Provide constructive feedback on others' contributions
- Focus on the issues, not the person
- Accept feedback graciously on your own contributions
- Help create a positive community for everyone

## License

By contributing to this project, you agree that your contributions will be licensed under the project's [Apache 2.0 License](https://github.com/domalab/ha-unraid/blob/main/LICENSE).
