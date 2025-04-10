# Setting Up a Documentation Site with Jekyll, Just the Docs, and Cloudflare Pages

This guide will walk you through the process of setting up a professional documentation site using Jekyll with the Just the Docs theme, deployed on Cloudflare Pages.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Repository Setup](#repository-setup)
3. [Jekyll and Just the Docs Installation](#jekyll-and-just-the-docs-installation)
4. [Site Configuration](#site-configuration)
5. [Content Structure](#content-structure)
6. [Local Development](#local-development)
7. [Cloudflare Pages Deployment](#cloudflare-pages-deployment)
8. [Custom Domain Configuration](#custom-domain-configuration)
9. [Maintenance and Updates](#maintenance-and-updates)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

- GitHub account
- Cloudflare account
- Ruby 3.3.0 installed (do not use Ruby 3.4.0 due to compatibility issues with Jekyll)
- Git installed
- Basic knowledge of Markdown

## Repository Setup

1. Create a new repository on GitHub for your documentation project.

2. Clone the repository to your local machine:
   ```bash
   git clone https://github.com/yourusername/your-repo.git
   cd your-repo
   ```

3. Create a `docs` directory in the repository root:
   ```bash
   mkdir docs
   cd docs
   ```

## Jekyll and Just the Docs Installation

1. Create a `Gemfile` in the `docs` directory with the following content:
   ```ruby
   source "https://rubygems.org"

   # Specify Ruby version compatibility
   ruby ">= 3.0.0"

   gem "jekyll", "~> 4.3.2"
   gem "webrick", "~> 1.8" # Required for Ruby 3+

   # Theme
   gem "just-the-docs"

   # Plugins
   group :jekyll_plugins do
     gem "jekyll-feed", "~> 0.12"
     gem "jekyll-seo-tag", "~> 2.8"
     gem "jekyll-sitemap", "~> 1.4"
     gem "jekyll-remote-theme"
   end

   # Windows and JRuby does not include zoneinfo files
   platforms :mingw, :x64_mingw, :mswin, :jruby do
     gem "tzinfo", ">= 1"
     gem "tzinfo-data"
   end

   # Performance-booster for watching directories on Windows
   gem "wdm", "~> 0.1.1", :platforms => [:mingw, :x64_mingw, :mswin]
   ```

2. Create a `.ruby-version` file in the `docs` directory:
   ```
   3.3.0
   ```

3. Install the dependencies:
   ```bash
   bundle install
   ```

4. Create a Cloudflare-specific build script for deployment. Create a file named `cloudflare-build.sh` in the `docs` directory:
   ```bash
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
   ```

5. Make the script executable:
   ```bash
   chmod +x cloudflare-build.sh
   ```

6. Create a Cloudflare Pages configuration file. Create a `.cloudflare` directory in the repository root and add a `pages.toml` file:
   ```toml
   # Cloudflare Pages configuration
   [build]
     command = "cd docs && ./cloudflare-build.sh"
     publish = "docs/_site"

   [build.environment]
     RUBY_VERSION = "3.3.0"
   ```

## Site Configuration

1. Create a `_config.yml` file in the `docs` directory:
   ```yaml
   # Site settings
   title: Your Documentation Title
   description: A concise description of your documentation
   baseurl: "" # the subpath of your site
   url: "https://your-docs-site.pages.dev" # Replace with your actual CloudFlare Pages domain

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
       - "https://github.com/yourusername/your-repo"

   # CloudFlare Pages specific settings
   permalink: pretty

   # Plugins
   plugins:
     - jekyll-feed
     - jekyll-seo-tag
     - jekyll-sitemap
     - jekyll-remote-theme

   # Exclude files from processing
   exclude:
     - Gemfile
     - Gemfile.lock
     - .sass-cache/
     - .jekyll-cache/
     - node_modules/
     - vendor/
   ```

2. Create a `.gitignore` file in the `docs` directory:
   ```
   _site
   .sass-cache
   .jekyll-cache
   .jekyll-metadata
   vendor
   .bundle
   ```

## Content Structure

1. Create an `index.md` file in the `docs` directory:
   ```markdown
   ---
   layout: home
   title: Home
   nav_order: 1
   ---

   # Your Documentation Title

   Welcome to the official documentation for your project. This site provides comprehensive information about installation, configuration, and usage.

   ## Features

   - Feature 1
   - Feature 2
   - Feature 3
   - Feature 4

   ## Quick Navigation

   <div class="grid-container">
     <div class="grid-item">
       <a href="{{ site.baseurl }}/content/getting-started/installation">
         <h3>Getting Started</h3>
         <p>Installation and basic setup</p>
       </a>
     </div>
     <div class="grid-item">
       <a href="{{ site.baseurl }}/content/api">
         <h3>API Reference</h3>
         <p>Detailed API documentation</p>
       </a>
     </div>
     <div class="grid-item">
       <a href="{{ site.baseurl }}/content/guides">
         <h3>Guides</h3>
         <p>Step-by-step tutorials</p>
       </a>
     </div>
   </div>

   ## About

   Brief description of your project and its purpose.

   ## License

   This project is licensed under the MIT License - see the [LICENSE](https://github.com/yourusername/your-repo/blob/main/LICENSE) file for details.
   ```

2. Create a content structure for your documentation:
   ```bash
   mkdir -p content/getting-started
   mkdir -p content/api
   mkdir -p content/guides
   ```

3. Create an index file for each section:

   For `content/getting-started/index.md`:
   ```markdown
   ---
   layout: default
   title: Getting Started
   nav_order: 2
   has_children: true
   permalink: /content/getting-started
   ---

   # Getting Started

   This section will help you get started with the project.
   ```

   For `content/api/index.md`:
   ```markdown
   ---
   layout: default
   title: API Reference
   nav_order: 3
   has_children: true
   permalink: /content/api
   ---

   # API Reference

   This section provides detailed documentation for the API.
   ```

   For `content/guides/index.md`:
   ```markdown
   ---
   layout: default
   title: Guides
   nav_order: 4
   has_children: true
   permalink: /content/guides
   ---

   # Guides

   Step-by-step tutorials for common tasks.
   ```

4. Add a sample page to the Getting Started section:

   Create `content/getting-started/installation.md`:
   ```markdown
   ---
   layout: default
   title: Installation
   parent: Getting Started
   nav_order: 1
   ---

   # Installation

   This guide will walk you through the process of installing the project.

   ## Requirements

   - Requirement 1
   - Requirement 2

   ## Installation Steps

   1. Step 1
   2. Step 2
   3. Step 3

   ## Verification

   To verify the installation was successful, run:

   ```bash
   your-command --version
   ```

   ## Next Steps

   Now that you have installed the project, you can:

   1. [Configure the settings](configuration)
   2. [Learn the basics](basics)
   ```

## Local Development

1. Start the Jekyll server locally:
   ```bash
   cd docs
   bundle exec jekyll serve
   ```

2. Open your browser and navigate to `http://localhost:4000` to see your site.

3. Make changes to your content and see them reflected in real-time.

## Cloudflare Pages Deployment

1. Commit and push your changes to GitHub:
   ```bash
   git add .
   git commit -m "Initial documentation setup"
   git push
   ```

2. Log in to your Cloudflare account and navigate to the Pages section.

3. Click "Create a project" and select "Connect to Git".

4. Select your repository from the list.

5. Configure your build settings:
   - Project name: `your-project-docs` (or any name you prefer)
   - Production branch: `main` (or your default branch)
   - Build command: `cd docs && bundle install && bundle exec jekyll build`
   - Build output directory: `docs/_site`
   - Environment variables:
     - `RUBY_VERSION`: `3.3.0`
     - `JEKYLL_ENV`: `production`

6. Click "Save and Deploy".

7. Wait for the build to complete. Cloudflare Pages will provide you with a URL like `https://your-project-docs.pages.dev`.

## Custom Domain Configuration

1. In the Cloudflare Pages project, go to the "Custom domains" tab.

2. Click "Set up a custom domain".

3. Enter your domain or subdomain (e.g., `docs.yourdomain.com` or `yourdomain.com/docs`).

4. Follow the instructions to verify domain ownership and configure DNS settings.

5. Update the `url` in your `_config.yml` to match your custom domain.

6. Commit and push the changes to trigger a new deployment.

## Maintenance and Updates

### Updating the Theme

To update the Just the Docs theme:

1. Update the version in your Gemfile:
   ```ruby
   gem "just-the-docs", "~> 0.5.0" # Replace with the latest version
   ```

2. Run:
   ```bash
   bundle update just-the-docs
   ```

### Adding New Content

1. Create new Markdown files in the appropriate directories.

2. Include the proper front matter at the top of each file:
   ```yaml
   ---
   layout: default
   title: Your Page Title
   parent: Parent Section Title
   nav_order: 1
   ---
   ```

3. For nested navigation, use:
   ```yaml
   ---
   layout: default
   title: Your Page Title
   parent: Parent Section Title
   grand_parent: Grandparent Section Title
   nav_order: 1
   ---
   ```

### Custom Styling

1. Create a `assets/css/custom.css` file in the `docs` directory:
   ```css
   /* Custom styles for your documentation */
   ```

2. Reference it in your `_config.yml`:
   ```yaml
   # Custom CSS
   custom_css:
     - custom.css
   ```

## Troubleshooting

### Common Issues

1. **Build Failures on Cloudflare Pages**:
   - Check the build logs for specific errors
   - Ensure Ruby version is set to 3.3.0
   - Verify that all dependencies are properly installed

2. **Missing Content in Navigation**:
   - Check that your front matter includes the correct `parent` and `nav_order` values
   - Ensure file paths and permalinks are correct

3. **Styling Issues**:
   - Check for CSS conflicts
   - Verify that the theme is properly loaded

### Getting Help

- Just the Docs Documentation: [https://just-the-docs.github.io/just-the-docs/](https://just-the-docs.github.io/just-the-docs/)
- Jekyll Documentation: [https://jekyllrb.com/docs/](https://jekyllrb.com/docs/)
- Cloudflare Pages Documentation: [https://developers.cloudflare.com/pages/](https://developers.cloudflare.com/pages/)

## Additional Resources

- [Just the Docs GitHub Repository](https://github.com/just-the-docs/just-the-docs)
- [Jekyll Themes](https://jekyllthemes.io/)
- [Markdown Guide](https://www.markdownguide.org/)
- [Cloudflare Pages Jekyll Guide](https://developers.cloudflare.com/pages/framework-guides/deploy-a-jekyll-site/)

---

By following this guide, you'll have a professional documentation site using Jekyll with the Just the Docs theme, deployed on Cloudflare Pages. The site will be easy to maintain, update, and extend as your project grows.
