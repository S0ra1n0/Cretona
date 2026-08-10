[CmdletBinding()]
param(
    [string]$JavaHome,
    [string]$AndroidSdk
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$failures = [System.Collections.Generic.List[string]]::new()
$results = [System.Collections.Generic.List[object]]::new()

function Add-Result {
    param(
        [string]$Tool,
        [bool]$Available,
        [string]$Evidence,
        [bool]$Required = $true
    )
    $results.Add([pscustomobject]@{
        Tool = $Tool
        Required = $Required
        Status = if ($Available) { 'PASS' } elseif ($Required) { 'FAIL' } else { 'OPTIONAL' }
        Evidence = $Evidence
    })
    if ($Required -and -not $Available) {
        $failures.Add($Tool)
    }
}

function Resolve-Executable {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) {
        return $null
    }
    $item = Get-Item -LiteralPath $command.Source -Force
    if ($item.LinkType -eq 'SymbolicLink' -and $item.Target) {
        return [string]$item.Target[0]
    }
    return $command.Source
}

function Invoke-Probe {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    # Several version commands (notably java and ffmpeg) deliberately write
    # normal version text to stderr. Do not let the script-wide Stop policy
    # misclassify that output as a failed tool.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $line = $output |
        ForEach-Object { $_.ToString() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -First 1
    return [pscustomobject]@{ ExitCode = $exitCode; Line = $line }
}

$rtk = Resolve-Executable 'rtk'
if ($rtk) {
    $probe = Invoke-Probe $rtk @('--version')
    Add-Result 'RTK' ($probe.ExitCode -eq 0) "$($probe.Line) at $rtk"
} else {
    Add-Result 'RTK' $false 'Install the official Windows release into a PATH directory.'
}

$git = Resolve-Executable 'git'
if ($git) {
    $probe = Invoke-Probe $git @('--version')
    Add-Result 'Git' ($probe.ExitCode -eq 0) "$($probe.Line) at $git"
} else {
    Add-Result 'Git' $false 'Git is required for the two-developer workflow.'
}

$python = Resolve-Executable 'python'
if ($python) {
    $probe = Invoke-Probe $python @('--version')
    Add-Result 'Python' ($probe.ExitCode -eq 0) "$($probe.Line) at $python"
} else {
    Add-Result 'Python' $false 'Python 3.12+ is required.'
}

$fastApiPython = Join-Path $projectRoot 'backend-fastapi\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $fastApiPython) {
    $probe = Invoke-Probe $fastApiPython @('-c', 'import fastapi; print(fastapi.__version__)')
    Add-Result 'FastAPI venv' ($probe.ExitCode -eq 0) "FastAPI $($probe.Line)"
} else {
    Add-Result 'FastAPI venv' $false 'Run the venv/install commands in backend-fastapi/README.md.'
}

$defaultAndroidJbr = Join-Path $env:ProgramFiles 'Android\Android Studio\jbr'
if (-not [string]::IsNullOrWhiteSpace($JavaHome)) {
    $resolvedJavaHome = $JavaHome
} else {
    $resolvedJavaHome = @($env:JAVA_HOME, $defaultAndroidJbr) |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and
            (Test-Path -LiteralPath (Join-Path $_ 'bin\java.exe'))
        } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($resolvedJavaHome)) {
        $resolvedJavaHome = $defaultAndroidJbr
    }
}
$jbr = Join-Path $resolvedJavaHome 'bin\java.exe'
if (Test-Path -LiteralPath $jbr) {
    $probe = Invoke-Probe $jbr @('-version')
    Add-Result 'Android JDK' ($probe.ExitCode -eq 0) "$($probe.Line) at $jbr"
} else {
    Add-Result 'Android JDK' $false "Not found at $jbr; pass -JavaHome or set JAVA_HOME."
}

$defaultAndroidSdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
if (-not [string]::IsNullOrWhiteSpace($AndroidSdk)) {
    $resolvedAndroidSdk = $AndroidSdk
} else {
    $resolvedAndroidSdk = @($env:ANDROID_SDK_ROOT, $env:ANDROID_HOME, $defaultAndroidSdk) |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and
            (Test-Path -LiteralPath $_)
        } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($resolvedAndroidSdk)) {
        $resolvedAndroidSdk = $defaultAndroidSdk
    }
}
Add-Result 'Android SDK' (Test-Path -LiteralPath $resolvedAndroidSdk) $resolvedAndroidSdk
Add-Result 'Gradle wrapper' (Test-Path -LiteralPath (Join-Path $projectRoot 'gradlew.bat')) 'Repository wrapper'

$adb = Join-Path $resolvedAndroidSdk 'platform-tools\adb.exe'
if (Test-Path -LiteralPath $adb) {
    $probe = Invoke-Probe $adb @('version')
    Add-Result 'ADB device evidence' ($probe.ExitCode -eq 0) "$($probe.Line) at $adb" $false
} else {
    Add-Result 'ADB device evidence' $false 'Optional for emulator/device end-to-end evidence.' $false
}

$emulator = Join-Path $resolvedAndroidSdk 'emulator\emulator.exe'
Add-Result 'Android emulator' (Test-Path -LiteralPath $emulator) $emulator $false

foreach ($name in @('ffmpeg', 'ffprobe')) {
    $executable = Resolve-Executable $name
    if ($executable -and (Test-Path -LiteralPath $executable)) {
        $probe = Invoke-Probe $executable @('-version')
        Add-Result $name ($probe.ExitCode -eq 0) "$($probe.Line) at $executable" $false
    } else {
        Add-Result $name $false 'Optional; required only to regenerate/inspect media fixtures.' $false
    }
}

$node = Resolve-Executable 'node'
if ($node) {
    $probe = Invoke-Probe $node @('--version')
    Add-Result 'Node.js reference backend' ($probe.ExitCode -eq 0) "$($probe.Line)" $false
} else {
    Add-Result 'Node.js reference backend' $false 'Optional while backend/ remains migration evidence.' $false
}

$npm = Resolve-Executable 'npm.cmd'
if ($npm) {
    $probe = Invoke-Probe $npm @('--version')
    Add-Result 'npm reference backend' ($probe.ExitCode -eq 0) "$($probe.Line) at $npm" $false
} else {
    Add-Result 'npm reference backend' $false 'Optional while backend/ remains migration evidence.' $false
}

$results | Format-Table -AutoSize
if ($failures.Count -gt 0) {
    throw "Required toolchain checks failed: $($failures -join ', ')"
}
