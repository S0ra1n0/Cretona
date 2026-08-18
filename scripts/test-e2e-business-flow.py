#!/usr/bin/env python3
"""Cretona Complete End-to-End Business Flow Test Suite.

Executes a full lifecycle business workflow:
1. System Health & Database Connectivity Check (GET /api/v1/health)
2. Identity & Quota Inspection (GET /api/v1/me)
3. AI Prompt Enhancement (POST /api/v1/prompts/enhance)
4. Video Generation Project Creation (POST /api/v1/projects)
5. Asynchronous Progress Polling (GET /api/v1/projects/{id})
6. Media & Thumbnail Asset Verification (GET /media/...)
7. History List & Ordering Verification (GET /api/v1/projects)
8. User Profile & Avatar Update (PATCH /api/v1/me)
9. Job Cancellation & Quota Refund (POST /api/v1/projects/{id}/cancel)
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
backend_dir = ROOT / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)


def run_e2e_business_flow(mode: str = "dev", token: str | None = None):
    print("=" * 70)
    print(f" >>> EXECUTING COMPLETE END-TO-END BUSINESS FLOW TEST (MODE: {mode.upper()}) <<<")
    print("=" * 70)

    dev_data_dir = backend_dir / ".devdata"
    dev_data_dir.mkdir(parents=True, exist_ok=True)

    if mode == "dev":
        os.environ["CRETONA_ENVIRONMENT"] = "development"
        os.environ["CRETONA_AUTH_MODE"] = "dev"
        os.environ["CRETONA_DATABASE_BACKEND"] = "sqlite"
        os.environ["CRETONA_DATABASE_PATH"] = ".devdata/e2e_test.db"
        os.environ["CRETONA_STORAGE_BACKEND"] = "local"
        os.environ["CRETONA_DEFAULT_VIDEO_PROVIDER"] = "mock"
        os.environ["CRETONA_RATE_LIMIT_ENABLED"] = "false"
        os.environ["CRETONA_GENERATION_LOG_RETENTION_ENABLED"] = "false"

    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.database import Database
    from app.main import create_app

    # Clear cached settings so process env overrides take effect
    get_settings.cache_clear()
    settings = get_settings()

    # Pre-seed dev user if running with sqlite
    dev_user_id = "00000000-0000-4000-8000-000000000001"
    if settings.database_backend == "sqlite":
        db = Database(settings.resolved_database_path())
        db.initialize()
        db.upsert_user(
            dev_user_id,
            email="dev@cretona.test",
            username="dev_creator",
            role="user",
            created_at="2026-01-01T00:00:00Z",
        )

    app = create_app(settings)

    with TestClient(app) as client:
        headers = {"X-Request-ID": "e2e-business-flow-test"}
        if mode == "dev":
            headers["X-Debug-User-Id"] = dev_user_id
        elif token:
            headers["Authorization"] = f"Bearer {token}"

        # -------------------------------------------------------------
        # Step 1: Health & Database Connectivity Check
        # -------------------------------------------------------------
        print("\n[Step 1/9] Checking Server Health & Database Ping...")
        res = client.get("/api/v1/health")
        assert res.status_code == 200, f"Health check failed: {res.text}"
        data = res.json()
        assert data.get("status") == "ok"
        print(f"  --> Status: OK (version={data.get('version')}) [PASS]")

        # -------------------------------------------------------------
        # Step 2: Identity & Quota Inspection
        # -------------------------------------------------------------
        print("\n[Step 2/9] Fetching User Profile & Initial Quota...")
        res = client.get("/api/v1/me", headers=headers)
        assert res.status_code == 200, f"Get /me failed: {res.text}"
        me = res.json()
        q_rem = me["quota"]["remaining"]
        q_lim = me["quota"]["limit"]
        print(f"  --> User ID: {me['id']} | Role: {me['role']} | Quota: {q_rem}/{q_lim} [PASS]")

        # -------------------------------------------------------------
        # Step 3: AI Prompt Enhancement
        # -------------------------------------------------------------
        print("\n[Step 3/9] Testing AI Prompt Enhancement Engine...")
        raw_prompt = "a majestic dragon flying over snowy mountain peaks"
        res = client.post(
            "/api/v1/prompts/enhance",
            headers=headers,
            json={"prompt": raw_prompt, "aspectRatio": "16:9"},
        )
        assert res.status_code == 200, f"Enhance prompt failed: {res.text}"
        enhanced = res.json()
        assert enhanced["originalPrompt"] == raw_prompt
        assert len(enhanced["enhancedPrompt"]) > len(raw_prompt)
        print(f"  --> Original Prompt: '{raw_prompt}'")
        print(f"  --> Enhanced Prompt: '{enhanced['enhancedPrompt'][:80]}...' [PASS]")

        # -------------------------------------------------------------
        # Step 4: Project Creation (Video Generation Job)
        # -------------------------------------------------------------
        print("\n[Step 4/9] Creating New Video Generation Project...")
        project_payload = {
            "title": "E2E Dragon Video",
            "prompt": enhanced["enhancedPrompt"],
            "aspectRatio": "16:9",
            "stylePreset": "cinematic",
            "cameraMotion": "zoom_in",
            "durationSeconds": 5,
        }
        res = client.post("/api/v1/projects", headers=headers, json=project_payload)
        assert res.status_code == 201, f"Project creation failed: {res.text}"
        project = res.json()
        project_id = project["id"]
        assert project["status"] in ("pending", "generating", "completed")
        print(f"  --> Created Project ID: {project_id} (Status: {project['status']}) [PASS]")

        # -------------------------------------------------------------
        # Step 5: Asynchronous Polling & Progress Tracking
        # -------------------------------------------------------------
        print("\n[Step 5/9] Polling Job Progress until Completion...")
        completed_project = None
        for attempt in range(1, 25):
            res = client.get(f"/api/v1/projects/{project_id}", headers=headers)
            assert res.status_code == 200
            curr = res.json()
            status = curr["status"]
            progress = curr.get("progress", 0)
            print(f"  --> Poll #{attempt}: status={status}, progress={progress}%")
            if status == "completed":
                completed_project = curr
                break
            time.sleep(0.1)

        assert completed_project is not None, "Project did not complete within poll limit!"
        assert completed_project["videoUrl"] is not None
        v_url = completed_project["videoUrl"]
        print(f"  --> Project Completed Successfully! Video URL: {v_url} [PASS]")

        # -------------------------------------------------------------
        # Step 6: Media & Thumbnail Byte Verification
        # -------------------------------------------------------------
        print("\n[Step 6/9] Verifying Video & Thumbnail Media Assets...")
        video_url = completed_project["videoUrl"]
        res_video = client.get(video_url)
        assert res_video.status_code == 200, f"Failed to download video: {res_video.status_code}"
        assert len(res_video.content) > 1000, "Video content is too small or empty!"
        print(f"  --> Video Media verified: {len(res_video.content)} bytes received [PASS]")

        if completed_project.get("thumbnailUrl"):
            thumb_url = completed_project["thumbnailUrl"]
            res_thumb = client.get(thumb_url)
            assert res_thumb.status_code == 200
            print(f"  --> Thumbnail Media verified: {len(res_thumb.content)} bytes received [PASS]")

        # -------------------------------------------------------------
        # Step 7: History List & Ordering Verification
        # -------------------------------------------------------------
        print("\n[Step 7/9] Verifying History List Retrieval...")
        res = client.get("/api/v1/projects", headers=headers)
        assert res.status_code == 200
        history = res.json()
        items = history.get("items", [])
        assert len(items) >= 1
        assert items[0]["id"] == project_id, "Latest project is not at top of history!"
        print(f"  --> History retrieved ({len(items)} projects). Top ID matches new project [PASS]")

        # -------------------------------------------------------------
        # Step 8: Profile & Avatar Update
        # -------------------------------------------------------------
        print("\n[Step 8/9] Updating User Profile (Username & Avatar)...")
        res = client.patch(
            "/api/v1/me",
            headers=headers,
            json={"username": "dragon_creator", "avatarPath": f"{me['id']}/avatar.jpg"},
        )
        assert res.status_code == 200, f"Profile update failed: {res.text}"
        updated_me = res.json()
        assert updated_me["username"] == "dragon_creator"
        print(f"  --> Profile updated successfully: username={updated_me['username']} [PASS]")

        # -------------------------------------------------------------
        # Step 9: Cancellation & Quota Refund Flow
        # -------------------------------------------------------------
        print("\n[Step 9/9] Testing Job Cancellation & Automatic Quota Refund...")
        q_before = client.get("/api/v1/me", headers=headers).json()["quota"]["remaining"]

        res_cancel_proj = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": "To be cancelled", "prompt": "cancel me", "aspectRatio": "9:16"},
        )
        assert res_cancel_proj.status_code == 201
        cancel_id = res_cancel_proj.json()["id"]

        res_cancel = client.post(f"/api/v1/projects/{cancel_id}/cancel", headers=headers)
        assert res_cancel.status_code == 200
        cancel_data = res_cancel.json()
        assert cancel_data["cancelled"] is True
        assert cancel_data["quotaRefunded"] is True

        q_after = client.get("/api/v1/me", headers=headers).json()["quota"]["remaining"]
        assert q_after == q_before, (
            f"Quota was not properly refunded! (before={q_before}, after={q_after})"
        )
        print(f"  --> Job cancelled & Quota successfully refunded ({q_after} remaining) [PASS]")

    print("\n" + "=" * 70)
    print(" >>> [SUCCESS] ALL 9 END-TO-END BUSINESS FLOW STEPS PASSED 100%! <<<")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Cretona Complete E2E Business Flow Tester")
    parser.add_argument(
        "--mode", choices=["dev", "live"], default="dev", help="Execution mode (dev or live)"
    )
    parser.add_argument("--token", type=str, default=None, help="Bearer token for live mode")
    args = parser.parse_args()

    token = args.token or os.environ.get("CRETONA_VERIFY_TOKEN")
    token_file = backend_dir / ".token"
    if not token and token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()

    run_e2e_business_flow(mode=args.mode, token=token)


if __name__ == "__main__":
    main()
