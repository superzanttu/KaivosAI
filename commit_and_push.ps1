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

Examples:
  .\commit_and_push.ps1
  .\commit_and_push.ps1 "Lisätty uusia ominaisuuksia"
  .\commit_and_push.ps1 "Korjattu bugi" -CreateTag
  .\commit_and_push.ps1 -Message "Custom message" -AppendMessage "Lisätiedot"
#>

param(
	[Parameter(Position=0)]
	[string]$AppendMessage = "",
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

# Rakenna commit viesti
$commitFile = Join-Path (Get-Location) "commit_message.txt"
$commitMessage = ""

# Luetaan olemassa olevaa viestia tai käytetään oletusta
if (Test-Path $commitFile) {
	$commitMessage = Get-Content $commitFile -Raw -ErrorAction SilentlyContinue
	if (-not $commitMessage -or $commitMessage.Trim() -eq "") {
		Write-Output "commit_message.txt is empty."
		$userMessage = Read-Host "Enter commit message"
		if ($userMessage.Trim()) {
			$commitMessage = $userMessage.Trim()
		} else {
			Write-Output "No commit message provided. Using default message."
			$commitMessage = $Message
		}
	}
} else {
	$commitMessage = $Message
}

# Lisää käyttäjän antama lisätieto viestin loppuun
if ($AppendMessage) {
	$commitMessage = $commitMessage.TrimEnd() + "`n`n" + $AppendMessage.Trim()
	Write-Output "Appended user message to commit."
}

# Kirjoita viesti tiedostoon
if ($commitMessage) {
	$commitMessage | Set-Content -Path $commitFile -Encoding UTF8 -NoNewline
}

# commit only if there are staged changes
$staged = git diff --cached --name-only
if (-not $staged) {
	Write-Output "No changes to commit."
} else {
	git commit -F $commitFile
	
	if ($LASTEXITCODE -eq 0) {
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