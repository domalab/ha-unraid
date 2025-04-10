#!/bin/bash
# Script to build the Jekyll site for Cloudflare Pages

# Print debug information
echo "Ruby version: $(ruby -v)"
echo "Gem version: $(gem -v)"

# Install a compatible version of Bundler for Ruby 3.3.0
gem install bundler -v 2.4.22
echo "Bundler version: $(bundle -v)"

# Install dependencies
bundle _2.4.22_ install

# Build the site
bundle _2.4.22_ exec jekyll build 