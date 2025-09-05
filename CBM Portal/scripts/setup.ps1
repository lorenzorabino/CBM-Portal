# Bootstrap Python virtual environment and install dependencies
param(
    [string[]] $PreferredVersions = @('3.13','3.12','3.11','3.10')
)

$ErrorActionPreference = 'Stop'

function Find-PythonVersion {
    param([string[]] $Versions)
    foreach ($v in $Versions) {
        try {
            & py -$v -V *> $null
            if ($LASTEXITCODE -eq 0) { return $v }
        } catch { }
    }
    return $null
}

function Resolve-PythonExe {
    # Prefer Windows py launcher if present and matching version is available
    $selected = Find-PythonVersion -Versions $PreferredVersions
    if ($selected) {
        return @{ kind = 'py'; arg = "-$selected" }
    }
    # Fallback: try python on PATH
    $candidates = @('python','python3','py')
    foreach ($name in $candidates) {
        try {
            & $name -V 2>$null 1>$null
            if ($LASTEXITCODE -eq 0) {
                # Check version >= 3.10
                $verOut = & $name -c "import sys;print(sys.version_info[:3])"
                if ($verOut) {
                    # parse like (3, 12, 4)
                    if ($verOut -match '([0-9]+),\s*([0-9]+)') {
                        $maj = [int]$Matches[1]; $min = [int]$Matches[2]
                        if ($maj -ge 3 -and $min -ge 10) { return @{ kind = 'exe'; path = $name } }
                    }
                } else {
                    return @{ kind = 'exe'; path = $name }
                }
            }
        } catch { }
    }
    return $null
}

Write-Host "[setup] Checking for Python..." -ForegroundColor Cyan
$py = Resolve-PythonExe
if (-not $py) {
    Write-Error "No suitable Python found. Please install Python 3.11+ from https://www.python.org/downloads/ and re-run this script."
}

$venvPath = Join-Path -Path (Get-Location) -ChildPath ".venv"
$venvPython = Join-Path -Path $venvPath -ChildPath "Scripts/python.exe"

function Test-VenvPython {
    param([string] $Exe)
    try {
        & $Exe -V *> $null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

if (Test-Path $venvPython) {
    if (Test-VenvPython -Exe $venvPython) {
        Write-Host "[setup] Using existing venv: $venvPath" -ForegroundColor Green
    } else {
        Write-Warning "[setup] Existing venv appears broken. Recreating..."
        try { Remove-Item -Recurse -Force $venvPath } catch { }
        Write-Host "[setup] Creating venv..." -ForegroundColor Cyan
        if ($py.kind -eq 'py') { & py $py.arg -m venv .venv } else { & $py.path -m venv .venv }
    }
} else {
    Write-Host "[setup] Creating venv..." -ForegroundColor Cyan
    if ($py.kind -eq 'py') { & py $py.arg -m venv .venv } else { & $py.path -m venv .venv }
}

Write-Host "[setup] Upgrading pip..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip

$lock = Join-Path -Path (Get-Location) -ChildPath "requirements.lock.txt"
$req = Join-Path -Path (Get-Location) -ChildPath "requirements.txt"

if (Test-Path $lock) {
    Write-Host "[setup] Installing dependencies from requirements.lock.txt..." -ForegroundColor Cyan
    & $venvPython -m pip install -r $lock
} elseif (Test-Path $req) {
    Write-Host "[setup] Installing dependencies from requirements.txt..." -ForegroundColor Cyan
    & $venvPython -m pip install -r $req
} else {
    Write-Warning "No requirements file found. Skipping package installation."
}

Write-Host "[setup] Done." -ForegroundColor Green
