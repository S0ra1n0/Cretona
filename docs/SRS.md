# Software Requirements Specification — Cretona

**Version:** 1.0 · **Status:** Accepted Baseline · **Last updated:** 2026-08-16

---

## 1. Introduction

### 1.1 Purpose
Cretona is a native Android application designed to produce short AI-generated videos from text prompts and reference images through high-performance cloud/local AI adapters. The application provides complete end-to-end functionality including authentication, role-based access control (RBAC), creative prompt engineering, live progress streaming, media playback, local gallery downloads, and 1-tap remixing.

### 1.2 System Boundary & Scope
The Cretona architecture consists of three integrated components:

| Component | Responsibility | Technology Stack |
|---|---|---|
| **Android Client** (`app/`) | Native user interface, Supabase authentication, creative studio controls, real-time SSE progress visualization, Media3 playback, MediaStore gallery integration, and Social Share sheets. | Kotlin 2.3, Jetpack Compose, Material 3, Hilt, Retrofit/OkHttp, Media3 ExoPlayer, Coil. |
| **Production Backend** (`backend/`) | API routing, JWT verification (ES256/JWKS), generation lifecycle management, quota enforcement, background poller, prompt enhancer, SSE streaming, and AI provider adapters. | Python 3.12, FastAPI, Uvicorn, psycopg, Pydantic, Starlette SSE. |
| **Data & Storage** (`supabase/`) | User identity, PostgreSQL data layer with Row Level Security (RLS), and private object storage buckets (`uploads`, `videos`). | PostgreSQL 16 (Supabase), Supabase Auth & Storage. |

Third-party AI video providers are isolated behind the server-side provider boundary. The Android client never possesses provider credentials.

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
- **FR-GEN-001 (Text-to-Video)**: The user shall be able to enter a text prompt (1–1000 characters) to initiate video generation.
- **FR-GEN-002 (Prompt Enhancement)**: The user shall be able to request AI prompt enhancement to expand a concise idea into a detailed prompt with clear confirmation.
- **FR-GEN-003 (Style Presets)**: The user shall be able to select from curated artistic styles:
  - `🌸 Anime`: Japanese animation aesthetic, vibrant colors, stylized lighting.
  - `🌆 Cyberpunk`: Neon glows, futuristic sci-fi cityscapes, atmospheric fog.
  - `🧸 3D Pixar`: 3D animated character style, warm ambient lighting, expressive depth.
  - `🎞️ Vintage Film`: 35mm grain, retro color palette, classic cinematic framing.
  - `📸 Photorealistic`: Natural lighting, 8k documentary detail, authentic textures.
- **FR-GEN-004 (Camera Motion)**: The user shall be able to specify cinematic camera movements:
  - `⬅️ Pan Left` / `➡️ Pan Right`: Horizontal camera panning.
  - `🔍 Zoom In` / `🔎 Zoom Out`: Focal distance transitions.
  - `🔄 Orbit`: 360-degree circling motion around the subject.
- **FR-GEN-005 (Aspect Ratios)**: The user shall be able to choose output dimensions: `9:16` (Vertical/Reels/TikTok), `16:9` (Widescreen/Cinematic), or `1:1` (Square).
- **FR-GEN-006 (Multi-Provider Selection)**: The user shall be able to select the target video engine:
  - `Fake`: Instant mock generation for development and offline testing.
  - `Real AI`: Generic Cloud AI Router (Fal.ai / Replicate / Cloud GPU).
  - `Wan 2.1`: Advanced open-source diffusion model adapter.
- **FR-GEN-007 (Real-Time Progress Streaming)**: The backend shall expose an SSE stream (`GET /api/v1/projects/{id}/events`) delivering real-time percentage progress (0–100%) and descriptive step messages (`"Synthesizing prompt..."`, `"Generating frames..."`, `"Encoding video..."`).
- **FR-GEN-008 (Job Cancellation)**: The user shall be able to cancel an in-flight video generation job via `POST /api/v1/projects/{id}/cancel`.

### 2.3 Media & Project Operations
- **FR-MEDIA-001 (1-Tap Save to Gallery)**: The user shall be able to download the generated MP4 video directly into the device's public `Movies/Cretona` gallery via `MediaStore.Video.Media`.
- **FR-MEDIA-002 (1-Tap Social Share)**: The user shall be able to share the video file to external apps (WhatsApp, Telegram, YouTube, etc.) via Android `FileProvider` and system Share Sheet.
- **FR-MEDIA-003 (1-Tap Remix)**: The user shall be able to tap **"✨ Remix"** on any completed project in their history to instantly populate the prompt, style preset, camera motion, and aspect ratio into the creation studio.
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
