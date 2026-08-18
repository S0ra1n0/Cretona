[CmdletBinding()]
param(
    [switch]$AutoTune
)

<#
.SYNOPSIS
    Diagnoses PC Hardware Resources, Runtimes, and Tooling for the Cretona project.

.DESCRIPTION
    Checks CPU, RAM, Pagefile, GPU/VRAM, Disk, Python, FFmpeg, Ollama, Java, and Android SDK,
    recommending the optimal AI tier (Mock, Cloud AI, Local Model) and auto-tuning .env.

.EXAMPLE
    .\scripts\check-pc-env.ps1
    .\scripts\check-pc-env.ps1 -AutoTune
#>

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$script = Join-Path $projectRoot 'scripts\check-system-resources.py'

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[WARN] FastAPI virtualenv not found at backend\.venv. Falling back to system python..." -ForegroundColor Yellow
    $python = 'python'
}

$argsList = @($script)
if ($AutoTune) {
    $argsList += '--auto-tune'
}

& $python @argsList
