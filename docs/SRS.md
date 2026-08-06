# Software Requirements Specification — Cretona

**Version:** 0.1 · **Status:** Draft · **Last updated:** 2026-08-06

---

## 1. Introduction

### 1.1 Purpose
Cretona is a native Android application that turns a text prompt, an image, or both into a short AI-generated video. It handles user accounts, role-based access, generation history, and media delivery. This document specifies what the system must do and the constraints it operates under.

### 1.2 Scope
The product consists of three parts:

| Component | Responsibility |
|---|---|
| Android app (Kotlin/Compose) | All user interaction; authenticates with Supabase; talks to the Cretona backend |
| Backend (Node.js/Express) | Business rules, quota enforcement, AI provider orchestration, admin operations |
| Supabase | Postgres database, auth (JWT issuer), object storage for images and videos |

Third-party AI video providers are external systems reached only by the backend.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| **Project** | One generation request and its result. Row in `video_projects`. |
| **Generation** | The act of producing a video for a project. |
| **Provider** | A third-party AI video API (Runway, Kling, Pika, Luma, Veo). |
| **Job** | A unit of work at the provider, identified by a provider job id. |
| **Quota** | The number of generations a user may run within a period. |
| **RLS** | Postgres Row Level Security. |

### 1.4 Actors

- **Guest** — unauthenticated; may only register or log in.
- **User** — authenticated; owns projects; can generate, view, download, delete their own.
- **Admin** — everything a User can do, plus user management and statistics.

---

## 2. Overall Description

### 2.1 Product perspective
A new, self-contained system. It depends on Supabase for identity/storage and on at least one external AI video provider. It is not a replacement for an existing system and has no legacy data to migrate.

### 2.2 Operating environment
- Android 8.0 (API 26) and above, phone form factor, portrait-first.
- Requires network connectivity; no offline generation.
- Backend runs on Node.js 20+ against Postgres 15+ (Supabase-managed).

### 2.3 Constraints
- **C-1** AI provider API keys must never exist on the device or in the APK.
- **C-2** Generation is asynchronous and can take from ~30 seconds to several minutes. No UI may assume a synchronous result.
- **C-3** Provider-hosted result URLs expire; results must be re-hosted before being persisted.
- **C-4** Provider usage costs real money per generation, so quota enforcement is a functional requirement, not an optimization.
- **C-5** The provider layer must be swappable without changing controllers or the Android app.

### 2.4 Assumptions
- One provider is live at launch; more are added behind the same interface.
- Users supply their own source images; no stock library is provided.
- Videos are short (typically 5–10 s) as constrained by the chosen provider.

---

## 3. Functional Requirements

Priority: **M** = MVP (must ship), **S** = should, **C** = could / post-MVP.

### 3.1 Authentication & Account

| ID | Requirement | Pri |
|---|---|---|
| FR-1.1 | A guest can register with email and password. Email must be unique and syntactically valid; password minimum 8 characters. | M |
| FR-1.2 | A guest can log in with email and password and receives a session (JWT + refresh token). | M |
| FR-1.3 | The session persists across app restarts and is refreshed automatically before expiry. | M |
| FR-1.4 | A user can log out, which clears all locally stored session material. | M |
| FR-1.5 | On registration a `users` row is created automatically with the default role `user`. | M |
| FR-1.6 | A user can view and edit their profile (username). | M |
| FR-1.7 | A user can request a password reset by email. | S |
| FR-1.8 | A disabled account is refused at the API boundary with `403 ACCOUNT_DISABLED` on every authenticated request. | M |

### 3.2 Video Generation

| ID | Requirement | Pri |
|---|---|---|
| FR-2.1 | A user can submit a **text-only** generation: a prompt of 1–1000 characters. | M |
| FR-2.2 | A user can submit an **image-only** generation by selecting an image from device storage. | M |
| FR-2.3 | A user can submit a **text + image** generation. | M |
| FR-2.4 | Source images are validated: JPEG/PNG/WebP, ≤ 10 MB, and uploaded to Supabase Storage before the project is created. | M |
| FR-2.5 | Submitting a generation creates a project with status `pending` and returns immediately with the project id. | M |
| FR-2.6 | The backend submits the job to the configured provider and moves the project to `generating`. | M |
| FR-2.7 | The system detects completion (polling or webhook), re-hosts the video in Supabase Storage, and sets status `completed` with a permanent `video_url`. | M |
| FR-2.8 | On provider error or timeout the project moves to `failed` and stores a user-readable error message. | M |
| FR-2.9 | The app reflects status changes without the user leaving and re-entering the screen. | M |
| FR-2.10 | Every provider request and response is recorded in `generation_logs`, with credentials redacted. | M |
| FR-2.11 | A user may retry a `failed` project, which creates a new generation attempt. | S |
| FR-2.12 | A user may choose the provider and generation parameters (duration, aspect ratio). | C |

### 3.3 History & Media

| ID | Requirement | Pri |
|---|---|---|
| FR-3.1 | A user can list their own projects, newest first, paginated. | M |
| FR-3.2 | The list shows title/prompt excerpt, status, and creation time; completed items show a thumbnail. | M |
| FR-3.3 | A user can open a project to see the full prompt, source image, and play the video in-app. | M |
| FR-3.4 | A user can download a completed video to device storage. | M |
| FR-3.5 | A user can share a completed video via the Android share sheet. | S |
| FR-3.6 | A user can delete their own project; associated stored media is deleted too. | M |
| FR-3.7 | A user can filter history by status. | S |
| FR-3.8 | A user is notified when a generation finishes while the app is backgrounded. | C |

