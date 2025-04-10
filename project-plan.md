# Project Plan: Jekyll Documentation Site on CloudFlare Pages with Google AdSense

## Developer Implementation Guide

This implementation guide provides detailed instructions for deploying a Jekyll-based documentation site for the Unraid API Python library to CloudFlare Pages with Google AdSense integration.

## Project Structure

### Directory Structure
```
docs/
├── _config.yml             (to be created)
├── _layouts/               (to be created)
│   ├── default.html        (to be created)
│   └── home.html           (to be created)
├── _includes/              (to be created)
│   ├── head.html           (to be created)
│   ├── header.html         (to be created)
│   └── footer.html         (to be created)
├── assets/                 (to be created)
│   ├── css/
│   ├── js/
│   └── images/
├── Gemfile                 (to be created)
├── Gemfile.lock            (will be generated)
├── _headers                (to be created)
├── _redirects              (to be created)
├── .gitignore              (to be created)
├── index.md                (exists)
└── content/                (exists with many markdown files)
```

## Project Epics

---

## Epic 1: Project Setup and Configuration
**Description**: Establish the foundation for the Jekyll documentation site, including repository structure and essential configuration files.  
**Priority**: P0 (Critical)

### Story 1.1: Repository Structure Setup
**Description**: As a developer, I need a properly structured repository so I can organize the Jekyll website effectively.  
**Priority**: P0  
**Acceptance Criteria**: Repository has the correct directory structure as outlined in the implementation guide.

#### Tasks:
1. **Create base directory structure** (Priority: P0, Effort: S)
   - Create docs/ directory and necessary subdirectories
   - Set up assets/ directory with css, js, and images subdirectories

2. **Set up version control** (Priority: P0, Effort: S)
   - Initialize Git repository (if not already done)
   - Create .gitignore file with appropriate exclusions
   - Dependencies: None

### Story 1.2: Jekyll Configuration
**Description**: As a developer, I need proper Jekyll configuration to build the site correctly.  
**Priority**: P0  
**Acceptance Criteria**: Jekyll builds successfully with the defined configuration.

#### Tasks:
1. **Create _config.yml** (Priority: P0, Effort: M)
   - Add site settings, build settings, and theme configuration
   - Configure collections and navigation
   - Dependencies: 1.1.1

2. **Set up Gemfile** (Priority: P0, Effort: S)
   - Add Jekyll and required gems
   - Add theme and plugin dependencies
   - Dependencies: 1.1.1

3. **Create CloudFlare configuration files** (Priority: P1, Effort: S)
   - Create _headers file with appropriate security headers
   - Create _redirects file for URL management
   - Dependencies: 1.1.1

---

## Epic 2: Jekyll Theme and Layout Implementation
**Description**: Create layouts, templates, and styling for the documentation site.  
**Priority**: P1 (High)

### Story 2.1: Core Layout Templates
**Description**: As a user, I need a well-designed documentation site so I can easily navigate and find information.  
**Priority**: P1  
**Acceptance Criteria**: Site has consistent header, footer, and navigation across all pages.

#### Tasks:
1. **Create default layout** (Priority: P1, Effort: M)
   - Create _layouts/default.html template
   - Implement page structure with navigation and content areas
   - Dependencies: 1.2.1, 1.2.2

2. **Create home layout** (Priority: P1, Effort: M)
   - Create _layouts/home.html template for landing page
   - Implement grid layout for main navigation sections
   - Dependencies: 2.1.1

3. **Create include components** (Priority: P1, Effort: M)
   - Create head.html with metadata and styling
   - Create header.html with navigation and search
   - Create footer.html with copyright and links
   - Create nav.html with navigation menu logic
   - Dependencies: 2.1.1

### Story 2.2: Styling and Assets
**Description**: As a user, I need a visually appealing and responsive documentation site for optimal reading experience.  
**Priority**: P2 (Medium)  
**Acceptance Criteria**: Site is aesthetically pleasing, responsive, and adheres to visual design standards.

#### Tasks:
1. **Create custom CSS styles** (Priority: P2, Effort: M)
   - Create custom.scss for overriding theme styles
   - Implement responsive design elements
   - Style documentation components (API method boxes, code blocks, etc.)
   - Dependencies: 2.1.1, 2.1.2, 2.1.3

2. **Set up assets** (Priority: P2, Effort: S)
   - Add favicon and logo images
   - Implement syntax highlighting styles
   - Set up responsive image handling
   - Dependencies: 1.1.1

---

## Epic 3: Google AdSense Integration
**Description**: Integrate Google AdSense for monetization while maintaining good user experience.  
**Priority**: P1 (High)

### Story 3.1: AdSense Configuration
**Description**: As a site owner, I need AdSense properly configured so I can monetize the documentation site.  
**Priority**: P1  
**Acceptance Criteria**: AdSense code is properly implemented and ads appear in designated locations.

#### Tasks:
1. **Add AdSense script to head** (Priority: P1, Effort: S)
   - Add AdSense initialization script to head.html
   - Configure with correct publisher ID
   - Dependencies: 2.1.3

