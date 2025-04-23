#!/bin/bash

# Create python virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install required packages
echo "Installing required packages..."
pip install mkdocs==1.6.1 mkdocs-material==9.6.12

# Start MkDocs development server
echo "Starting MkDocs development server..."
echo "Open http://localhost:8000 in your browser to preview the documentation"
echo "Press Ctrl+C to stop the server"
mkdocs serve