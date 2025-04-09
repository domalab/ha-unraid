---
layout: default
title: Contributing Guide
---

We welcome contributions to the Home Assistant Unraid Integration! This guide will help you get started with contributing to the project.

## Ways to Contribute

There are many ways to contribute to the project:

1. **Reporting Bugs**: Report bugs and issues you encounter
2. **Suggesting Features**: Suggest new features or improvements
3. **Writing Code**: Implement new features or fix bugs
4. **Improving Documentation**: Help improve the documentation
5. **Testing**: Test new features and provide feedback

## Reporting Bugs

If you encounter a bug:

1. Check if the bug has already been reported on [GitHub Issues](https://github.com/domalab/ha-unraid/issues)
2. If not, create a new issue with:
   - A clear title and description
   - Steps to reproduce the bug
   - Expected and actual behavior
   - Home Assistant and Unraid versions
   - Any relevant logs or screenshots

## Suggesting Features

If you have an idea for a new feature:

1. Check if the feature has already been suggested on [GitHub Issues](https://github.com/domalab/ha-unraid/issues)
2. If not, create a new issue with:
   - A clear title and description
   - The problem the feature would solve
   - How the feature would work
   - Any relevant examples or mockups

## Development Setup

To set up a development environment:

1. Fork the repository on GitHub
2. Clone your fork locally:

   ```bash
   git clone https://github.com/YOUR_USERNAME/ha-unraid.git
   cd ha-unraid
   ```

3. Set up a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Development Workflow

1. Create a new branch for your changes:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes
3. Test your changes
4. Commit your changes with a clear commit message:

   ```bash
   git commit -m "Add feature: your feature name"
   ```

5. Push your changes to your fork:

   ```bash
   git push origin feature/your-feature-name
   ```

6. Create a pull request on GitHub

## Code Style

Please follow these guidelines for code style:

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code
- Use meaningful variable and function names
- Add comments for complex code
- Write docstrings for functions and classes
- Keep functions small and focused

## Testing

Before submitting a pull request:

1. Test your changes thoroughly
2. Make sure all existing tests pass
3. Add new tests for new functionality

## Documentation

If your changes require documentation updates:

1. Update the relevant documentation files
2. Add comments to your code
3. Update the README if necessary

## Pull Request Process

1. Update the README.md with details of changes if needed
2. Update the CHANGELOG.md with details of changes
3. The PR will be merged once it's reviewed and approved

## Questions?

If you have any questions, feel free to:

1. Open an issue on GitHub
2. Ask in the Home Assistant community forums

Thank you for contributing to the Home Assistant Unraid Integration!
