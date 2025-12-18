<#
Run these commands in PowerShell from the project root to commit and push.
Edit the remote URL line if your remote already exists or replace with your repo URL.
#>

<#
Safe commit & push helper for KaivosAI.

Usage:
  - Edit remote URL below (or run `git remote add origin <URL>` once).
  - Run this script from the repository root in PowerShell.
  - If PowerShell blocks script execution, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (admin rights not required for Process scope).
#>

param(
	[string]$RemoteUrl = "",
	[string]$Branch = "main",
	[string]$Message = "Update KaivosAI",
	[switch]$CreateTag
)

function Ensure-Git {
	if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
		Write-Error "git is not installed or not in PATH. Install Git and retry."
		exit 1
	}
}

Ensure-Git

if (-not (Test-Path .git)) {
	git init
	Write-Output "Initialized empty git repository."
}

if ($RemoteUrl) {
	# set or update origin
	$existing = git remote get-url origin 2>$null
	if ($LASTEXITCODE -ne 0) {
		git remote add origin $RemoteUrl
		Write-Output "Added remote origin=$RemoteUrl"
	} elseif ($existing -ne $RemoteUrl) {
		git remote set-url origin $RemoteUrl
		Write-Output "Updated remote origin to $RemoteUrl"
	}
}

# Ensure user identity is configured locally if missing
$name = git config user.name
$email = git config user.email
if (-not $name -or -not $email) {
	Write-Output "Git user.name or user.email not set for this repo."
	Write-Output "Set globally with:"
	Write-Output "  git config --global user.name \"Your Name\""
	Write-Output "  git config --global user.email \"you@example.com\""
}

Write-Output "Repository status (uncommitted changes):"
git status --short

git add -A

# If commit_message.txt exists in repo root, use it as commit message and trim whitespace.
$commitFile = Join-Path (Get-Location) "commit_message.txt"
if (Test-Path $commitFile) {
	try {
		$fileMsg = Get-Content $commitFile -Raw -ErrorAction Stop
		if ($fileMsg) { $Message = $fileMsg.Trim() }
	} catch {
		Write-Output "Warning: failed to read commit_message.txt: $_"
	}
}

# commit only if there are staged changes
$staged = git diff --cached --name-only
if (-not $staged) {
	Write-Output "No changes to commit."
} else {
	git commit -m $Message
	if ($LASTEXITCODE -eq 0 -and (Test-Path $commitFile)) {
		# delete commit_message.txt after successful commit
		try {
			Remove-Item $commitFile -Force -ErrorAction Stop
			Write-Output "Removed commit_message.txt after commit."
		} catch {
			Write-Output "Warning: failed to remove commit_message.txt: $_"
		}
	}
}

# Ensure branch and push
git branch -M $Branch
git push -u origin $Branch

if ($CreateTag.IsPresent) {
	$tag = Read-Host "Tag name (e.g. v0.1.0)"
	if ($tag) {
		git tag $tag
		git push origin $tag
	}
}