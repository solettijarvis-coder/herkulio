#!/bin/bash
# Setup Herkulio GitHub repo
# Run this after creating repo on GitHub

echo "Setting up Herkulio GitHub repository..."

# Configure git
git config user.email "herkulio@jlcventures.com"
git config user.name "Herkulio"

# Rename branch to main
git branch -m main

# Add remote (replace with your actual repo URL)
# git remote add origin https://github.com/herkulio/intelligence-platform.git
# OR for SSH:
# git remote add origin git@github.com:herkulio/intelligence-platform.git

echo "Git configured. Next steps:"
echo "1. Create repo at https://github.com/new"
echo "2. Name it: herkulio/intelligence-platform (or your choice)"
echo "3. Run: git remote add origin <your-repo-url>"
echo "4. Run: git push -u origin main"
