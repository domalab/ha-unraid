#!/bin/bash

# Exit on error
set -e

echo "Starting Cloudflare Pages build process..."
echo "Skipping Python dependencies installation"

# Change to docs directory
cd docs

# Install Ruby dependencies
echo "Installing Ruby dependencies..."
bundle install

# Build Jekyll site
echo "Building Jekyll site..."
JEKYLL_ENV=production bundle exec jekyll build

echo "Build completed successfully!"
