# API Contract — Cretona Backend

**Version:** v1 · **Status:** Draft · **Base path:** `/api/v1`

This is the framework-neutral contract between the Android app and the active FastAPI backend. It is the source of truth for both sides; change it here first. The Express implementation under `backend/` remains migration evidence until FastAPI reaches parity.

---

## 1. Conventions

### 1.1 Transport
- HTTPS only in staging and production. Debug builds may use `http://10.0.2.2:8000` (emulator → active FastAPI host).
- `Content-Type: application/json; charset=utf-8` for request and response bodies.
- All timestamps are ISO-8601 UTC with `Z` (e.g. `2026-08-06T09:14:22Z`).
- All ids are UUID v4 strings unless stated otherwise.

### 1.2 Authentication
Every endpoint except `GET /health` requires:

```
Authorization: Bearer <supabase_access_token>
```

The token is the JWT issued by Supabase Auth to the app. The backend verifies its signature and expiry, resolves the `users` row from the `sub` claim, and rejects disabled accounts.

| Situation | Status | Code |
|---|---|---|
| Header missing or malformed | 401 | `UNAUTHENTICATED` |
| Token expired or invalid signature | 401 | `TOKEN_INVALID` |
| Valid token, account disabled | 403 | `ACCOUNT_DISABLED` |
| Valid token, insufficient role | 403 | `FORBIDDEN` |

The app must refresh the token via the Supabase SDK on `401 TOKEN_INVALID` and retry the request once. A second 401 forces logout.

The zero-spend local profile is the only exception: when the server is
explicitly started with `CRETONA_AUTH_MODE=dev`, it supplies a fixed local user
and accepts `X-Debug-User-Id` for ownership tests. This header is rejected by
non-development profiles and must never be used as production authentication.

