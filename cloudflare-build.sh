#!/bin/bash

# Exit on error
set -e

echo "Starting Cloudflare Pages build process..."
echo "Skipping Python dependencies installation"

# Change to docs directory
cd docs

# Debug: List files in current directory
echo "Files in docs directory:"
ls -la

# Debug: Check Gemfile content
echo "Gemfile content:"
cat Gemfile

# Debug: Check _config.yml content
echo "_config.yml content:"
cat _config.yml

# Install Ruby dependencies
echo "Installing Ruby dependencies..."
bundle install

# Debug: List installed gems
echo "Installed gems:"
bundle list

# Build Jekyll site with verbose output
echo "Building Jekyll site..."
JEKYLL_ENV=production bundle exec jekyll build --verbose

echo "Build completed successfully!"
