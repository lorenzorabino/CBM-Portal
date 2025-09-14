param(
  [string] $Sqlite = "./database/portal_demo3.db",
  [switch] $DropExisting,
  [string] $Tables = "",
  [string] $Exclude = "",
  [int] $BatchSize = 1000
)

$ErrorActionPreference = 'Stop'

if (-not $env:MSSQL_CONN) {
  Write-Error "MSSQL_CONN environment variable is not set. Set it to a valid pyodbc URL."
}

# Enforce CBM2 target
if ($env:MSSQL_CONN -match '/CBM(\?|$)') {
  Write-Error "[migrate] MSSQL_CONN points to 'CBM' (legacy). Please switch to 'CBM2' before migrating."
  exit 1
}

$python = Join-Path -Path (Get-Location) -ChildPath ".venv/Scripts/python.exe"
if (-not (Test-Path $python)) {
  Write-Host "[migrate] venv missing. Running setup first..." -ForegroundColor Yellow
  & ./scripts/setup.ps1
}

$argsList = @("./scripts/migrate_sqlite_to_mssql.py", "--sqlite", $Sqlite, "--batch-size", $BatchSize)
if ($DropExisting) { $argsList += "--drop-existing" }
if ($Tables) { $argsList += @("--tables", $Tables) }
if ($Exclude) { $argsList += @("--exclude", $Exclude) }

& $python @argsList
