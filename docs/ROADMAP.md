# Cretona — Master Roadmap & Development Plan

This document consolidates the original **Cretona Development Plan** and the detailed **Implementation Roadmap** into a single source of truth for architecture, delivery milestones, and technical progress.

---

## 1. Project Overview & Architecture Baseline

**Cretona** is a native Android application built with **Kotlin & Jetpack Compose** that allows users to generate AI videos from text prompts and reference images through high-performance backend pipelines.

### Tech Stack & System Boundaries
- **Client (Android Native):** Kotlin, Jetpack Compose, Material 3, MVVM + Clean Architecture, Hilt (DI), Retrofit + OkHttp, Media3 (ExoPlayer), Coil, MediaStore & FileProvider.
- **Backend (Python FastAPI):** FastAPI, Uvicorn, psycopg (PostgreSQL), Starlette SSE streams, JWT/ES256 verification, async poll leasing, structured JSON logging.
- **Data & Auth (Supabase):** PostgreSQL 16, Supabase Auth (JWT ES256/HS256), Supabase Storage.
- **AI Providers & Adapters:**
  - `fake`: Deterministic local development & automated test adapter.
  - `real`: Cloud AI Video Router (Fal.ai / Replicate / Cloud GPU).
  - `wan21`: Open-source Wan 2.1 Video Diffusion adapter.

---

## 2. Core Feature Matrix

### User Capabilities
- **Creative AI Studio:** Text prompts, preset chips (`🌸 Anime`, `🌆 Cyberpunk`, `🧸 3D Pixar`, `🎞️ Vintage Film`), Camera Motion controls (`Pan`, `Zoom`, `Orbit`), and Aspect Ratio (`9:16`, `16:9`, `1:1`).
- **Real-Time Video Generation:** Live progress streaming (SSE / polling) with progress percentages and step messages.
- **Studio & Media Operations:** In-app Media3 video playback, 1-tap save to local Gallery (`MediaStore.Video.Media`), 1-tap Social Share (`FileProvider`), and 1-tap **✨ Remix Video**.
- **Quota & Spend Safety:** Rolling window quota enforcement per user.

### Admin Capabilities
- User management (view, search, enable/disable account, role assignment).
- System-wide generation analytics and failure rates.

---

## 3. Detailed Milestone Status

**Legend:** `[ ]` Not Started · `[~]` In Progress · `[x]` Completed

### Phase 0 — Foundations & Decisions ✅
| ID | Task | Status |
|---|---|---|
| P0-1 | Monorepo layout with Android at root | `[x]` |
| P0-2 | Provider adapter architecture & multi-provider support | `[x]` |
| P0-3 | Machine-local configuration via `local.properties` / `.env` | `[x]` |
| P0-4 | Environments and config matrix | `[x]` |
| P0-5 | Server-Sent Events (SSE) & Async poll strategy | `[x]` |
| P0-6 | Rolling daily per-user generation quota | `[x]` |
| P0-7 | Supabase Auth ES256/HS256 JWT validation | `[x]` |

### Phase 1 — Supabase & Database Schema ✅
| ID | Task | Status |
|---|---|---|
| P1-1 | Postgres schema with migrations 001 - 009 | `[x]` |
| P1-2 | `project_status` enum, error codes, progress tracking columns | `[x]` |
| P1-3 | Role-Based Access Control (`user`, `admin`) | `[x]` |
| P1-4 | User sync triggers and audit timestamps | `[x]` |
| P1-5 | Row Level Security (RLS) & column grants | `[x]` |
| P1-6 | Partial indexes for polling scans, history, and idempotency | `[x]` |

### Phase 2 — Production Backend (FastAPI) ✅
| ID | Task | Status |
|---|---|---|
| P2-1 | FastAPI service architecture & routes | `[x]` |
| P2-2 | Endpoints `/health`, `/me`, `/projects`, `/admin/users`, `/admin/stats` | `[x]` |
| P2-3 | SSE real-time stream `GET /projects/{id}/events` | `[x]` |
| P2-4 | Style Presets & Camera Motion prompt synthesis | `[x]` |
| P2-5 | Rate limiting and structured logging with secret redaction | `[x]` |
| P2-6 | Pytest verification suite (302 tests passing) | `[x]` |

### Phase 3 — Android Client (Kotlin + Jetpack Compose) ✅
| ID | Task | Status |
|---|---|---|
| P3-1 | Jetpack Compose UI with Material 3 design system | `[x]` |
| P3-2 | Multi-provider selector (`Fake`, `Real AI`, `Wan 2.1`) | `[x]` |
| P3-3 | Style Preset chips, Camera Motion chips & Aspect Ratio switcher | `[x]` |
| P3-4 | Media3 ExoPlayer integration for video playback | `[x]` |
| P3-5 | `MediaDownloader` 1-tap Save to Gallery via `MediaStore` | `[x]` |
| P3-6 | `FileProvider` 1-tap Social Share Sheet | `[x]` |
| P3-7 | `CretonaNotificationManager` for background completion alerts | `[x]` |
| P3-8 | 1-tap ✨ Remix project to reload prompt and creative parameters | `[x]` |
| P3-9 | Full Android unit test suite (29 tests passing) | `[x]` |

---

## 4. Non-Scope / Excluded from MVP
- Direct cloud-vendor proprietary SDK embedding on Android.
- In-app NLE timeline video editing / audio multi-track mixing.
- Payment gateway / credit card processing.
