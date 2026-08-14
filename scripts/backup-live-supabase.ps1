[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$OutputRoot,
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

function Test-FileContainsLiteral {
    param(
        [string]$Path,
        [string]$Literal
    )

    if ([string]::IsNullOrEmpty($Literal)) {
        return $false
    }
    foreach ($line in [IO.File]::ReadLines($Path)) {
        if ($line.Contains($Literal)) {
            return $true
        }
    }
    return $false
}

function Protect-BackupDirectory {
    param([string]$Path)

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $systemSid = [Security.Principal.SecurityIdentifier]::new(
        [Security.Principal.WellKnownSidType]::LocalSystemSid,
        $null
    )
    $administratorsSid = [Security.Principal.SecurityIdentifier]::new(
        [Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid,
        $null
    )
    $inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    $propagation = [Security.AccessControl.PropagationFlags]::None
    $allow = [Security.AccessControl.AccessControlType]::Allow

    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($identity.User)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($identity.User, $systemSid, $administratorsSid)) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            $inheritance,
            $propagation,
            $allow
        )
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
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

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path (Split-Path $projectRoot -Parent) 'Cretona-backups'
}
$resolvedOutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$projectPrefix = $projectRoot + [IO.Path]::DirectorySeparatorChar
if (
    $resolvedOutputRoot.Equals($projectRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $resolvedOutputRoot.StartsWith($projectPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw 'Backup output must be outside the Git repository.'
}

$npx = Get-Command 'npx.cmd' -ErrorAction Stop | Select-Object -First 1
$docker = Get-Command 'docker' -ErrorAction Stop | Select-Object -First 1
$dockerVersion = & $docker.Source version --format '{{.Server.Version}}' 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($dockerVersion)) {
    throw 'Docker Desktop is not ready; Supabase CLI cannot run pg_dump.'
}

New-Item -ItemType Directory -Path $resolvedOutputRoot -Force | Out-Null
$timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$backupDirectory = Join-Path $resolvedOutputRoot $timestamp
if (Test-Path -LiteralPath $backupDirectory) {
    throw "Refusing to overwrite existing backup directory $backupDirectory"
}
New-Item -ItemType Directory -Path $backupDirectory | Out-Null
Protect-BackupDirectory $backupDirectory

function Invoke-SupabaseDump {
    param(
        [string]$Label,
        [string[]]$DumpArguments
    )

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $null = & $npx.Source --yes "supabase@$SupabaseCliVersion" @DumpArguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "Supabase CLI $Label dump failed with exit code $exitCode. Output withheld to protect connection details."
    }
}

$rolesPath = Join-Path $backupDirectory 'roles.sql'
$schemaPath = Join-Path $backupDirectory 'schema.sql'
$dataPath = Join-Path $backupDirectory 'data.sql'

Invoke-SupabaseDump 'roles' @(
    'db', 'dump', '--db-url', $directUrl, '--file', $rolesPath, '--role-only'
)
Invoke-SupabaseDump 'schema' @(
    'db', 'dump', '--db-url', $directUrl, '--file', $schemaPath
)
Invoke-SupabaseDump 'data' @(
    'db', 'dump', '--db-url', $directUrl, '--file', $dataPath,
    '--use-copy', '--data-only',
    '--exclude', 'storage.buckets_vectors',
    '--exclude', 'storage.vector_indexes'
)

$password = if ($databaseUri.UserInfo.Contains(':')) {
    [Uri]::UnescapeDataString($databaseUri.UserInfo.Split(':', 2)[1])
} else {
    ''
}
$files = foreach ($path in @($rolesPath, $schemaPath, $dataPath)) {
    $item = Get-Item -LiteralPath $path
    if ($item.Length -eq 0) {
        throw "Backup artifact $($item.Name) is empty."
    }
    if (Test-FileContainsLiteral $item.FullName $directUrl) {
        throw "Backup artifact $($item.Name) contains the database URL."
    }
    if ($password.Length -ge 8 -and (Test-FileContainsLiteral $item.FullName $password)) {
        throw "Backup artifact $($item.Name) contains the database password."
    }

    [ordered]@{
        name = $item.Name
        bytes = $item.Length
        sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$manifest = [ordered]@{
    schemaVersion = '1.0'
    createdAt = (Get-Date).ToUniversalTime().ToString('o')
    projectRef = $projectRef
    supabaseCliVersion = $SupabaseCliVersion
    dockerServerVersion = $dockerVersion.Trim()
    backupDirectory = $backupDirectory
    files = @($files)
    storageObjectBytesIncluded = $false
    notes = @(
        'roles.sql, schema.sql, and data.sql follow the Supabase CLI backup guide.',
        'The database dump contains Storage metadata, not the bytes stored by the Storage API.',
        'The backup directory disables inherited ACLs and grants full control only to the current user, local SYSTEM, and builtin Administrators.',
        'Restore execution is not part of this backup command.'
    )
}
$manifestPath = Join-Path $backupDirectory 'manifest.json'
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 6),
    [Text.UTF8Encoding]::new($false)
)

$manifest | ConvertTo-Json -Depth 6
