[CmdletBinding()]
param(
    [string]$HostAddress = '0.0.0.0',
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$SkipPreflight
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$diagScript = Join-Path $projectRoot 'scripts\check-system-resources.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'FastAPI virtual environment is missing. Follow docs/SETUP.md first.'
}

# 1. MANDATORY PC HARDWARE & RESOURCE PREFLIGHT CHECK
if (-not $SkipPreflight -and (Test-Path -LiteralPath $diagScript)) {
    Write-Host "`n>>> Running PC Hardware & Resource Preflight Check... <<<" -ForegroundColor Cyan
    & $python $diagScript --auto-tune
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] Preflight diagnostic reported non-zero status. Proceeding to startup..." -ForegroundColor Yellow
    }
}

# 2. START FASTAPI BACKEND SERVER
Push-Location $backendRoot
try {
    Write-Host "`nStarting FastAPI server on http://${HostAddress}:${Port} (emulator: http://10.0.2.2:${Port})..." -ForegroundColor Green
    & $python -m uvicorn app.main:app --host $HostAddress --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Uvicorn exited with code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
