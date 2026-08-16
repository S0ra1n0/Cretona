# Cretona Documentation

# Cretona Documentation

## Start here

| If you want to… | Read |
|---|---|
| Get the project running on your machine | [SETUP.md](SETUP.md) |
| Know what the system must do | [SRS.md](SRS.md) |
| Know what to build next | [ROADMAP.md](ROADMAP.md) |
| Call or implement an endpoint | [API_CONTRACT.md](API_CONTRACT.md) |
| Change the database | [DATA_MODEL.md](DATA_MODEL.md) |
| Understand how the pieces fit | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Add an AI provider | [AI_PROVIDER_SPEC.md](AI_PROVIDER_SPEC.md) |
| Handle a key, token, or user data | [SECURITY.md](SECURITY.md) |
| Inspect executed Android/FastAPI evidence | [evidence/ANDROID_FASTAPI_E2E.md](evidence/ANDROID_FASTAPI_E2E.md) |
| Inspect the local-model feasibility gate | [experiments/EXP-005/](experiments/EXP-005/README.md) |
| Know why something is the way it is | [adr/](adr/README.md) |

## What is authoritative

Requirements have ids (`FR-2.1`, `NFR-2.3`) and everything else refers back to them. When documents disagree:

1. **[API_CONTRACT.md](API_CONTRACT.md)** wins on wire format — request and response shapes, status codes, error codes.
2. **[DATA_MODEL.md](DATA_MODEL.md)** wins on schema — columns, constraints, RLS policies.
3. **[SRS.md](SRS.md)** wins on behaviour — what the system must do.
4. **[adr/](adr/README.md)** wins on rationale, and records what a decision costs.

`ARCHITECTURE.md` and `AI_PROVIDER_SPEC.md` describe how we intend to satisfy the above. If reality diverges from them, fix the code or fix the document — a stale architecture doc is worse than none, because people trust it.

## Keeping this current

- Changing the API? Update the contract in the same commit as the code.
- Changing the schema? Update the data model in the same commit as the migration.
- Making a decision that a future reader would ask "why?" about? Write an ADR. They are short by design.
- Adding a `local.properties` or `.env` key? Add it to [SETUP.md](SETUP.md) and `.env.example`, or the next person's build breaks in a way that is hard to diagnose.

Progress against the plan is tracked in [ROADMAP.md](ROADMAP.md), which is the file to update when a task lands.
