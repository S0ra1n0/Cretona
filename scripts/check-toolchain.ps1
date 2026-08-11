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

function Test-CompleteModelSnapshot {
    param(
        [string]$RepositoryCachePath,
        [string]$SnapshotPath,
        [string[]]$RequiredRelativePaths
    )

    if (-not (Test-Path -LiteralPath $SnapshotPath)) {
        return $false
    }
    foreach ($relativePath in $RequiredRelativePaths) {
        if (-not (Test-Path -LiteralPath (Join-Path $SnapshotPath $relativePath))) {
            return $false
        }
    }
    $incomplete = Get-ChildItem -LiteralPath $RepositoryCachePath -Recurse -File -Filter '*.incomplete' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    return $null -eq $incomplete
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

$hf = Resolve-Executable 'hf'
if ($hf) {
    $probe = Invoke-Probe $hf @('version')
    Add-Result 'Hugging Face CLI' ($probe.ExitCode -eq 0) "$($probe.Line) at $hf" $false
} else {
    Add-Result 'Hugging Face CLI' $false 'Optional; required to verify and download pinned local-model revisions.' $false
}

$uv = Resolve-Executable 'uv'
if ($uv) {
    $probe = Invoke-Probe $uv @('--version')
    Add-Result 'uv Python manager' ($probe.ExitCode -eq 0) "$($probe.Line) at $uv" $false
} else {
    Add-Result 'uv Python manager' $false 'Optional; used for isolated model-worker Python runtimes.' $false
}

$sevenZip = @(
    (Resolve-Executable '7z'),
    (Join-Path $env:ProgramFiles '7-Zip\7z.exe')
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) } |
    Select-Object -First 1
if ($sevenZip) {
    $probe = Invoke-Probe $sevenZip @('i')
    Add-Result '7-Zip' ($probe.ExitCode -eq 0) "$($probe.Line) at $sevenZip" $false
} else {
    Add-Result '7-Zip' $false 'Optional; used to verify and extract the official FramePack Windows package.' $false
}