2. **Create ad placements** (Priority: P2, Effort: M)
   - Add header ad placement in header.html
   - Add footer ad placement in footer.html
   - Style ad containers for responsive display
   - Dependencies: 3.1.1, 2.1.3

3. **Configure Content Security Policy** (Priority: P2, Effort: M)
   - Update _headers file to allow AdSense domains
   - Ensure all required AdSense scripts and resources are allowed
   - Dependencies: 1.2.3, 3.1.1

### Story a.2: Ad Optimization
**Description**: As a site owner, I need ads optimally placed for good user experience and maximum revenue.  
**Priority**: P3 (Low)  
**Acceptance Criteria**: Ads are placed strategically without disrupting content consumption.

#### Tasks:
1. **Implement additional strategic ad placements** (Priority: P3, Effort: M)
   - Add inline content ad spots for longer pages
   - Add sidebar ad placement
   - Dependencies: 3.1.2

2. **Create responsive ad behavior** (Priority: P3, Effort: M)
   - Adjust ad visibility based on screen size
   - Implement ad loading optimizations
   - Dependencies: 3.1.2, 2.2.1

---

## Epic 4: Content Organization and Formatting
**Description**: Organize and format the existing documentation content for optimal readability and navigation.  
**Priority**: P1 (High)

### Story 4.1: Content Structure
**Description**: As a user, I need well-organized documentation so I can find information quickly.  
**Priority**: P1  
**Acceptance Criteria**: Content is logically organized with clear hierarchy and navigation.

#### Tasks:
1. **Review and organize existing markdown files** (Priority: P1, Effort: M)
   - Ensure frontmatter is consistent across files
   - Verify navigation order and parent-child relationships
   - Dependencies: 1.2.1

2. **Implement table of contents** (Priority: P2, Effort: S)
   - Add auto-generated table of contents to longer pages
   - Style TOC for usability
   - Dependencies: 2.1.1, 2.2.1

### Story 4.2: Content Formatting
**Description**: As a user, I need documentation with consistent formatting for better readability.  
**Priority**: P2 (Medium)  
**Acceptance Criteria**: Code blocks, tables, API examples, etc. have consistent and readable formatting.

#### Tasks:
1. **Style API documentation sections** (Priority: P2, Effort: M)
   - Create consistent styling for API method documentation
   - Style parameters, returns, and examples sections
   - Dependencies: 2.2.1

2. **Implement code syntax highlighting** (Priority: P2, Effort: S)
   - Configure syntax highlighting for Python code blocks
   - Ensure JSON and other code formats are properly highlighted
   - Dependencies: 2.2.1

---

## Epic 5: CloudFlare Pages Deployment
**Description**: Configure and deploy the site to CloudFlare Pages with proper CI/CD setup.  
**Priority**: P1 (High)

### Story 5.1: Build Configuration
**Description**: As a developer, I need proper build configuration so the site deploys correctly to CloudFlare Pages.  
**Priority**: P1  
**Acceptance Criteria**: Build script successfully compiles the Jekyll site for deployment.

#### Tasks:
1. **Create build script** (Priority: P1, Effort: S)
   - Create build.sh with required commands
   - Set appropriate permissions
   - Dependencies: 1.2.1, 1.2.2

2. **Configure environment variables** (Priority: P1, Effort: S)
   - Set up RUBY_VERSION
   - Set up JEKYLL_ENV
   - Dependencies: None

### Story 5.2: CloudFlare Pages Setup
**Description**: As a site owner, I need the site deployed to CloudFlare Pages for hosting and CDN benefits.  
**Priority**: P1  
**Acceptance Criteria**: Site is successfully deployed and accessible online.

#### Tasks:
1. **Connect repository to CloudFlare Pages** (Priority: P1, Effort: S)
   - Link GitHub repository to CloudFlare
   - Configure build settings
   - Dependencies: 5.1.1, 5.1.2

2. **Configure custom domain** (Priority: P2, Effort: S)
   - Set up custom domain if available
   - Configure SSL
   - Dependencies: 5.2.1

---

## Epic 6: Testing and Optimization
**Description**: Test and optimize the site for performance, SEO, and user experience.  
**Priority**: P2 (Medium)

### Story 6.1: Quality Assurance
**Description**: As a site owner, I need the site thoroughly tested to ensure it works correctly for all users.  
**Priority**: P2  
**Acceptance Criteria**: Site functions correctly across devices and browsers with no critical issues.

#### Tasks:
1. **Cross-browser testing** (Priority: P2, Effort: M)
   - Test on Chrome, Firefox, Safari, Edge
   - Verify responsive design works on all browsers
   - Dependencies: 5.2.1

2. **Mobile testing** (Priority: P2, Effort: M)
   - Test on iOS and Android devices
   - Verify readability and navigation on small screens
   - Dependencies: 5.2.1

3. **Functionality testing** (Priority: P2, Effort: M)
   - Test search functionality
   - Verify all links work correctly
   - Test navigation and breadcrumbs
   - Dependencies: 5.2.1

### Story 6.2: Performance Optimization
**Description**: As a user, I need the site to load quickly and perform well for efficient documentation access.  
**Priority**: P2  
**Acceptance Criteria**: Site achieves good performance scores on Lighthouse and similar tools.

