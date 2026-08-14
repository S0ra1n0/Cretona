[CmdletBinding()]
param(
    [string]$EnvFile,
    [ValidateSet('all', 'security', 'performance')]
    [string]$Type = 'all',
    [ValidateSet('info', 'warn', 'error')]
    [string]$Level = 'info',
    [string]$SupabaseCliVersion = '2.114.0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $projectRoot 'env'
}
$envPath = (Resolve-Path -LiteralPath $EnvFile).Path

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    foreach ($line in [IO.File]::ReadLines($Path)) {
        if ($line -notmatch '^\s*([^#][^=]*)=(.*)$') {
            continue
        }
        if ($matches[1].Trim() -ne $Name) {
            continue
        }

        $value = $matches[2].Trim()
        if (
            $value.Length -ge 2 -and
            (($value[0] -eq '"' -and $value[-1] -eq '"') -or
             ($value[0] -eq "'" -and $value[-1] -eq "'"))
        ) {
            return $value.Substring(1, $value.Length - 2)
        }
        return $value
    }

    throw "Required key $Name is missing from the selected env file."
}

$supabaseUrl = Get-DotEnvValue $envPath 'SUPABASE_URL'
$directUrl = Get-DotEnvValue $envPath 'DIRECT_URL'

$projectUri = $null
if (
    -not [Uri]::TryCreate($supabaseUrl, [UriKind]::Absolute, [ref]$projectUri) -or
    -not $projectUri.Host.EndsWith('.supabase.co', [StringComparison]::OrdinalIgnoreCase)
) {
    throw 'SUPABASE_URL is not a valid Supabase project URL.'
}
$projectRef = $projectUri.Host.Split('.')[0]

$databaseUri = $null
if (
    -not [Uri]::TryCreate($directUrl, [UriKind]::Absolute, [ref]$databaseUri) -or
    $databaseUri.Scheme -notin @('postgres', 'postgresql')
) {
    throw 'DIRECT_URL is not a valid PostgreSQL connection string.'
}
$databaseUser = [Uri]::UnescapeDataString($databaseUri.UserInfo.Split(':', 2)[0])
$hostMatches = $databaseUri.Host.Equals(
    "db.$projectRef.supabase.co",
    [StringComparison]::OrdinalIgnoreCase
)
$poolerUserMatches = $databaseUser.EndsWith(
    ".$projectRef",
    [StringComparison]::OrdinalIgnoreCase
)
if (-not ($hostMatches -or $poolerUserMatches)) {
    throw 'DIRECT_URL does not match the project identity from SUPABASE_URL.'
}

$npx = Get-Command 'npx.cmd' -ErrorAction Stop | Select-Object -First 1
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $rawOutput = & $npx.Source --yes "supabase@$SupabaseCliVersion" `
        db advisors `
        --db-url $directUrl `
        --type $Type `
        --level $Level `
        --fail-on none `
        --output-format json 2>&1
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}

$output = $rawOutput -join [Environment]::NewLine
$password = if ($databaseUri.UserInfo.Contains(':')) {
    [Uri]::UnescapeDataString($databaseUri.UserInfo.Split(':', 2)[1])
} else {
    ''
}
if ($output.Contains($directUrl)) {
    throw 'Advisor output contained the database URL; output withheld.'
}
if ($password.Length -ge 8 -and $output.Contains($password)) {
    throw 'Advisor output contained the database password; output withheld.'
}
if ($exitCode -ne 0) {
    throw "Supabase Advisors failed with exit code $exitCode. Output withheld to protect connection details."
}

$output
