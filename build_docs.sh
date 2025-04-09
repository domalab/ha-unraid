#!/bin/bash

# Exit on error
set -e

# Install documentation dependencies
pip install -r requirements_docs.txt

# Build the documentation
mkdocs build

# Output success message
echo "Documentation built successfully in the 'site' directory."
echo "To view the documentation, open 'site/index.html' in your browser."
echo "To serve the documentation locally, run 'mkdocs serve'."