#### Tasks:
1. **Asset optimization** (Priority: P3, Effort: M)
   - Optimize image sizes and formats
   - Implement lazy loading for images
   - Dependencies: 5.2.1

2. **Performance testing** (Priority: P3, Effort: M)
   - Run Lighthouse audits
   - Optimize based on recommendations
   - Dependencies: 6.2.1

3. **SEO optimization** (Priority: P3, Effort: M)
   - Implement meta tags for SEO
   - Create sitemap.xml
   - Ensure all pages have proper titles and descriptions
   - Dependencies: 5.2.1

---

## Dependencies Overview

### Critical Path Dependencies:
1. Repository Structure (1.1.1) → Jekyll Configuration (1.2.1, 1.2.2) → Core Layout Templates (2.1.1, 2.1.3) → AdSense Integration (3.1.1) → Build Configuration (5.1.1) → CloudFlare Pages Setup (5.2.1) → Testing (6.1.1, 6.1.2, 6.1.3)

### Secondary Dependencies:
1. Core Layout Templates (2.1.1, 2.1.3) → Styling (2.2.1) → Ad Placements (3.1.2) → Ad Optimization (3.2.1, 3.2.2)
2. Jekyll Configuration (1.2.1) → Content Structure (4.1.1) → Content Formatting (4.2.1, 4.2.2)
3. CloudFlare Pages Setup (5.2.1) → Performance Optimization (6.2.1, 6.2.2, 6.2.3)

## Implementation Steps Checklist

### Step 1: Initial Setup
- [ ] Clone repository
- [ ] Create directory structure
- [ ] Create .gitignore file
- [ ] Create _config.yml
- [ ] Create Gemfile
- [ ] Test Jekyll build locally

### Step 2: Layout Implementation
- [ ] Create default.html layout
- [ ] Create home.html layout
- [ ] Create head.html include
- [ ] Create header.html include
- [ ] Create footer.html include
- [ ] Create nav.html include
- [ ] Create custom.scss

### Step 3: AdSense Integration
- [ ] Add AdSense script to head.html
- [ ] Create header ad placement
- [ ] Create footer ad placement
- [ ] Configure Content Security Policy in _headers

### Step 4: Content Organization
- [ ] Review and organize markdown files
- [ ] Implement table of contents
- [ ] Style API documentation sections
- [ ] Configure syntax highlighting

### Step 5: Deployment Setup
- [ ] Create build.sh script
- [ ] Configure CloudFlare Pages project
- [ ] Set environment variables
- [ ] Test initial deployment

### Step 6: Testing and Optimization
- [ ] Perform cross-browser testing
- [ ] Perform mobile testing
- [ ] Test functionality
- [ ] Optimize assets
- [ ] Run performance tests
- [ ] Implement SEO optimizations

---

## File Templates

### _config.yml
```yaml
# Site settings
title: Unraid API Documentation
description: Official documentation for the Unraid API Python library - a clean, intuitive interface to Unraid's GraphQL API
baseurl: "" # the subpath of your site
url: "https://unraid-api-docs.pages.dev" # Replace with your actual CloudFlare Pages domain

# Build settings
markdown: kramdown
remote_theme: just-the-docs/just-the-docs
search_enabled: true

# Theme settings
color_scheme: light
heading_anchors: true
nav_sort: case_sensitive

# Collections
collections:
  content:
    permalink: "/:collection/:path/"
    output: true

# Just the Docs settings
aux_links:
  "GitHub Repository":
    - "https://github.com/domalab/unraid-api"

# Google AdSense
google_adsense_id: "ca-pub-7358189775686770"

# CloudFlare Pages specific settings
permalink: pretty

# Plugins
plugins:
  - jekyll-feed
  - jekyll-seo-tag
  - jekyll-sitemap

# Exclude files from processing
exclude:
  - Gemfile
  - Gemfile.lock
  - .sass-cache/
  - .jekyll-cache/
  - node_modules/
  - vendor/
```

### Gemfile
```ruby
source "https://rubygems.org"

gem "jekyll", "~> 4.3.2"
gem "webrick", "~> 1.8" # Required for Ruby 3+

# Theme
gem "just-the-docs"

# Plugins
group :jekyll_plugins do
  gem "jekyll-feed", "~> 0.12"
  gem "jekyll-seo-tag", "~> 2.8"
  gem "jekyll-sitemap", "~> 1.4"
end

# Windows and JRuby does not include zoneinfo files, so bundle the tzinfo-data gem
platforms :mingw, :x64_mingw, :mswin, :jruby do
  gem "tzinfo", ">= 1"
  gem "tzinfo-data"
end

# Performance-booster for watching directories on Windows
gem "wdm", "~> 0.1.1", :platforms => [:mingw, :x64_mingw, :mswin]
```

### build.sh
```bash
#!/bin/bash
# build.sh - Custom build script for CloudFlare Pages

# Move to docs directory
cd docs

# Install dependencies
bundle install

# Build the Jekyll site
JEKYLL_ENV=production bundle exec jekyll build

# Done
echo "✅ Build completed successfully!"
```
