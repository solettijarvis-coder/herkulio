#!/bin/bash
# Create Herkulio repo on GitHub and push

REPO_URL="${1:-git@github.com:solettijarvis-coder/herkulio.git}"

echo "=========================================="
echo "Herkulio GitHub Setup"
echo "=========================================="
echo ""
echo "STEP 1: Create the repo"
echo "----------------------"
echo "1. Go to: https://github.com/new"
echo "2. Repository name: herkulio"
echo "3. Description: Herkulio OSINT Intelligence SaaS Platform"
echo "4. Make it PRIVATE"
echo "5. Click 'Create repository'"
echo ""
echo "STEP 2: Push the code"
echo "---------------------"
echo "Running: git push -u origin main"
echo ""

cd /home/jarvis/herkulio-saas
git remote set-url origin "$REPO_URL"
GIT_SSH_COMMAND="ssh -i ~/.ssh/herkulio -o IdentitiesOnly=yes" git push -u origin main

echo ""
echo "✅ Herkulio pushed to GitHub!"
echo "Repository: $REPO_URL"
