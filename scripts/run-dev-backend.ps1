[CmdletBinding()]
param(
    [string]$HostAddress = '0.0.0.0',
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    # Verify real Supabase logins instead of using the fixed dev identity.
    # Still SQLite, so nothing is written to the live database -- only the
    # token is checked against Supabase, and the profile behind it is read
    # from the local seed.
    [switch]$RealAuth
)

<#
Runs FastAPI locally against SQLite, so emulator testing never writes to the
live database. backend/.env is read for Supabase URL/keys but is never
modified; the profile keys below are overridden at the process level.

Two auth modes:

  (default)   Fixed dev identity. The app sends X-Debug-User-Id when nobody
              has signed in, and the backend trusts it. No network needed for
              auth, but every session is the same user -- signing in as
              somebody else will NOT change the profile you see.

  -RealAuth   Verifies real Supabase tokens (ES256 via JWKS), so whoever signs
              in on the login screen is who the backend serves. Still SQLite:
              the token is checked against Supabase, but the profile behind it
              is read from the local seed below, and nothing is written to the
              live database. Use this to test the admin role end to end.

SQLite database and generated media both land in backend/.devdata/, which
is gitignored and disposable. Delete it any time to reset to a clean slate.
#>

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$devDataDir = Join-Path $backendRoot '.devdata'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'FastAPI virtual environment is missing. Follow docs/SETUP.md first.'
}
New-Item -ItemType Directory -Force -Path $devDataDir | Out-Null

if ($RealAuth) {
    # Real Supabase token verification (ES256 via JWKS). The algorithm, issuer
    # and project URL come from backend/.env, which is left untouched.
    $env:CRETONA_AUTH_MODE = 'supabase'
} else {
    $env:CRETONA_AUTH_MODE = 'dev'
}
$env:CRETONA_ENVIRONMENT = 'development'
$env:CRETONA_DATABASE_BACKEND = 'sqlite'
$env:CRETONA_DATABASE_PATH = '.devdata\emulator.db'
$env:CRETONA_STORAGE_BACKEND = 'local'
$env:CRETONA_DEFAULT_VIDEO_PROVIDER = 'mock'
$env:CRETONA_RATE_LIMIT_ENABLED = 'false'
$env:CRETONA_GENERATION_LOG_RETENTION_ENABLED = 'false'

Push-Location $backendRoot
try {
    # Fixed dev identity from app/config.py's dev_user_id default -- must match
    # the UUID hardcoded in NetworkModule.kt's X-Debug-User-Id header exactly.
    # Rewritten every run: idempotent (ON CONFLICT DO UPDATE), so this is cheap
    # and keeps the script self-contained rather than depending on a file that
    # has to already exist.
    $seedScript = @'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.database import Database
db = Database(pathlib.Path(__file__).resolve().parent / "emulator.db")
db.initialize()

# A token proves identity; the database decides authority (see auth.py's
# _resolved_account). So a real sign-in only resolves to the right role if a
# row with that Supabase user id exists locally too. These are the ids of the
# accounts supabase/seed_dev_users.sql creates in this project.
for user_id, email, username, role in (
    ("00000000-0000-4000-8000-000000000001", "user@cretona.test", "dev", "user"),
    ("0f2ca26d-c0cc-4093-9c80-c40460176d83", "user@cretona.test", "user", "user"),
    ("046ea264-dd97-448e-9483-a1549664baae", "admin@cretona.test", "admin", "admin"),
):
    db.upsert_user(
        user_id, email=email, username=username, role=role,
        created_at="2026-01-01T00:00:00Z",
    )
print("dev + real-auth users ready")
'@
    Set-Content -LiteralPath (Join-Path $devDataDir 'seed_dev_user.py') -Value $seedScript -Encoding utf8
    & $python (Join-Path $devDataDir 'seed_dev_user.py')

    $authLabel = if ($RealAuth) { 'supabase (real login)' } else { 'dev (fixed identity)' }
    Write-Host "Dev backend starting on http://${HostAddress}:${Port} (emulator: http://10.0.2.2:${Port})" -ForegroundColor Cyan
    Write-Host "  auth mode: $authLabel   database: sqlite (.devdata/emulator.db)" -ForegroundColor Cyan
    & $python -m uvicorn app.main:app --host $HostAddress --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Uvicorn exited with code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
