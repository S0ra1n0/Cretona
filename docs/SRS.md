# Software Requirements Specification — Cretona

**Version:** 1.1 · **Status:** Implemented Baseline with Open AI Output Gap · **Last updated:** 2026-08-20

---

## 1. Introduction

### 1.1 Purpose
Cretona is a native Android application for creating short video artifacts from text prompts and optional reference images through provider-neutral FastAPI adapters. Authentication, role-based access control (RBAC), prompt enhancement, project lifecycle management, playback, gallery downloads, sharing, and remixing are implemented. The accepted zero-spend output is not temporal AI video: cloud/local tiers generate or retrieve one still and apply camera motion with ffmpeg. A frame-to-frame video model is an open product requirement.

Implementation truth boundary: the backend exposes an SSE endpoint, while the
current Android client observes progress through REST polling. Android JVM,
lint, build, and compile gates have passed; device runtime was not executed in
the 2026-08-20 audit. Desired requirements below must not be read as proof of a
temporal model or an Android SSE client.

### 1.2 System Boundary & Scope
The Cretona architecture consists of three integrated components:

| Component | Responsibility | Technology Stack |
|---|---|---|
| **Android Client** (`app/`) | Native user interface, persisted Supabase authentication, creative studio controls, REST progress polling, cursor-paginated history/admin lists, Media3 playback, MediaStore gallery integration, and Share sheets. | Kotlin 2.4.10, Jetpack Compose, Material 3, Hilt, Retrofit/OkHttp, Media3 ExoPlayer, Coil. |
| **Production Backend** (`backend/`) | API routing, JWT verification (ES256/JWKS), generation lifecycle management, quota enforcement, background poller, prompt enhancer, SSE streaming, and AI provider adapters. | Python 3.12, FastAPI, Uvicorn, psycopg, Pydantic, Starlette SSE. |
| **Data & Storage** (`supabase/`) | User identity, PostgreSQL data layer with Row Level Security (RLS), and private object storage buckets (`uploads`, `videos`). | PostgreSQL 17 (Supabase), Supabase Auth & Storage. |

Third-party AI/media providers are isolated behind the server-side provider boundary. The Android client never possesses provider credentials.

### 1.3 Actors & Roles
- **Guest**: Unauthenticated user; may register a new account or log into an existing account.
- **User**: Authenticated account holder; owns creative projects, submits generation jobs, watches live progress, downloads and shares videos, and tracks daily quotas.
- **Admin**: Authenticated account with elevated privileges; can inspect system-wide generation metrics and manage user account states (enable/disable users, update roles).

---

## 2. Functional Requirements

### 2.1 Authentication & Authorization
- **FR-AUTH-001**: A guest shall be able to register with email and password via Supabase Auth.
- **FR-AUTH-002**: A registered user shall be able to log in, receive a secure JWT access token, and persist the session across app launches.
- **FR-AUTH-003**: The backend shall verify Supabase JWT tokens via JWKS (supporting both ES256 and HS256) and reject expired, invalid, or disabled accounts (`ACCOUNT_DISABLED`).
- **FR-AUTH-004**: Administrative endpoints shall require the `admin` role enforced by the backend (`FORBIDDEN`).

### 2.2 Creative Studio & Video Generation
- **FR-GEN-001 (Text-to-Video Workflow)**: The user shall be able to enter a text prompt (1–1000 characters) to initiate a provider-neutral video project. Temporal synthesis remains open; the accepted zero-spend implementation renders camera motion over one generated/retrieved still.
- **FR-GEN-002 (Prompt Enhancement)**: The user shall be able to request AI prompt enhancement to expand a concise idea into a detailed prompt with clear confirmation.
- **FR-GEN-003 (Style Presets)**: The user shall be able to select from curated artistic styles:
  - `🌸 Anime`: Japanese animation aesthetic, vibrant colors, stylized lighting.
  - `🌆 Cyberpunk`: Neon glows, futuristic sci-fi cityscapes, atmospheric fog.
  - `🧸 3D Pixar`: 3D animated character style, warm ambient lighting, expressive depth.
  - `🎞️ Vintage Film`: 35mm grain, retro color palette, classic cinematic framing.
  - `📸 Photorealistic`: Natural lighting, 8k documentary detail, authentic textures.
