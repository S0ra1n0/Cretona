# Development setup

This guide describes the current local integration profile: Android talks to
FastAPI on port 8000. The Express service in `backend/` remains executable
migration evidence; it is not the active Mobile 1 runtime.

## 1. Prerequisites

| Tool | Required version | Role |
|---|---:|---|
| Android Studio | 2025.2+ | IDE, emulator, bundled JBR |
| JDK | 17+ | Android build; prefer Android Studio's JBR |
| Android SDK | API 37 | Compile SDK required by the checked-in dependencies |
| Python | 3.12+ | Active FastAPI backend |
| RTK | 0.45+ | Compact, repeatable Codex/CLI command output |
| Node.js | 20 LTS | Optional: verify the Express reference backend |
| FFmpeg/FFprobe | recent | Optional: regenerate or inspect video fixtures |
| Ollama | recent | Optional: real local prompt enhancement |
| Hugging Face CLI | 1.27+ | Optional: verify pinned model snapshots for EXP-005 |
| uv | 0.10+ | Optional: isolated Python runtimes for model research |
| 7-Zip | 26.02+ | Optional: verify/extract the official FramePack Windows archive |

Run the repository-owned preflight first:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-toolchain.ps1
```

The checker reports required and optional tools separately. It never reads or
prints secrets. It discovers Java and Android SDK paths from `JAVA_HOME`,
`ANDROID_SDK_ROOT`, `ANDROID_HOME`, and standard Windows locations. Nonstandard
installations can be supplied without editing the script:

```powershell
.\scripts\check-toolchain.ps1 -JavaHome 'D:\Tools\jbr' -AndroidSdk 'D:\Android\Sdk'
```

## 2. Android

Open the repository root (`Cretona/`) in Android Studio, not `app/`.

`local.properties` is machine-local and git-ignored. Android Studio normally
creates `sdk.dir`; add the Cretona values without committing this file:

```properties
sdk.dir=C\:\\Users\\<you>\\AppData\\Local\\Android\\Sdk

# 10.0.2.2 is the host machine from an Android emulator.
cretona.api.baseUrl.debug=http\://10.0.2.2\:8000/api/v1/
cretona.api.baseUrl.release=https\://api.cretona.app/api/v1/

# Optional until Supabase auth is ported to FastAPI.
supabase.url=https\://<project-ref>.supabase.co
supabase.anonKey=<anon-public-key>
```

Only the public Supabase anon key may be present here. Service-role keys,
database passwords, and provider credentials belong only in an ignored backend
`.env`; see [SECURITY.md](SECURITY.md).

The debug manifest permits cleartext HTTP only for local development. The
release manifest retains Android's HTTPS-by-default behavior.

Build gates on Windows:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
.\gradlew.bat :app:testDebugUnitTest :app:lintDebug :app:assembleDebug --no-daemon
```

## 3. Active FastAPI backend

Create an isolated environment and install the locked dependency ranges:

```powershell
Set-Location backend-fastapi
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-windows-py312.lock -e ".[dev]"
Copy-Item .env.example .env
Set-Location ..
```

The committed `.env.example` contains placeholders only. The ignored `.env`
may override settings, but the zero-spend demo works without any credential.

Start the service from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-fastapi.ps1
```

The service binds `0.0.0.0:8000` so an emulator can use
`http://10.0.2.2:8000/api/v1/`. Development auth uses one fixed local identity
or `X-Debug-User-Id`; this mode must never be used as a deployed auth profile.

Verify the backend:

```powershell
Set-Location backend-fastapi
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
Set-Location ..
```

### Optional local LLM

The default prompt enhancer is deterministic and keeps the demo offline. To
prove a real local LLM call, install Ollama, pull the selected model, then set
these values in `backend-fastapi/.env`:

```properties
CRETONA_PROMPT_LLM_PROVIDER=ollama
CRETONA_OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
```

The API response field `usedFallback` is the evidence boundary: `false` means
Ollama answered; `true` means the deterministic fallback answered. Neither
state proves a real video model has run.

On the measured 16 GB laptop, keep `CRETONA_OLLAMA_NUM_CTX=4096`,
`CRETONA_OLLAMA_NUM_PREDICT=180`, and `CRETONA_OLLAMA_TEMPERATURE=0.2`. FastAPI
sends `keep_alive: 0` so Ollama unloads Qwen immediately after each request and
does not compete with the video worker for memory.