### 1.3 Error envelope
Every non-2xx response uses exactly this shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Prompt must be between 1 and 1000 characters.",
    "details": [
      { "field": "prompt", "issue": "too_long" }
    ]
  },
  "requestId": "1f0f9c4e-3b2a-4a1e-9c0b-8f3d2e1a7b55"
}
```

`details` is optional and only present for validation failures. `requestId` is echoed in server logs and should be surfaced in bug reports.

**Error codes**

| Code | Status | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Request body or query failed validation |
| `UNAUTHENTICATED` | 401 | No usable credentials |
| `TOKEN_INVALID` | 401 | JWT rejected |
| `ACCOUNT_DISABLED` | 403 | Account disabled by an admin |
| `FORBIDDEN` | 403 | Authenticated but not permitted |
| `NOT_FOUND` | 404 | Resource absent, or not visible to this caller |
| `CONFLICT` | 409 | State transition not legal (e.g. retry on a completed project) |
| `PAYLOAD_TOO_LARGE` | 413 | Upload exceeds the size limit |
| `QUOTA_EXCEEDED` | 429 | Generation quota exhausted |
| `RATE_LIMITED` | 429 | Too many requests |
| `PROVIDER_ERROR` | 502 | Upstream AI provider failed |
| `INTERNAL_ERROR` | 500 | Unhandled server fault |

> A project belonging to another user returns `404 NOT_FOUND`, never `403` — existence is not disclosed.

### 1.4 Pagination
List endpoints are cursor-paginated, newest first.

**Query:** `?limit=20&cursor=<opaque>` — `limit` 1–50, default 20.

**Response:**
```json
{
  "items": [ … ],
  "page": { "nextCursor": "eyJjIjoiMjAyNi0wOC0wNlQwOToxNDoyMloifQ==", "hasMore": true }
}
```
`nextCursor` is `null` when `hasMore` is `false`. Cursors are opaque; clients must not parse them.

### 1.5 Idempotency
`POST /projects` accepts an optional `Idempotency-Key` header (client-generated UUID). Repeating a request with the same key within 24 hours returns the original project instead of creating a second one. The app sends this on every submit so a retry after a network drop cannot double-charge quota.

---

## 2. Endpoints

### 2.1 Health

#### `GET /health`
Unauthenticated liveness probe.

**200**
```json
{ "status": "ok", "version": "0.1.0" }
```

### 2.2 Prompt enhancement

#### `POST /prompts/enhance`

Asks the backend-owned text-LLM adapter to turn a short idea into a clearer
video prompt. The Android app never calls Ollama, Gemini, or OpenAI directly.

**Body**
```json
{ "prompt": "a cat astronaut", "aspectRatio": "16:9" }
```

**200**
```json
{
  "originalPrompt": "a cat astronaut",
  "enhancedPrompt": "Cinematic wide shot of a cat astronaut...",
  "provider": "ollama",
  "usedFallback": false
}
```

`provider: "deterministic"` and `usedFallback: true` mean no live LLM was
available. This keeps the demo usable but is not evidence that FastAPI called a
real LLM.

---

### 2.3 Profile

#### `GET /me`
Returns the caller's profile and current quota.

**200**
```json
{
  "id": "9f1c2a3d-4b5e-6f70-8192-a3b4c5d6e7f8",
  "email": "user@example.com",
  "username": "khoa",
  "role": "user",
  "isDisabled": false,
  "createdAt": "2026-07-14T02:11:05Z",
  "quota": { "limit": 10, "used": 3, "remaining": 7, "resetsAt": "2026-08-07T00:00:00Z" }
}
```

#### `PATCH /me`
**Body** — all fields optional, at least one required:
```json
{ "username": "khoa" }
```
`username`: 3–30 chars, `[a-zA-Z0-9_]`, unique.

**200** — same shape as `GET /me`.
**400** `VALIDATION_ERROR` · **409** `CONFLICT` if the username is taken.

---

### 2.4 Uploads

#### `POST /uploads/sign`
Issues a short-lived signed URL so the app uploads the source image directly to Supabase Storage. The backend never proxies image bytes.

**Body**
```json
{ "contentType": "image/jpeg", "sizeBytes": 1843200 }
```
Allowed `contentType`: `image/jpeg`, `image/png`, `image/webp`. Max `sizeBytes`: 10485760 (10 MB).

**201**
```json
{
  "uploadUrl": "https://<project>.supabase.co/storage/v1/object/upload/sign/uploads/…",
  "storagePath": "uploads/9f1c2a3d/2026-08-06/2b7e…​.jpg",
  "expiresAt": "2026-08-06T09:24:22Z"
}
```

The app `PUT`s the image bytes to `uploadUrl`, then passes `storagePath` to `POST /projects`. A `storagePath` not owned by the caller is rejected at project creation.

**413** `PAYLOAD_TOO_LARGE` · **400** `VALIDATION_ERROR` for a disallowed type.

---

### 2.5 Projects

#### `POST /projects`
Creates a project and queues a generation.

**Headers:** `Idempotency-Key: <uuid>` (recommended)

**Body**
```json
{
  "title": "Neon city flythrough",
  "prompt": "A drone shot flying through a neon-lit cyberpunk city at night",
  "imagePath": "uploads/9f1c2a3d/2026-08-06/2b7e….jpg",
  "provider": "fake",
  "options": { "durationSeconds": 5, "aspectRatio": "16:9" }
}
```

| Field | Required | Rules |
|---|---|---|
| `title` | no | ≤ 120 chars; derived from the prompt if omitted |
| `prompt` | conditional | 1–1000 chars. Required unless `imagePath` is present |
| `imagePath` | conditional | A `storagePath` from `POST /uploads/sign`, owned by the caller. Required unless `prompt` is present |
| `provider` | no | Defaults to the server's configured provider. The zero-spend demo exposes only `fake`; a local LTX/FramePack key is added only after EXP-005 passes. |
| `options.durationSeconds` | no | Integer, provider-dependent range |
| `options.aspectRatio` | no | One of `16:9`, `9:16`, `1:1` |

At least one of `prompt` / `imagePath` must be present — that is what distinguishes the three generation modes (FR-2.1 – FR-2.3).

**201** — a Project object (§3.1) with `status: "pending"`.

**400** `VALIDATION_ERROR` · **429** `QUOTA_EXCEEDED` · **502** `PROVIDER_ERROR` if submission fails immediately.

#### `GET /projects`
The caller's own projects, newest first.

**Query:** `limit`, `cursor`, and optional `status` (`pending|generating|completed|failed`).

**200** — paginated envelope of Project objects.

#### `GET /projects/:id`
**200** — Project object. **404** `NOT_FOUND` if absent or owned by someone else.

The app polls this endpoint while a project is `pending` or `generating` (see §4).

#### `DELETE /projects/:id`
Deletes the project, its source image, and its generated video from Storage. Logs are retained for auditing.

**204** — no body. **404** `NOT_FOUND`. **409** `CONFLICT` while the project is `generating`.

#### `POST /projects/:id/retry`
Re-queues a `failed` project. Consumes quota.

**202** — Project object with `status: "pending"`.
**409** `CONFLICT` if the project is not `failed`. **429** `QUOTA_EXCEEDED`.

---

### 2.6 Admin

All endpoints below require role `admin`; anything else gets `403 FORBIDDEN`.

#### `GET /admin/users`
**Query:** `limit`, `cursor`, `q` (matches email or username), `role`, `isDisabled`.

**200**
```json
{
  "items": [
    {
      "id": "9f1c2a3d-…",
      "email": "user@example.com",
      "username": "khoa",
      "role": "user",
      "isDisabled": false,
      "projectCount": 12,
      "createdAt": "2026-07-14T02:11:05Z"
    }
  ],
  "page": { "nextCursor": null, "hasMore": false }
}
```

#### `PATCH /admin/users/:id`
**Body** — at least one field:
```json
{ "isDisabled": true, "role": "admin" }
```

**200** — the updated admin user object.
**403** `FORBIDDEN` if the target is the calling admin (FR-4.6). **404** `NOT_FOUND`.

#### `GET /admin/stats`
**Query:** `days` (1–90, default 30).

**200**
```json
{
  "totals": { "users": 128, "activeUsers": 121, "projects": 1043 },
  "projectsByStatus": { "pending": 2, "generating": 5, "completed": 981, "failed": 55 },
  "projectsByProvider": { "runway": 812, "kling": 231 },
  "failureRate": 0.053,
  "daily": [
    { "date": "2026-08-05", "created": 41, "completed": 39, "failed": 2 }
  ]
}
```

---

### 2.7 Provider Webhook (post-MVP)

#### `POST /webhooks/providers/:provider`
Called by the provider, not by the app. Unauthenticated by JWT; authenticated by provider signature header, verified before the body is parsed. Unknown or unsigned requests are dropped with `401` and logged.

Handlers must be idempotent — providers retry.

---

## 3. Object Schemas

### 3.1 Project

```json
{
  "id": "3c9a1b2d-…",
  "title": "Neon city flythrough",
  "prompt": "A drone shot flying through a neon-lit cyberpunk city at night",
  "imageUrl": "https://…/uploads/…jpg?token=…",
  "videoUrl": "https://…/videos/…mp4?token=…",
  "thumbnailUrl": "https://…/videos/…jpg?token=…",
  "status": "completed",
  "provider": "runway",
  "errorMessage": null,
  "durationSeconds": 5,
  "createdAt": "2026-08-06T09:14:22Z",
  "updatedAt": "2026-08-06T09:16:48Z",
  "completedAt": "2026-08-06T09:16:48Z"
}
```

| Field | Notes |
|---|---|
| `status` | `pending` · `generating` · `completed` · `failed` |
| `imageUrl` | `null` for text-only. Signed, ~1 h expiry |
| `videoUrl` | `null` unless `completed`. Signed, ~1 h expiry — do not cache past `expiresAt` |
| `errorMessage` | Non-null only when `failed`. User-readable; never a raw provider payload |
| `completedAt` | Non-null only when `completed` or `failed` |

> Because media URLs are signed and short-lived, the app must fetch a fresh Project before playback or download rather than persisting the URL.

### 3.2 Quota
```json
{ "limit": 10, "used": 3, "remaining": 7, "resetsAt": "2026-08-07T00:00:00Z" }
```

---

## 4. Async Generation Flow

```
App                Backend              Provider
 │  POST /projects    │                      │
 ├───────────────────►│  insert (pending)    │
 │  201 {id,pending}  │                      │
 │◄───────────────────┤  submit ────────────►│
 │                    │◄──── jobId           │
 │                    │  update (generating) │
 │  GET /projects/:id │                      │
 ├───────────────────►│   poller ───────────►│
 │  200 {generating}  │◄──── status          │
 │◄───────────────────┤                      │
 │                    │  download + re-host  │
 │  GET /projects/:id │  update (completed)  │
 ├───────────────────►│                      │
 │  200 {completed}   │                      │
 │◄───────────────────┤                      │
```

**Client polling policy:** poll `GET /projects/:id` every 5 s for the first minute, then every 15 s, giving up after 10 minutes and showing a "still working, check back later" state. Polling stops when the app is backgrounded and resumes on foreground. The project row remains authoritative regardless.

---

## 5. Rate Limits

| Scope | Limit |
|---|---|
| `POST /projects`, `POST /projects/:id/retry` | 5 / minute / user |
| `POST /uploads/sign` | 20 / minute / user |
| All other authenticated endpoints | 120 / minute / user |
| Unauthenticated | 60 / minute / IP |

Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. A `429 RATE_LIMITED` includes `Retry-After` in seconds.

---

## 6. Versioning

The path carries the major version. Additive changes (new optional fields, new endpoints) ship within `v1`. Removing or renaming a field, or changing its type or meaning, requires `v2`. The app sends `X-Client-Version: <versionName>` so the backend can identify traffic from builds that predate a change.
