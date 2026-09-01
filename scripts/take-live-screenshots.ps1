[CmdletBinding()]
param(
    [string]$OutputDir,
    [string]$AdbPath,
    [string]$DeviceSerial,
    [string]$ConnectEndpoint,
    [string]$ApkPath,
    [switch]$IncludeAdmin
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $repoRoot "docs\evidence\screenshots\$stamp"
}
if (-not $ApkPath) {
    $ApkPath = Join-Path $repoRoot "app\build\outputs\apk\debug\app-debug.apk"
}

function Resolve-Adb {
    $candidates = @()
    if ($AdbPath) { $candidates += $AdbPath }
    $command = Get-Command adb -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "adb was not found. Pass -AdbPath or install Android SDK Platform Tools."
}

$script:AdbExecutable = Resolve-Adb

function Invoke-Adb {
    param([string[]]$Arguments)

    # Windows PowerShell 5.1 turns every stderr line from a native executable
    # into an ErrorRecord, and with $ErrorActionPreference = "Stop" that is
    # fatal even when the exe exits 0. `adb pull` writes its transfer progress
    # to stderr, so the screenshot pass died on a successful pull. Relax the
    # preference only around the call; the exit-code check below is what
    # actually decides whether adb failed.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = @(& $script:AdbExecutable @Arguments 2>&1)
    } finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($LASTEXITCODE -ne 0) {
        $message = ($output | ForEach-Object { $_.ToString() }) -join "`n"
        throw "adb failed ($($Arguments -join ' ')): $message"
    }
    return $output
}

if ($ConnectEndpoint) {
    Invoke-Adb -Arguments @("connect", $ConnectEndpoint) | Out-Host
}

$deviceLines = Invoke-Adb -Arguments @("devices")
$connected = @(
    $deviceLines |
        ForEach-Object { $_.ToString().Trim() } |
        Where-Object { $_ -match "^(\S+)\s+device$" } |
        ForEach-Object { ($_ -split "\s+")[0] }
)

if ($DeviceSerial) {
    if ($DeviceSerial -notin $connected) {
        throw "Device '$DeviceSerial' is not connected and ready."
    }
    $serial = $DeviceSerial
} elseif ($connected.Count -eq 1) {
    $serial = $connected[0]
} elseif ($connected.Count -eq 0) {
    throw "No ready Android device found. Start one or pass -ConnectEndpoint."
} else {
    throw "Multiple devices are ready ($($connected -join ', ')). Pass -DeviceSerial."
}

$boot = ""
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    $boot = (Invoke-Adb -Arguments @("-s", $serial, "shell", "getprop", "sys.boot_completed")) -join ""
    if ($boot.Trim() -eq "1") { break }
    Start-Sleep -Seconds 2
}
if ($boot.Trim() -ne "1") {
    throw "Android did not finish booting within 60 seconds."
}
if (-not (Test-Path -LiteralPath $ApkPath -PathType Leaf)) {
    throw "Debug APK not found: $ApkPath"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
Invoke-Adb -Arguments @("-s", $serial, "install", "-r", $ApkPath) | Out-Host
Invoke-Adb -Arguments @(
    "-s", $serial, "shell", "am", "start", "-W", "-n",
    "com.cretona.app.debug/com.cretona.app.MainActivity"
) | Out-Host
Start-Sleep -Seconds 3

$remoteXml = "/sdcard/cretona-window.xml"
$localXml = Join-Path $OutputDir ".window.xml"

function Get-WindowNodes {
    Invoke-Adb -Arguments @("-s", $serial, "shell", "uiautomator", "dump", $remoteXml) |
        Out-Null
    Invoke-Adb -Arguments @("-s", $serial, "pull", $remoteXml, $localXml) | Out-Null
    [xml]$document = Get-Content -LiteralPath $localXml -Raw
    return @($document.SelectNodes("//node"))
}

function Find-UiNode {
    param([string]$Label)

    foreach ($node in Get-WindowNodes) {
        $text = [string]$node.text
        $description = [string]$node.'content-desc'
        if ($text.Equals($Label, [StringComparison]::OrdinalIgnoreCase) -or
            $description.Equals($Label, [StringComparison]::OrdinalIgnoreCase)) {
            return $node
        }
    }
    return $null
}

function Tap-UiLabel {
    param([string]$Label)

    $node = Find-UiNode -Label $Label
    if (-not $node) { throw "UI element '$Label' was not found." }
    $bounds = [string]$node.bounds
    if ($bounds -notmatch "\[(\d+),(\d+)\]\[(\d+),(\d+)\]") {
        throw "UI element '$Label' has invalid bounds '$bounds'."
    }
    $x = [int](([int]$Matches[1] + [int]$Matches[3]) / 2)
    $y = [int](([int]$Matches[2] + [int]$Matches[4]) / 2)
    Invoke-Adb -Arguments @("-s", $serial, "shell", "input", "tap", "$x", "$y") | Out-Null
    Start-Sleep -Seconds 2
}

function Save-Screenshot {
    param([string]$Name)

    $remote = "/sdcard/$Name.png"
    $local = Join-Path $OutputDir "$Name.png"
    Invoke-Adb -Arguments @("-s", $serial, "shell", "screencap", "-p", $remote) | Out-Null
    Invoke-Adb -Arguments @("-s", $serial, "pull", $remote, $local) | Out-Null
    $file = Get-Item -LiteralPath $local
    if ($file.Length -le 1024) { throw "Screenshot '$local' is unexpectedly small." }
    Write-Host "Captured $local"
}

if (-not (Find-UiNode -Label "Home")) {
    throw "The signed-in Home shell is not visible. Sign in, then run this script again."
}

Save-Screenshot -Name "live_screen_01_home"
Tap-UiLabel -Label "History"
Save-Screenshot -Name "live_screen_02_history"
Tap-UiLabel -Label "Credits"
Save-Screenshot -Name "live_screen_03_credits"
Tap-UiLabel -Label "Profile"
Save-Screenshot -Name "live_screen_04_profile"

if ($IncludeAdmin) {
    Tap-UiLabel -Label "Admin"
    Save-Screenshot -Name "live_screen_05_admin"
    Invoke-Adb -Arguments @("-s", $serial, "shell", "input", "keyevent", "4") | Out-Null
    Start-Sleep -Seconds 2
}

Tap-UiLabel -Label "Home"
Remove-Item -LiteralPath $localXml -Force -ErrorAction SilentlyContinue
Write-Host "Screenshot pass completed successfully: $OutputDir"
