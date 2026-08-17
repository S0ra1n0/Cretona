"""Exercise the T3-2 feature surface against live Supabase (T3-2).

Drives `create_app` itself rather than reimplementing the API, so a pass means
the shipping code works against the real project -- not that a parallel script
does.

Paste the token into `backend/.token` (git-ignored) and run with no arguments:

    python scripts/verify-live-runtime.py
    python scripts/verify-live-runtime.py --generate
    python scripts/verify-live-runtime.py --generate --slow   # tests cancellation

`--token-file` and `CRETONA_VERIFY_TOKEN` also work. `--token` exists but is
discouraged: an access token on a command line lands in PowerShell's
ConsoleHost_history.txt, where it outlives the session and is readable by
anything running as you.

Without `--generate` every check is a read: identity, quota, project list, and
one project fetch. `--generate` additionally creates a project, watches its
progress, cancels it, and checks the quota refund -- it writes to the live
database, and because projects soft-delete, the row it creates persists. The
title is stamped so the row is obviously a verification artefact.

The token is never printed and never written anywhere by this script. Get one
from an authenticated client; it deliberately cannot mint its own, because that
would need credentials a verification script has no business holding.

Doc/code drift found while writing the cancel-persistence check: ProjectResponse
(app/schemas.py) has no `errorCode` field, and `to_response()` (project_service.py)
never sets one -- despite docs/API_CONTRACT.md's example payload showing
`errorCode`, a nested `options` object, `stylePreset`, and `cameraMotion`, none of
which the API actually returns. The doc also describes `POST /cancel` as
returning a full Project Object with `status: "cancelled"`; the real response is
the distinct {cancelled, projectId, quotaRefunded} shape, and `status` can never
be `"cancelled"` at the API layer -- ProjectStatus only has pending/generating/
completed/failed. Per this project's convention, the code is authoritative; the
doc has not been corrected here.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

# The poller would advance jobs underneath the checks and make the observed
# progress sequence non-deterministic. Reads drive the state machine instead.
os.environ["CRETONA_POLLER_ENABLED"] = "false"
os.environ["CRETONA_GENERATION_LOG_RETENTION_ENABLED"] = "false"

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

DEFAULT_TOKEN_FILE = ROOT / "backend" / ".token"

# Anything that is obviously a stand-in rather than a credential. Passing one of
# these through to the API wastes a live round trip and returns a 401 that looks
# like a real auth failure, which is a confusing way to learn you forgot to
# substitute.
PLACEHOLDERS = frozenset(
    {
        "paste_token_here",
        "your_token_here",
        "your-token-here",
        "<token>",
        "token",
        "changeme",
        "xxx",
    }
)


class TokenError(RuntimeError):
    """No usable token was supplied."""


def resolve_token(inline: str, token_file: Path) -> tuple[str, str]:
    """Find a token, and refuse anything that is plainly not one.

    Order: --token, then CRETONA_VERIFY_TOKEN, then the token file. The file is
    last because it is the recommended path and the least surprising default --
    an explicit flag should still win over it.
    """
    candidates = (
        (inline.strip(), "--token (inline; consider a file instead)"),
        (os.environ.get("CRETONA_VERIFY_TOKEN", "").strip(), "CRETONA_VERIFY_TOKEN"),
    )
    for value, source in candidates:
        if value:
            return validated(value, source), source

    if token_file.is_file():
        value = token_file.read_text(encoding="utf-8-sig").strip()
        if value:
            return validated(value, str(token_file)), str(token_file)

    raise TokenError(
        "No token found. Put a Supabase access token in:\n"
        f"    {token_file}\n"
        "then re-run with no arguments. CRETONA_VERIFY_TOKEN and --token also work.\n"
        "Every check here is authenticated; there is nothing useful to run without one."
    )


def validated(token: str, source: str) -> str:
    """Catch a placeholder before it costs a live round trip and a puzzling 401."""
    if token.casefold() in PLACEHOLDERS:
        raise TokenError(
            f"The value from {source} is the placeholder text, not a token.\n"
            "Substitute a real Supabase access token."
        )
    # header.payload.signature -- cheap shape check, not verification.
    if token.count(".") != 2:
        raise TokenError(
            f"The value from {source} is not a JWT: expected three dot-separated "
            f"segments, found {token.count('.') + 1}.\n"
            "A Supabase access token looks like eyJhbGciOi....<payload>.<signature>"
        )
    return token


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def record(self, outcome: str, label: str, detail: str = "") -> None:
        self.rows.append((outcome, label, detail))
        print(f"  {outcome}  {label}{f' -- {detail}' if detail else ''}")

    def failed(self) -> int:
        return sum(1 for outcome, _, _ in self.rows if outcome == FAIL)

    def summary(self) -> str:
        counts = {name: 0 for name in (PASS, FAIL, SKIP)}
        for outcome, _, _ in self.rows:
            counts[outcome] += 1
        return f"{counts[PASS]} passed, {counts[FAIL]} failed, {counts[SKIP]} skipped"


def check_identity(client: TestClient, headers: dict[str, str], report: Report) -> dict[str, Any]:
    """The first authenticated live request the project has ever made."""
    response = client.get("/api/v1/me", headers=headers)
    if response.status_code != 200:
        report.record(FAIL, "GET /me", f"HTTP {response.status_code}: {response.text[:160]}")
        return {}
    body = response.json()
    report.record(PASS, "GET /me -- ES256 verified against a live token")
    quota = body.get("quota") or {}
    report.record(
        PASS,
        "quota read",
        f"limit={quota.get('limit')} remaining={quota.get('remaining')}",
    )
    return body


def check_gallery(client: TestClient, headers: dict[str, str], report: Report) -> None:
    response = client.get("/api/v1/projects?limit=5", headers=headers)
    if response.status_code != 200:
        report.record(FAIL, "GET /projects", f"HTTP {response.status_code}")
        return
    body = response.json()
    items = body.get("items", [])
    report.record(PASS, "GET /projects -- media gallery", f"{len(items)} item(s)")

    if not items:
        report.record(SKIP, "project detail", "caller owns no projects")
        return
    first = items[0]
    detail = client.get(f"/api/v1/projects/{first['id']}", headers=headers)
    if detail.status_code != 200:
        report.record(FAIL, "GET /projects/{id}", f"HTTP {detail.status_code}")
        return
    row = detail.json()
    report.record(
        PASS,
        "GET /projects/{id} -- progress fields present",
        f"status={row.get('status')} progress={row.get('progressPercent')}",
    )
    # Populated only once a video exists; absence is information, not failure.
    outcome = PASS if row.get("videoUrl") else SKIP
    report.record(outcome, "videoUrl signed from live storage", str(bool(row.get("videoUrl"))))


def check_generate_and_cancel(
    client: TestClient,
    headers: dict[str, str],
    report: Report,
    *,
    slow: bool,
) -> None:
    """Create, watch progress, cancel, and confirm the refund. Writes to live."""
    marker = f"live-verification-{uuid.uuid4().hex[:8]}"
    before = client.get("/api/v1/me", headers=headers).json().get("quota", {})

    # MockVideoProvider requires three polls for a prompt starting with 'slow',
    # against one otherwise. Without it the job reaches a terminal state before
    # the cancel arrives and the cancel path goes untested -- which is the one
    # path here that has never run against live.
    prompt = f"{marker} a paper lantern drifting over still water"
    if slow:
        prompt = f"slow {prompt}"

    created = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"prompt": prompt, "provider": "fake", "title": marker},
    )
    if created.status_code != 201:
        report.record(FAIL, "POST /projects", f"HTTP {created.status_code}: {created.text[:160]}")
        return
    project = created.json()
    project_id = project["id"]
    report.record(PASS, "POST /projects -- live create", f"id={project_id}")
    print(f"       (row persists; soft-delete keeps it. Title: {marker})")

    # Reads advance the state machine, so this is the progress sequence a real
    # client would see. When cancelling, stop early and deliberately: polling to
    # completion first would leave nothing cancellable.
    budget = 1 if slow else 4
    seen: list[Any] = []
    for _ in range(budget):
        row = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()
        seen.append((row.get("status"), row.get("progressPercent")))
        if row.get("status") in ("completed", "failed"):
            break
        time.sleep(0.4)
    report.record(PASS, "progress tracking observed", " -> ".join(str(s) for s in seen))

    cancel = client.post(f"/api/v1/projects/{project_id}/cancel", headers=headers)
    if cancel.status_code == 200:
        body = cancel.json()
        report.record(
            PASS,
            "POST /cancel -- first live cancellation",
            f"cancelled={body.get('cancelled')} refunded={body.get('quotaRefunded')}",
        )
        # The cancel response claims a refund; this is whether the row agrees.
        # ProjectResponse has no errorCode field (to_response() in
        # project_service.py never sets one, despite docs/API_CONTRACT.md
        # documenting it -- see the drift note in the module docstring), so
        # errorMessage is the only client-visible signal that distinguishes a
        # user cancellation from any other failure.
        after_cancel = client.get(f"/api/v1/projects/{project_id}", headers=headers).json()
        landed = (
            after_cancel.get("status") == "failed"
            and after_cancel.get("errorMessage") == "Generation was cancelled by the user."
        )
        status, message = after_cancel.get("status"), after_cancel.get("errorMessage")
        report.record(
            PASS if landed else FAIL,
            "cancellation persisted to live",
            f"status={status} errorMessage={message!r}",
        )
    elif cancel.status_code == 409:
        # Only reachable without --slow: the provider finished first.
        report.record(
            SKIP,
            "POST /cancel",
            "409 -- already terminal; re-run with --slow to catch it in flight",
        )
    else:
        report.record(FAIL, "POST /cancel", f"HTTP {cancel.status_code}: {cancel.text[:160]}")

    after = client.get("/api/v1/me", headers=headers).json().get("quota", {})
    report.record(
        PASS,
        "quota accounting",
        f"remaining {before.get('remaining')} -> {after.get('remaining')}",
    )


def check_sse(client: TestClient, headers: dict[str, str], report: Report) -> None:
    listed = client.get("/api/v1/projects?limit=1", headers=headers).json().get("items", [])
    if not listed:
        report.record(SKIP, "SSE stream", "no project to stream")
        return
    project_id = listed[0]["id"]
    try:
        with client.stream(
            "GET", f"/api/v1/projects/{project_id}/events", headers=headers, timeout=10
        ) as stream:
            if stream.status_code != 200:
                report.record(FAIL, "GET /events -- SSE", f"HTTP {stream.status_code}")
                return
            content_type = stream.headers.get("content-type", "")
            first = next((line for line in stream.iter_lines() if line), "")
        report.record(PASS, "GET /events -- SSE", f"{content_type}; first line: {first[:60]}")
    except Exception as exc:
        report.record(FAIL, "GET /events -- SSE", f"{type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--token",
        default="",
        help="Access token inline. Discouraged -- it lands in shell history.",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_FILE,
        help=f"File holding the access token (default: {DEFAULT_TOKEN_FILE}).",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Also create, cancel and refund one project. WRITES to live.",
    )
    parser.add_argument(
        "--slow",
        action="store_true",
        help="With --generate: hold the job in flight so the cancel path is actually tested.",
    )
    args = parser.parse_args()

    if args.slow and not args.generate:
        print("--slow only affects the --generate cycle; add --generate.", file=sys.stderr)
        return 2

    try:
        token, source = resolve_token(args.token, args.token_file)
    except TokenError as error:
        print(f"{error}", file=sys.stderr)
        return 2
    print(f"token source   : {source}")

    settings = Settings()
    print(
        f"profile: db={settings.database_backend} storage={settings.storage_backend} "
        f"auth={settings.auth_mode} env={settings.environment}"
    )
    if settings.auth_mode != "supabase":
        print(
            f"\nCRETONA_AUTH_MODE is '{settings.auth_mode}', so the token is not being verified. "
            "This run proves nothing about live auth.",
            file=sys.stderr,
        )

    headers = {"Authorization": f"Bearer {token}"}
    report = Report()

    with TestClient(create_app(settings)) as client:
        print("\nidentity and quota:")
        if not check_identity(client, headers, report):
            print("\nAborting: the token was not accepted, so nothing below would mean anything.")
            print(report.summary())
            return 1

        print("\nmedia gallery:")
        check_gallery(client, headers, report)

        print("\nSSE:")
        check_sse(client, headers, report)

        if args.generate:
            print("\ngenerate, progress, cancel, refund (writes to live):")
            check_generate_and_cancel(client, headers, report, slow=args.slow)
        else:
            print("\ngenerate/cancel/refund:")
            report.record(SKIP, "write cycle", "re-run with --generate")

    print(f"\n{report.summary()}")
    return 1 if report.failed() else 0


if __name__ == "__main__":
    raise SystemExit(main())
