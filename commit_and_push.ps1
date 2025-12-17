<#
Run these commands in PowerShell from the project root to commit and push.
Edit the remote URL line if your remote already exists or replace with your repo URL.
#>

# Optional: set git user (only if not configured)
# git config --global user.name "Your Name"
# git config --global user.email "you@example.com"

# Show status
git status --porcelain

# Add files (respect .gitignore)
git add .

# Commit
git commit -m "Add KaivosAI game, task manager, map and persistence"

# If remote not set, add it (replace URL with your GitHub repo)
# git remote add origin https://github.com/USERNAME/KaivosAI.git

# Push to main
git branch -M main
git push -u origin main