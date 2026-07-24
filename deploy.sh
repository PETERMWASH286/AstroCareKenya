#!/bin/bash
cd ~/public_html/AstroCare-main

# Optional: stash any local changes temporarily
git stash --include-untracked

# Pull latest changes from GitHub
git fetch origin
git reset --hard origin/main

# Optional: pop local stashed changes (ignored files)
git stash pop || true

# Optional: run migrations or restart server
# python3 manage.py migrate  # if Django
# systemctl restart myapp    # if using a service