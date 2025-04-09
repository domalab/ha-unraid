#!/bin/bash

# Exit on error
set -e

# Install documentation dependencies
pip install -r requirements_docs.txt

# Serve the documentation
mkdocs serve