- **FR-GEN-004 (Camera Motion Intent)**: The user shall be able to add a camera-motion directive to the generation prompt. The placeholder renderer does not guarantee a distinct physical path for every choice:
  - `⬅️ Pan Left` / `➡️ Pan Right`: Horizontal camera panning.
  - `🔍 Zoom In` / `🔎 Zoom Out`: Focal distance transitions.
  - `🔄 Orbit`: 360-degree circling motion around the subject.
- **FR-GEN-005 (Aspect Ratios)**: The user shall be able to choose output dimensions: `9:16` (Vertical/Reels/TikTok), `16:9` (Widescreen/Cinematic), or `1:1` (Square).
- **FR-GEN-006 (Multi-Provider Selection)**: The user shall be able to select a stable provider tier without receiving raw model identifiers:
  - `Mock`: bundled zero-spend clip for deterministic development/testing.
  - `Cloud`: optional hosted still generation followed by ffmpeg pan/zoom; no temporal model currently runs.
  - `Local`: reserved local tier; currently the same still-plus-pan path and no local weights.
- **FR-GEN-007 (Progress Observation)**: The backend shall expose an SSE stream (`GET /api/v1/projects/{id}/events`) with percentage and step messages. The implemented Android client may use bounded REST polling until direct SSE consumption is accepted and device-tested.
- **FR-GEN-008 (Job Cancellation)**: The user shall be able to cancel an in-flight video generation job via `POST /api/v1/projects/{id}/cancel`.

### 2.3 Media & Project Operations
- **FR-MEDIA-001 (1-Tap Save to Gallery)**: The user shall be able to download the generated MP4 video directly into the device's public `Movies/Cretona` gallery via `MediaStore.Video.Media`.
- **FR-MEDIA-002 (1-Tap Social Share)**: The user shall be able to share the video file to external apps (WhatsApp, Telegram, YouTube, etc.) via Android `FileProvider` and system Share Sheet.
- **FR-MEDIA-003 (1-Tap Remix)**: The implemented remix action repopulates the prompt and aspect ratio. Persisting and restoring style preset and camera-motion metadata remains open because project responses do not currently return those creation options.
- **FR-MEDIA-004 (In-App Playback)**: The user shall be able to play generated videos seamlessly within the app using AndroidX Media3 (ExoPlayer).

### 2.4 Quota & Spend Controls
- **FR-QUOTA-001**: The backend shall enforce a daily rolling quota (default: 10 generations/day) per user.
- **FR-QUOTA-002**: When quota is exceeded, creation attempts shall be rejected with HTTP 429 `QUOTA_EXCEEDED` before invoking any third-party provider.
- **FR-QUOTA-003**: The Android client shall display the current remaining quota and time-to-reset on the studio dashboard.

---

## 3. Non-Functional Requirements

### 3.1 Security & Data Protection
- **NFR-SEC-001**: AI provider API keys, model endpoints, and secret tokens must never exist in the client APK or client-side storage.
- **NFR-SEC-002**: All client-server communication must use TLS (HTTPS in staging/production).
- **NFR-SEC-003**: Row Level Security (RLS) policies in PostgreSQL must isolate project records so users can never read or modify another user's media.

### 3.2 Performance & Reliability
- **NFR-REL-001**: The backend poller shall use database leases (`poll_lease_until`) to prevent race conditions during concurrent worker polling.
- **NFR-REL-002**: Idempotent project submission (`Idempotency-Key` header) must prevent duplicate job charges on network reconnects.
- **NFR-REL-003**: The Android UI must remain completely responsive (60fps+) during background video polling, downloads, and playback.
