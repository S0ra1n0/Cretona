[CmdletBinding()]
param(
    [ValidateSet('dev', 'live')]
    [string]$Profile = 'dev',
    [switch]$RealAuth,
    [switch]$SkipPreflight
)

<#
.SYNOPSIS
    One-click runner for the Cretona project with mandatory PC resource checks.

.DESCRIPTION
    1. Runs the PC Hardware & Environment Diagnostics tool to profile resources.
    2. Auto-tunes .env to match the PC's CPU/RAM/GPU capabilities.
    3. Boots the Cretona backend server (dev SQLite or live Supabase profile).

.EXAMPLE
    .\scripts\run-all.ps1
    .\scripts\run-all.ps1 -Profile live
    .\scripts\run-all.ps1 -RealAuth
#>

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " 🚀 STARTING CRETONA PROJECT (PROFILE: $Profile)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. MANDATORY PREFLIGHT HARDWARE DIAGNOSTICS & TUNING
if (-not $SkipPreflight) {
    & (Join-Path $PSScriptRoot 'check-pc-env.ps1') -AutoTune
}

# 2. RUN BACKEND SERVER
if ($Profile -eq 'live') {
    Write-Host "`n[STARTING LIVE BACKEND]" -ForegroundColor Green
    & (Join-Path $PSScriptRoot 'run-fastapi.ps1') -SkipPreflight
} else {
    Write-Host "`n[STARTING DEV BACKEND]" -ForegroundColor Green
    $params = @{ SkipPreflight = $true }
    if ($RealAuth) {
        $params['RealAuth'] = $true
    }
    & (Join-Path $PSScriptRoot 'run-dev-backend.ps1') @params
}
