<#
.SYNOPSIS
Sign in to the live Supabase project and write the access token to backend/.token.

.DESCRIPTION
verify-live-runtime.py needs a Supabase access token. Getting one means signing
in as a real user, which needs a password -- so this prompts for it rather than
taking it as an argument, and never echoes or stores it.

The token is written straight to backend/.token (git-ignored) instead of being
printed, so it never reaches the terminal or ConsoleHost_history.txt.

SUPABASE_URL is read from backend/.env. The anon key is not in that file, so
pass it once with -AnonKey, or set CRETONA_SUPABASE_ANON_KEY.

Find the anon key at:
  Supabase Dashboard -> your project -> Project Settings -> API Keys
  -> "anon" / "public". It is safe to use here: it is the key the mobile app
  itself ships with, and it grants nothing on its own.

.EXAMPLE
  .\scripts\get-live-token.ps1 -Email user@cretona.test -AnonKey eyJhbGci...

.EXAMPLE
  $env:CRETONA_SUPABASE_ANON_KEY = 'eyJhbGci...'
  .\scripts\get-live-token.ps1
#>
[CmdletBinding()]
param(
    [string]$Email,
    [string]$AnonKey,
    [string]$EnvFile,
    [string]$OutFile
)

$ErrorActionPreference = 'Stop'

# Resolved here rather than as param defaults: under `powershell.exe -File`,
# $PSScriptRoot is empty while the param block is being bound, which silently
# turns the default into a relative path off the caller's directory.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $EnvFile) { $EnvFile = Join-Path $scriptDir '..\backend\.env' }
if (-not $OutFile) { $OutFile = Join-Path $scriptDir '..\backend\.token' }

function Get-EnvValue {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path $Path)) { throw "Env file not found: $Path" }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        $split = $trimmed.IndexOf('=')
        if ($split -lt 1) { continue }
        if ($trimmed.Substring(0, $split).Trim() -ne $Key) { continue }
        $value = $trimmed.Substring($split + 1).Trim()
        if ($value.Length -ge 2 -and $value[0] -eq $value[-1] -and ($value[0] -eq '"' -or $value[0] -eq "'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        return $value
    }
    return ''
}

$supabaseUrl = Get-EnvValue -Path $EnvFile -Key 'SUPABASE_URL'
if (-not $supabaseUrl) { $supabaseUrl = Get-EnvValue -Path $EnvFile -Key 'CRETONA_SUPABASE_URL' }
if (-not $supabaseUrl) { throw "SUPABASE_URL is not set in $EnvFile" }
$supabaseUrl = $supabaseUrl.TrimEnd('/')
Write-Host "project  : $supabaseUrl"

if (-not $AnonKey) { $AnonKey = $env:CRETONA_SUPABASE_ANON_KEY }
if (-not $AnonKey) {
    Write-Host ''
    Write-Host 'The anon key is needed to sign in, and is not in backend/.env.'
    Write-Host 'Get it from: Supabase Dashboard -> Project Settings -> API Keys -> "anon" / "public"'
    Write-Host ''
    $AnonKey = Read-Host -Prompt 'anon key'
}
$AnonKey = $AnonKey.Trim()
if (-not $AnonKey) { throw 'No anon key supplied.' }

if (-not $Email) { $Email = Read-Host -Prompt 'email' }
$Email = $Email.Trim()
if (-not $Email) { throw 'No email supplied.' }

# -AsSecureString so it is not echoed and does not land in shell history.
$securePassword = Read-Host -Prompt "password for $Email" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$body = @{ email = $Email; password = $plainPassword } | ConvertTo-Json -Compress

try {
    $response = Invoke-RestMethod `
        -Method Post `
        -Uri "$supabaseUrl/auth/v1/token?grant_type=password" `
        -Headers @{ apikey = $AnonKey; Authorization = "Bearer $AnonKey" } `
        -ContentType 'application/json' `
        -Body $body
} catch {
    $status = ''
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
    Write-Host ''
    if ($status -eq 400) {
        Write-Host 'Sign-in refused (HTTP 400). Usually a wrong email/password, or the'
        Write-Host 'account exists but was never confirmed. In the Dashboard, check'
        Write-Host 'Authentication -> Users, and tick "Auto Confirm User" if needed.'
    } elseif ($status -eq 401) {
        Write-Host 'HTTP 401 -- the anon key was rejected. Check it is the "anon" / "public"'
        Write-Host 'key for THIS project, not another one and not the service_role key.'
    } else {
        if ($status) {
            Write-Host "Sign-in failed (HTTP $status)."
        } else {
            Write-Host 'Sign-in failed.'
        }
    }
    throw
} finally {
    $plainPassword = $null
    [GC]::Collect()
}

if (-not $response.access_token) { throw 'Sign-in succeeded but no access_token was returned.' }

# -NoNewline: the Python side strips whitespace, but a bare token is tidier.
[IO.File]::WriteAllText((New-Item -ItemType File -Path $OutFile -Force).FullName, $response.access_token)

$expiresIn = $response.expires_in
Write-Host ''
Write-Host "signed in: $($response.user.email)"
Write-Host "token     : written to $OutFile ($($response.access_token.Length) chars, not printed)"
if ($expiresIn) {
    Write-Host "expires   : in $([math]::Round($expiresIn / 60)) minutes -- re-run this script when it lapses"
}
Write-Host ''
Write-Host 'Now run:'
Write-Host '  & "C:\Users\M15R6\AndroidStudioProjects\Final_Plus\Cretona\backend\.venv\Scripts\python.exe" "C:\Users\M15R6\AndroidStudioProjects\Final_Plus\Cretona\scripts\verify-live-runtime.py"'
