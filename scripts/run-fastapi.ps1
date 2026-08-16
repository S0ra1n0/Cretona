[CmdletBinding()]
param(
    [string]$HostAddress = '0.0.0.0',
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'FastAPI virtual environment is missing. Follow docs/SETUP.md first.'
}

Push-Location $backendRoot
try {
    & $python -m uvicorn app.main:app --host $HostAddress --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Uvicorn exited with code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
