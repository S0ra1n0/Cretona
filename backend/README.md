# Cretona FastAPI backend

This is the active backend migration target required by the Mobile 1 course.
It preserves the framework-neutral contract and provider boundary from the
tested Express implementation in `../backend/`.

## What works now

- `GET /api/v1/health`
- `POST /api/v1/prompts/enhance`
- create, list, fetch, delete, and retry projects
- SQLite persistence and opaque cursor pagination
- deterministic `pending -> generating -> completed|failed` fake jobs
- idempotent create and owner-scoped project access
- safe error envelopes with request IDs
- static serving of the bundled synthetic H.264/AAC demo MP4
- optional free local prompt enhancement through Ollama
- bounded 180-day `generation_logs` retention with metadata-only summaries
- atomic Postgres-backed rate-limit windows with an in-memory SQLite fallback

This is a zero-spend integration profile. The fake provider proves the app and
job lifecycle; it does not prove real AI video quality. Qwen prompt enhancement
has passed live, but no video adapter is selected: LTX-Video 2B was rejected by
pre-screen and FramePack remains blocked on EXP-005.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-windows-py312.lock -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The Android emulator uses `http://10.0.2.2:8000/api/v1/`.

`constraints-windows-py312.lock` records the exact dependency environment that
passed the repository gates. Update it only together with a clean-environment
install and a rerun of Ruff/Pytest.

To call a real free local text LLM, install Ollama, pull the configured model,
and set:

```properties
CRETONA_PROMPT_LLM_PROVIDER=ollama
CRETONA_OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
```

The response field `usedFallback` is the evidence boundary: `false` means
Ollama answered; `true` means the deterministic enhancer kept the demo usable.
The request uses a 4K context, a bounded 180-token response, and
`keep_alive: 0` so the model releases memory before video generation starts.

## Verify

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
```

That leaves **31 tests skipped**: `test_postgres_parity.py` needs a real
Postgres, and production runs Postgres. Everything with a second implementation
in `postgres.py` — the credit ledger especially — is unexercised until you run
them.

```powershell
docker run -d --rm --name cretona-pg-test -e POSTGRES_PASSWORD=test `
  -e POSTGRES_DB=cretona_test -p 55433:5432 postgres:17-alpine

$env:CRETONA_TEST_DATABASE_URL = "postgresql://postgres:test@127.0.0.1:55433/cretona_test"
.\.venv\Scripts\python.exe -m pytest

docker stop cretona-pg-test
```

Expect **468 passed, 0 skipped**. `tests/db_safety.py` refuses to apply the
destructive test schema to anything but a local host, so this cannot be pointed
at Supabase by accident.