### Optional EXP-005 video-research runtime

The large video runtime is machine-local and intentionally excluded from Git.
On Bruce's measured laptop, durable tools/caches live beside the repository
root on drive D:

```text
PLUS26/.ai-runtimes/   extracted/pinned model runtimes
PLUS26/.ai-models/     Ollama, Hugging Face and Torch caches
PLUS26/.downloads/     verified vendor archives
PLUS26/.tools/         portable tools such as Ollama and uv-managed Python
```

`scripts/check-toolchain.ps1` verifies the exact FramePack source revision,
bundled Python/Torch/CUDA runtime, three pinned model snapshots, incomplete-file
absence, and the persistent cache roots. Reproduction metadata—release URL,
source/model revisions, byte counts, hashes, and license status—is in
`docs/experiments/EXP-005/MODEL_RUNTIME_MANIFEST.json`.

Do not run FramePack's bundled `update.bat`: its failure path performs
`git reset --hard`. Update an intentionally clean runtime only with a reviewed,
explicit fast-forward, then record the new revision in the manifest. Do not
download LTX 2B weights while its documented Ampere host-envelope gate remains
failed.

Before any FramePack process starts, run:

```powershell
.\scripts\check-toolchain.ps1
.\scripts\check-exp005-preflight.ps1 -Profile framepack
```

The second command currently fails by design. It requires at least 6 GiB free
physical RAM, 6 GiB free VRAM, 48 GiB free virtual-memory headroom, 100 GiB free
on drive D, AC power, and no loaded Ollama model. A Windows pagefile change is
a separate system-level decision; the setup script does not make it.

## 4. Express reference backend

Use this only to protect behavior during the FastAPI migration:

```powershell
Set-Location backend
npm ci
npm run prisma:generate
npm test
npm run typecheck
npm run build
Set-Location ..
```

Do not copy provider, Supabase, or database secrets into Android configuration.
Do not delete the Express reference until FastAPI reaches the parity gates in
[ADR-008](adr/ADR-008-fastapi-migration.md) and both developers approve it.

## 5. Emulator networking

| Runtime | Debug base URL |
|---|---|
| Android emulator, FastAPI on host | `http://10.0.2.2:8000/api/v1/` |
| Physical device on same Wi-Fi | `http://<host-LAN-IP>:8000/api/v1/` |
| Remote staging | HTTPS URL supplied by the deployed environment |

FastAPI must bind `0.0.0.0`; `localhost` inside the emulator means the emulator
itself. For a physical device, allow only the required port on the trusted local
network and do not expose development auth to the public internet.

## 6. RTK durability note

RTK is installed at `C:\Users\ASUS\.local\bin\rtk.exe`. Its tracking database
is configured in the ignored `.rtk-data/` directory because Codex Desktop's
Windows sandbox cannot reliably write RTK's default LocalAppData database. The
user-scoped `CLAUDE_CONFIG_DIR` variable also prevents RTK from relying on an
undefined home path in a fresh Codex shell. A restarted shell should inherit
the setting.

Native Windows Codex currently uses RTK through repository/global instructions;
the missing shell-hook notice does not mean command filtering is unavailable.

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Emulator cannot reach FastAPI | Start it with `--host 0.0.0.0`; use `10.0.2.2`, not `localhost` |
| Android points to port 3000 | Replace the stale Express URL in ignored `local.properties` with port 8000 and rebuild |
| Java/Gradle version failure | Set `JAVA_HOME` to Android Studio's bundled JBR for that shell |
| `requires compile against version 37` | Install Android API 37 in SDK Manager |
| FastAPI import fails | Recreate `backend-fastapi/.venv` and install `-e ".[dev]"` |
| Prompt says deterministic fallback | Ollama is disabled/unreachable; check `.env`, model availability, and `/api/tags` locally |
| Video is a color test pattern | Expected fake-provider evidence; real AI video remains gated by EXP-005 |
| `rtk gain` cannot write LocalAppData | Confirm the roaming RTK config points `database_path` at `.rtk-data/history.db` |
| FFmpeg link is blocked in Codex | Run `check-toolchain.ps1`; it resolves the WinGet symlink target before invoking the executable |
