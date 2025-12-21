#!/usr/bin/env powershell
<#
.SYNOPSIS
    Launch KaivosAI in a new PowerShell window

.DESCRIPTION
    This script opens a new PowerShell window and launches the KaivosAI mining simulator.
    The game runs in a separate window so you can continue working in the current terminal.

.EXAMPLE
    .\test.ps1
#>

# Get the script's directory
$scriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition

# Build command to run in new window
$command = @"
# Change to script directory
cd '$scriptDir'

# Activate virtual environment
& '.\\.venv\\Scripts\\Activate.ps1'

# Run KaivosAI
Write-Host "Starting KaivosAI..." -ForegroundColor Cyan
python kaivosai.py

# Keep window open if there's an error
if (`$LASTEXITCODE -ne 0) {
    Write-Host "Program exited with code `$LASTEXITCODE" -ForegroundColor Red
    Read-Host "Press Enter to close"
}
"@

# Launch in new window
try {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $command -WindowStyle Normal -ErrorAction Stop
    Write-Host "[+] KaivosAI launched in new window" -ForegroundColor Green
}
catch {
    Write-Host "[!] Failed to launch: $_" -ForegroundColor Red
    exit 1
}