### 3.4 Administration

| ID | Requirement | Pri |
|---|---|---|
| FR-4.1 | An admin can list all users with search and pagination. | M |
| FR-4.2 | An admin can disable and re-enable a user account. | M |
| FR-4.3 | An admin can change a user's role. | S |
| FR-4.4 | An admin can view statistics: total users, total projects, counts by status, counts by provider, generations over the last 30 days. | M |
| FR-4.5 | Admin-only screens and endpoints are inaccessible to non-admins; the app hides them and the API rejects them with `403`. | M |
| FR-4.6 | An admin cannot disable or demote their own account. | S |

### 3.5 Quota & Abuse Control

| ID | Requirement | Pri |
|---|---|---|
| FR-5.1 | Each user has a generation quota per rolling period; exceeding it returns `429 QUOTA_EXCEEDED`. | M |
| FR-5.2 | Remaining quota is visible in the app before submitting. | S |
| FR-5.3 | Generation endpoints are rate-limited per user and per IP independently of quota. | M |

---

## 4. Non-Functional Requirements

### 4.1 Performance
- **NFR-1.1** Non-generation API calls respond in < 500 ms at p95 under nominal load.
- **NFR-1.2** History list renders the first page in < 1 s on a mid-range device.
- **NFR-1.3** Status changes surface in the app within 10 s of the backend recording them.
- **NFR-1.4** The app remains responsive (no ANR) while a generation is in flight.

### 4.2 Security
- **NFR-2.1** All traffic over HTTPS/TLS 1.2+. Cleartext is permitted only for `10.0.2.2` in debug builds.
- **NFR-2.2** Every non-public endpoint verifies the Supabase JWT signature and expiry.
- **NFR-2.3** RLS is enabled on every user-data table; a compromised anon key must not expose other users' rows.
- **NFR-2.4** Authorization is enforced server-side on every resource access — never by hiding UI alone (IDOR protection on `/projects/:id`).
- **NFR-2.5** Provider keys and the Supabase `service_role` key exist only in backend environment variables.
- **NFR-2.6** Logs redact `Authorization` headers, API keys, and tokens.
- **NFR-2.7** Storage objects are served through short-lived signed URLs, scoped to the owner.

### 4.3 Reliability
- **NFR-3.1** A backend restart must not lose in-flight generations; job state lives in the database, not in memory.
- **NFR-3.2** Provider calls retry transient failures (5xx, timeout) up to 3 times with exponential backoff.
- **NFR-3.3** A job that has not completed within its provider timeout is marked `failed` rather than left `generating` indefinitely.
- **NFR-3.4** Generation submission is idempotent per client request id, so a retried submit does not double-charge.

### 4.4 Usability
- **NFR-4.1** Every screen has explicit loading, empty, and error states with a retry path.
- **NFR-4.2** Errors are shown in plain language; raw provider or stack messages are never surfaced.
- **NFR-4.3** Light and dark theme, Material 3, minimum 4.5:1 text contrast, content descriptions on interactive elements.

### 4.5 Maintainability
- **NFR-5.1** Android follows MVVM + repository; ViewModels hold no Android framework references beyond `ViewModel` itself.
- **NFR-5.2** Adding a provider requires implementing one interface and registering it — no changes to controllers, routes, or the app.
- **NFR-5.3** Business logic in services, not controllers; controllers only translate HTTP.

### 4.6 Privacy & Compliance
- **NFR-6.1** Users can delete their projects and the underlying media.
- **NFR-6.2** The Play Store data-safety declaration must state that prompts and uploaded images are transmitted to third-party AI providers.
- **NFR-6.3** A privacy policy is published before release.

---

## 5. Data Requirements

Entities, columns, relationships, and RLS policies are specified in [DATA_MODEL.md](DATA_MODEL.md). Summary:

`roles` 1—N `users` 1—N `video_projects` 1—N `generation_logs`

Project status is a state machine: `pending → generating → completed | failed`. No other transition is legal except `failed → pending` via retry (FR-2.11).

---

## 6. External Interfaces

- **Client ↔ Backend:** REST/JSON over HTTPS, specified in [API_CONTRACT.md](API_CONTRACT.md).
- **Client ↔ Supabase:** Auth (sign-up, sign-in, refresh) and direct-to-Storage image upload via signed URL.
- **Backend ↔ Provider:** per-provider HTTP, normalized behind the interface in [AI_PROVIDER_SPEC.md](AI_PROVIDER_SPEC.md).

---

## 7. Acceptance Criteria for MVP

The MVP is accepted when, on a clean install:

1. A new user can register, log in, and see an empty history.
2. Each of the three input modes (text, image, text+image) produces a playable video.
3. Status transitions are visible in the app without a manual restart.
4. A completed video can be downloaded and plays outside the app.
5. Deleting a project removes it from history and removes its stored media.
6. A second user cannot read, open, or delete the first user's projects — verified by direct API call, not just UI.
7. A non-admin receives `403` from every `/admin/*` endpoint.
8. An admin can disable an account, and that account is refused on its next request.
9. Exceeding the quota returns `429` and a clear message in the app.
10. Killing and restarting the backend mid-generation still yields a completed project.

---

## 8. Out of Scope

Payments and subscriptions · social feed or public sharing · in-app video editing or trimming · multi-language UI · web or iOS clients · offline queueing · team/organization accounts.
