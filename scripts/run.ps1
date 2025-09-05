# Ensure venv exists then run the Flask dev server

$ErrorActionPreference = 'Stop'

$venvPython = Join-Path -Path (Get-Location) -ChildPath ".venv/Scripts/python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[run] venv missing. Bootstrapping..." -ForegroundColor Yellow
    & ./scripts/setup.ps1
}

$env:FLASK_ENV = 'development'
$env:FLASK_DEBUG = '1'
& $venvPython run.py
