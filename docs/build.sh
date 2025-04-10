#!/bin/bash

# build.sh - Custom build script for CloudFlare Pages

# Install dependencies
bundle install

# Build the Jekyll site
JEKYLL_ENV=production bundle exec jekyll build

# Done
echo "✅ Build completed successfully!"
