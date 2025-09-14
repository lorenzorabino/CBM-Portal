# Ensure venv exists then run the Flask dev server

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$venvPython = Join-Path -Path (Get-Location) -ChildPath ".venv/Scripts/python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[run] venv missing. Bootstrapping..." -ForegroundColor Yellow
    & ./scripts/setup.ps1
}

# Ensure MSSQL_CONN is available (required by the app). Prefer loading from scripts/mssql_conn.ps1 if not set.
if (-not $env:MSSQL_CONN) {
    $connFile = Join-Path $scriptDir 'mssql_conn.ps1'
    if (Test-Path $connFile) {
        . $connFile
        Write-Host "[run] Loaded MSSQL_CONN from scripts/mssql_conn.ps1" -ForegroundColor Green
    } else {
        Write-Error "[run] MSSQL_CONN is not set. Create scripts/mssql_conn.ps1 to set it or export MSSQL_CONN before running."
        exit 1
    }
}

# Guard: discourage legacy DB 'CBM' (use 'CBM2')
if ($env:MSSQL_CONN -match '/CBM(\?|$)') {
    Write-Error "[run] MSSQL_CONN points to 'CBM' (legacy). Please switch to 'CBM2' in scripts/mssql_conn.ps1 or your environment."
    exit 1
}

Write-Host "[run] Using MSSQL_CONN:" $env:MSSQL_CONN -ForegroundColor Cyan

$env:FLASK_ENV = 'development'
$env:FLASK_DEBUG = '1'
& $venvPython run.py
