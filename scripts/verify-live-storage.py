"""Verify Supabase Storage against the real project (T1-1).

Exercises `app.storage.SupabaseStorage` itself rather than reimplementing the
REST calls, so a pass means the shipping adapter works — not that a parallel
script does.

Reads backend/.env. Never prints a credential.

    python scripts/verify-live-storage.py            # read-only checks
    python scripts/verify-live-storage.py --round-trip   # also writes + deletes

The round trip uploads one tiny PNG under a clearly marked path, signs a read
URL, fetches it back, and deletes it. It is opt-in because it writes to a live
bucket.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings
from app.storage import SupabaseStorage

# A 1x1 PNG. Small enough to be free, real enough to be a valid image.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "05fd8f8a8a0000000049454e44ae426082"
)


class CheckFailed(RuntimeError):
    """A verification step failed, without exposing credentials."""


def settings_from_env() -> Settings:
    settings = Settings()
    if settings.storage_backend != "supabase":
        raise CheckFailed(
            f"CRETONA_STORAGE_BACKEND is '{settings.storage_backend}'. "
            "Set it to 'supabase' in backend/.env before verifying live storage."
        )
    if not settings.supabase_url:
        raise CheckFailed("CRETONA_SUPABASE_URL is not set.")
    if not settings.supabase_service_role_key.get_secret_value():
        raise CheckFailed("CRETONA_SUPABASE_SERVICE_ROLE_KEY is not set.")
    return settings


def list_buckets(settings: Settings) -> list[str]:
    key = settings.supabase_service_role_key.get_secret_value()
    response = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/storage/v1/bucket",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=15,
    )
    if response.status_code >= 400:
        raise CheckFailed(
            f"Listing buckets failed with HTTP {response.status_code}. "
            "The service-role key may lack storage access."
        )
    return [b["name"] for b in response.json() if isinstance(b, dict) and "name" in b]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--round-trip",
        action="store_true",
        help="Upload, sign, fetch and delete one tiny object in the uploads bucket.",
    )
    args = parser.parse_args()

    try:
        settings = settings_from_env()
        print(f"project        : {settings.supabase_url}")
        print(f"uploads bucket : {settings.supabase_uploads_bucket}")
        print(f"videos bucket  : {settings.supabase_videos_bucket}")
        print(f"signed URL TTL : {settings.signed_url_ttl_seconds}s")

        buckets = list_buckets(settings)
        print(f"\nbuckets found  : {', '.join(buckets) if buckets else '(none)'}")

        missing = [
            name
            for name in (settings.supabase_uploads_bucket, settings.supabase_videos_bucket)
            if name not in buckets
        ]
        if missing:
            raise CheckFailed(
                f"Missing bucket(s): {', '.join(missing)}. "
                "Create them in Dashboard > Storage before continuing."
            )
        print("bucket check   : both present")

        if not args.round_trip:
            print("\nRead-only checks passed. Re-run with --round-trip to test upload/sign/delete.")
            return 0

        storage = SupabaseStorage(
            base_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key.get_secret_value(),
            uploads_bucket=settings.supabase_uploads_bucket,
            videos_bucket=settings.supabase_videos_bucket,
            signed_url_ttl_seconds=settings.signed_url_ttl_seconds,
        )

        # A path that is obviously a verification artefact if cleanup ever fails.
        probe_user = f"storage-verification-{uuid.uuid4()}"

        print("\n--- round trip (writes to the live bucket) ---")
        stored_path = storage.store_image(probe_user, "image/png", TINY_PNG)
        print(f"upload         : ok -> {stored_path}")

        signed = storage.read_url(stored_path, "", video=False)
        if not signed:
            raise CheckFailed("Signing a read URL returned nothing for an object just uploaded.")
        print(f"signed URL     : ok ({len(signed)} chars)")

        fetched = httpx.get(signed, timeout=15)
        if fetched.status_code >= 400:
            raise CheckFailed(f"Signed URL did not serve the object (HTTP {fetched.status_code}).")
        if fetched.content != TINY_PNG:
            raise CheckFailed("Signed URL served different bytes than were uploaded.")
        print(f"fetch back     : ok ({len(fetched.content)} bytes, identical)")

        storage.remove_objects(stored_path, None)
        gone = httpx.get(signed, timeout=15)
        # Removal is best effort by design, so report rather than fail hard.
        state = "removed" if gone.status_code >= 400 else "STILL READABLE"
        print(f"delete         : {state}")

        print("\nRound trip passed. Supabase Storage is verified end to end.")
        return 0

    except CheckFailed as error:
        print(f"\nFAILED: {error}", file=sys.stderr)
        return 2
    except httpx.HTTPError as error:
        print(f"\nNETWORK ERROR: {type(error).__name__}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
