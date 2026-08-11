[CmdletBinding()]
param(
    [ValidateSet('general', 'framepack')]
    [string]$Profile = 'general',
    [double]$MinimumFreeRamGiB = 6,
    [double]$MinimumFreeVramGiB = 6,
    [double]$MinimumFreeDiskGiB = 100,
    [double]$MinimumFreeVirtualGiB = 0,
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Find-OllamaExecutable {
    $command = Get-Command ollama -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        return $command.Source
    }

    $projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
    $candidates = @(
        (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Ollama\ollama.exe'),
        (Join-Path (Split-Path $projectRoot -Parent) '.tools\Ollama\ollama.exe')
    )
    return $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

$os = Get-CimInstance Win32_OperatingSystem
$freeRamGiB = [math]::Round(($os.FreePhysicalMemory * 1KB) / 1GB, 2)
$freeVirtualGiB = [math]::Round(($os.FreeVirtualMemory * 1KB) / 1GB, 2)
if ($Profile -eq 'framepack' -and $MinimumFreeVirtualGiB -eq 0) {
    # The pinned FramePack manifest contains about 42.9 GB of model files that
    # the official launcher initially materializes as CPU modules. Leave a
    # small margin for Python, CUDA, the OS, and generation tensors.
    $MinimumFreeVirtualGiB = 48
}

$gpuLine = & nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,power.draw --format=csv,noheader,nounits
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gpuLine)) {
    throw 'nvidia-smi did not return a GPU resource row.'
}
$gpuValues = $gpuLine.Split(',') | ForEach-Object { $_.Trim() }
$freeVramGiB = [math]::Round(([double]$gpuValues[3]) / 1024, 2)
$drive = Get-PSDrive -Name D
$freeDiskGiB = [math]::Round($drive.Free / 1GB, 2)

$battery = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
$onAcPower = if ($battery) { $battery.BatteryStatus -in @(2, 3, 6, 7, 8, 9, 11) } else { $true }

$ollama = Find-OllamaExecutable
$loadedOllamaModels = @()
if ($ollama) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $loadedOutput = & $ollama ps 2>&1
        if ($LASTEXITCODE -eq 0) {
            $loadedOllamaModels = @($loadedOutput | Select-Object -Skip 1 | Where-Object { -not [string]::IsNullOrWhiteSpace($_.ToString()) })
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

$checks = [ordered]@{
    acPower = $onAcPower
    freeRam = $freeRamGiB -ge $MinimumFreeRamGiB
    freeVram = $freeVramGiB -ge $MinimumFreeVramGiB
    freeDisk = $freeDiskGiB -ge $MinimumFreeDiskGiB
    freeVirtualMemory = $MinimumFreeVirtualGiB -eq 0 -or $freeVirtualGiB -ge $MinimumFreeVirtualGiB
    noLoadedOllamaModel = $loadedOllamaModels.Count -eq 0
}
$passed = -not ($checks.Values -contains $false)

$evidence = [ordered]@{
    schemaVersion = '1.1'
    experimentId = 'EXP-005'
    profile = $Profile
    capturedAt = (Get-Date).ToUniversalTime().ToString('o')
    host = [ordered]@{
        gpuName = $gpuValues[0]
        gpuVramTotalMiB = [double]$gpuValues[1]
        gpuVramUsedMiB = [double]$gpuValues[2]
        gpuVramFreeGiB = $freeVramGiB
        gpuTemperatureC = [double]$gpuValues[4]
        gpuPowerDrawW = [double]$gpuValues[5]
        physicalRamTotalGiB = [math]::Round(($os.TotalVisibleMemorySize * 1KB) / 1GB, 2)
        physicalRamFreeGiB = $freeRamGiB
        virtualMemoryTotalGiB = [math]::Round(($os.TotalVirtualMemorySize * 1KB) / 1GB, 2)
        virtualMemoryFreeGiB = $freeVirtualGiB
        driveDFreeGiB = $freeDiskGiB
        onAcPower = $onAcPower
        loadedOllamaModelCount = $loadedOllamaModels.Count
    }
    thresholds = [ordered]@{
        minimumFreeRamGiB = $MinimumFreeRamGiB
        minimumFreeVramGiB = $MinimumFreeVramGiB
        minimumFreeDiskGiB = $MinimumFreeDiskGiB
        minimumFreeVirtualGiB = $MinimumFreeVirtualGiB
    }
    checks = $checks
    passed = $passed
}

$json = $evidence | ConvertTo-Json -Depth 6
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $resolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
    $parent = Split-Path $resolvedOutput -Parent
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    [IO.File]::WriteAllText($resolvedOutput, $json, [Text.UTF8Encoding]::new($false))
}
$json

if (-not $passed) {
    throw 'EXP-005 preflight failed. Do not start video inference.'
}