$ollama = Resolve-Executable 'ollama'
if (-not $ollama) {
    $ollama = @(
        (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Ollama\ollama.exe'),
        (Join-Path (Split-Path $projectRoot -Parent) '.tools\Ollama\ollama.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if ($ollama) {
    $probe = Invoke-Probe $ollama @('--version')
    Add-Result 'Ollama' ($probe.ExitCode -eq 0) "$($probe.Line) at $ollama" $false

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $ollamaList = & $ollama list 2>&1
        $ollamaListExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $qwenTag = 'qwen3:4b-instruct-2507-q4_K_M'
    $matchingQwenRows = @(
        $ollamaList |
            ForEach-Object { $_.ToString() } |
            Where-Object { $_ -match "^$([regex]::Escape($qwenTag))\s" }
    )
    $hasQwen = $ollamaListExitCode -eq 0 -and $matchingQwenRows.Count -gt 0
    Add-Result 'Qwen prompt model' $hasQwen $qwenTag $false
} else {
    Add-Result 'Ollama' $false 'Optional; required for real local prompt enhancement.' $false
    Add-Result 'Qwen prompt model' $false 'Pull qwen3:4b-instruct-2507-q4_K_M after Ollama is installed.' $false
}

$ollamaModelRoot = [Environment]::GetEnvironmentVariable('OLLAMA_MODELS', 'User')
$hfHome = [Environment]::GetEnvironmentVariable('HF_HOME', 'User')
$torchHome = [Environment]::GetEnvironmentVariable('TORCH_HOME', 'User')
Add-Result 'Ollama model root on D' (
    -not [string]::IsNullOrWhiteSpace($ollamaModelRoot) -and
    $ollamaModelRoot.StartsWith('D:\', [StringComparison]::OrdinalIgnoreCase)
) $(if ($ollamaModelRoot) { $ollamaModelRoot } else { 'Set user OLLAMA_MODELS to a bounded drive-D directory.' }) $false
Add-Result 'Hugging Face cache on D' (
    -not [string]::IsNullOrWhiteSpace($hfHome) -and
    $hfHome.StartsWith('D:\', [StringComparison]::OrdinalIgnoreCase)
) $(if ($hfHome) { $hfHome } else { 'Set user HF_HOME to a bounded drive-D directory.' }) $false
Add-Result 'Torch cache on D' (
    -not [string]::IsNullOrWhiteSpace($torchHome) -and
    $torchHome.StartsWith('D:\', [StringComparison]::OrdinalIgnoreCase)
) $(if ($torchHome) { $torchHome } else { 'Set user TORCH_HOME to a bounded drive-D directory.' }) $false

$framePackRoot = Join-Path (Split-Path $projectRoot -Parent) '.ai-runtimes\framepack_cu126_torch26'
$framePackWebUi = Join-Path $framePackRoot 'webui'
$framePackPython = Join-Path $framePackRoot 'system\python\python.exe'
if ((Test-Path -LiteralPath (Join-Path $framePackWebUi '.git')) -and $git) {
    $probe = Invoke-Probe $git @('-c', "safe.directory=$framePackWebUi", '-C', $framePackWebUi, 'rev-parse', 'HEAD')
    Add-Result 'FramePack source revision' (
        $probe.ExitCode -eq 0 -and $probe.Line -eq '97fe5dbe06ac1f337ece08935b1076a35eefeeb9'
    ) "expected 97fe5dbe06ac1f337ece08935b1076a35eefeeb9; observed $($probe.Line)" $false
} else {
    Add-Result 'FramePack source revision' $false "Optional runtime not found at $framePackWebUi" $false
}
if (Test-Path -LiteralPath $framePackPython) {
    $probe = Invoke-Probe $framePackPython @(
        '-c',
        "import torch; print(f'Python CUDA runtime: torch={torch.__version__}; cuda={torch.version.cuda}; available={torch.cuda.is_available()}')"
    )
    Add-Result 'FramePack Python/CUDA' ($probe.ExitCode -eq 0) $probe.Line $false
} else {
    Add-Result 'FramePack Python/CUDA' $false "Optional runtime not found at $framePackPython" $false
}

$framePackSnapshots = @(
    @{
        Name = 'FramePack F1 weights'
        Repo = 'models--lllyasviel--FramePack_F1_I2V_HY_20250503'
        Revision = 'ab239828e0b384fed75580f186f078717d4020f7'
        Files = @(
            'diffusion_pytorch_model-00001-of-00003.safetensors',
            'diffusion_pytorch_model-00002-of-00003.safetensors',
            'diffusion_pytorch_model-00003-of-00003.safetensors',
            'diffusion_pytorch_model.safetensors.index.json'
        )
    },
    @{
        Name = 'Hunyuan support weights'
        Repo = 'models--hunyuanvideo-community--HunyuanVideo'
        Revision = 'e8c2aaa66fe3742a32c11a6766aecbf07c56e773'
        Files = @(
            'text_encoder/model-00001-of-00004.safetensors',
            'text_encoder/model-00002-of-00004.safetensors',
            'text_encoder/model-00003-of-00004.safetensors',
            'text_encoder/model-00004-of-00004.safetensors',
            'text_encoder_2/model.safetensors',
            'vae/diffusion_pytorch_model.safetensors'
        )
    },
    @{
        Name = 'FramePack image encoder'
        Repo = 'models--lllyasviel--flux_redux_bfl'
        Revision = '45b801affc54ff2af4e5daf1b282e0921901db87'
        Files = @('image_encoder/model.safetensors')
    }
)
foreach ($snapshot in $framePackSnapshots) {
    $repositoryCachePath = Join-Path $framePackWebUi "hf_download\$($snapshot.Repo)"
    $snapshotPath = Join-Path $repositoryCachePath "snapshots\$($snapshot.Revision)"
    $complete = Test-CompleteModelSnapshot $repositoryCachePath $snapshotPath $snapshot.Files
    Add-Result $snapshot.Name $complete $snapshotPath $false
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
