<# Päivittää Sphinx-dokumentaation docstringeistä HTML-muotoon #>
param(
    [string]$BuildDir = "docs/_build/html"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Push-Location $PSScriptRoot
try {
    Write-Host "Asennetaan dokumentaatiovaatimukset..." -ForegroundColor Cyan
    python -m pip install -r "docs/requirements.txt"

    if (-not (Test-Path $BuildDir)) {
        New-Item -ItemType Directory -Path $BuildDir | Out-Null
    }

    Write-Host "Rakennetaan HTML-dokumentaatio..." -ForegroundColor Cyan
    python -m sphinx -b html "docs" $BuildDir
    Write-Host "Valmis: $BuildDir" -ForegroundColor Green
}
finally {
    Pop-Location
}
