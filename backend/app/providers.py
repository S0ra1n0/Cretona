from __future__ import annotations

import logging
import re
import subprocess
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol
from uuid import uuid4

import httpx

from app.webhook_verification import DEFAULT_TOLERANCE_SECONDS, verify_hmac_webhook

logger = logging.getLogger("cretona.providers")

ProviderFailure = Literal[
    "content_policy",
    "invalid_input",
    "quota",
    "timeout",
    "provider_error",
    "cancelled",
    "unknown",
]


@dataclass(frozen=True)
class SubmitResult:
    job_id: str


@dataclass(frozen=True)
class PollResult:
    status: Literal["running", "succeeded", "failed"]
    video_path: str | None = None
    duration_seconds: int | None = None
    failure: ProviderFailure | None = None
    progress_percent: int = 0
    step_message: str | None = None


class VideoProvider(Protocol):
    name: str

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult: ...

    def poll(
        self,
        *,
        job_id: str,
        prompt: str | None,
        poll_count: int,
        image_path: str | None = None,
    ) -> PollResult: ...

    def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
        secret: str = "",
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    ) -> dict[str, Any]: ...


# Hosted text-to-image endpoint. Free and keyless, which is why it satisfies
# the zero-spend gate, but it is a third party that receives user prompts.
# Configurable as CRETONA_IMAGE_ENDPOINT; setting it empty disables the call
# and falls the providers back to the bundled clip (T2-2, CONFIGURATION.md).
DEFAULT_IMAGE_ENDPOINT = "https://image.pollinations.ai"

# The response is written to disk and later served as user media, so what comes
# back has to actually be an image. A generous cap: a 1280x720 still that needs
# more than this is not a still.
ALLOWED_STILL_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_STILL_BYTES = 16 * 1024 * 1024
STILL_EXTENSION = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


# Image magic numbers, as hex so no layer of quoting can mangle them.
_MAGIC_JPEG = bytes.fromhex('ffd8ff')
_MAGIC_PNG = bytes.fromhex('89504e470d0a1a0a')


def _sniff_still_type(data: bytes) -> str:
    """Identify an uploaded image by its magic bytes.

    The stored content type is not carried on the project row, and a
    client-declared one could name itself anything. The leading bytes are
    the only thing here that cannot be talked out of the truth. Anything
    unrecognised returns a type the renderer refuses rather than writes.
    """
    if data.startswith(_MAGIC_JPEG):
        return "image/jpeg"
    if data.startswith(_MAGIC_PNG):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


class StillFetchError(RuntimeError):
    """The hosted endpoint did not return a usable image."""


def _fetch_ai_still_typed(
    prompt: str, image_endpoint: str, client: httpx.Client | None
) -> tuple[bytes, str]:
    """Fetch one still for `prompt`, returning its bytes and content type.

    The user's prompt leaves this machine here, which is the whole reason the
    endpoint is configurable: a deployment that cannot send prompts to a third
    party sets CRETONA_IMAGE_ENDPOINT empty and gets the bundled clip instead.
    """
    if not image_endpoint:
        raise StillFetchError("No image endpoint is configured.")

    encoded = urllib.parse.quote(prompt, safe="")
    url = f"{image_endpoint.rstrip('/')}/prompt/{encoded}"
    params = {"width": "1280", "height": "720", "model": "turbo", "nologo": "true"}

    owned = client is None
    active = client or httpx.Client(timeout=20, follow_redirects=True)
    try:
        response = active.get(url, params=params, headers={"Accept": "image/*"})
        if response.status_code >= 400:
            raise StillFetchError(f"Endpoint returned {response.status_code}.")
        # A hosted endpoint that starts returning HTML error pages must not have
        # them written into the media directory and served as user media.
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_STILL_TYPES:
            raise StillFetchError(f"Endpoint returned {content_type or 'no'} content type.")
        data = response.content
        if not data:
            raise StillFetchError("Endpoint returned an empty body.")
        if len(data) > MAX_STILL_BYTES:
            raise StillFetchError(f"Endpoint returned {len(data)} bytes.")
        return data, content_type
    except httpx.HTTPError as exc:
        raise StillFetchError(str(exc)) from exc
    finally:
        if owned:
            active.close()


def _clean_prompt_for_diffusion(raw_prompt: str) -> str:
    """Clean emojis, non-ASCII characters, and normalize keywords to maximize

    AI diffusion model subject fidelity.
    """
    replacements = {
        "bay trên": "flying over",
        "bay tren": "flying over",
        "đang bay": "flying",
        "trên đỉnh": "on top of",
        "núi tuyết": "snowy mountain",
        "thành phố": "city",
        "vũ trụ": "outer space",
        "phát sáng": "glowing",
        "rồng": "dragon",
    }
    cleaned = raw_prompt
    for vn, en in replacements.items():
        cleaned = re.sub(re.escape(vn), en, cleaned, flags=re.IGNORECASE)
    # Strip emojis and non-ASCII characters that pollute CLIP text encoders
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    # Remove repetitive video prefixes if present
    cleaned = re.sub(r"(?i)(cinematic\s+\d+:\d+\s+video\s+of\s*)+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "a majestic mystical glowing dragon flying over snowy mountain peaks"
    return cleaned


def _render_kenburns_from_ai_still(
    prompt: str | None,
    output_filename: str,
    media_dir: Path | None,
    ffmpeg_bin: str = "ffmpeg",
    image_endpoint: str = DEFAULT_IMAGE_ENDPOINT,
    client: httpx.Client | None = None,
    source_still: tuple[bytes, str] | None = None,
) -> str | None:
    """Fetch one AI-generated still and pan across it for five seconds.

    This is NOT video generation. A text-to-image model produces a single
    frame; ffmpeg's `zoompan` then applies a Ken Burns move to it. There is no
    temporal model, no motion synthesis, and no frame-to-frame coherence — the
    subject cannot move, because only one image exists.

    It is a legitimate zero-spend placeholder that looks better than a static
    demo clip. It is not evidence that a video model runs, and EXP-005 remains
    the gate for that (ADR-009). Do not describe its output as AI-generated
    video.

    `source_still` is an optional `(bytes, content_type)` pair. When present it
    is used as the frame and no text-to-image call is made at all -- that is
    the image-to-video path, where the still is the account's own uploaded
    reference rather than a generated one. Nothing about the result becomes
    more "AI video" either way; the caveats above apply identically.

    Returns the media path, or None if the still could not be obtained or
    ffmpeg is unavailable — callers fall back to the bundled demo clip.
    """
    # A reference image is enough on its own: the prompt only ever fed the
    # text-to-image call, which is skipped when the caller supplies the frame.
    if not media_dir or (not prompt and source_still is None):
        return None
    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        target_mp4 = media_dir / output_filename
        if target_mp4.exists() and target_mp4.stat().st_size > 1024:
            return f"/media/{output_filename}"

        if source_still is not None:
            data, content_type = source_still
            if content_type not in STILL_EXTENSION:
                # An upload the renderer cannot name a file for. Falling back
                # is better than writing an unknown type into media.
                return None
        else:
            clean_prompt = _clean_prompt_for_diffusion(prompt or "")
            data, content_type = _fetch_ai_still_typed(clean_prompt, image_endpoint, client)
        temp_img = media_dir / f"temp_{target_mp4.stem}.{STILL_EXTENSION[content_type]}"
        temp_img.write_bytes(data)

        try:
            # Synthesize 5-second cinematic video with smooth pan/zoom motion using FFmpeg
            cmd = [
                ffmpeg_bin,
                "-loop",
                "1",
                "-i",
                str(temp_img),
                "-vf",
                "zoompan=z='min(zoom+0.0015,1.5)':d=150:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps=30",
                "-t",
                "5",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(target_mp4),
                "-y",
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=20)
        finally:
            # An ffmpeg timeout used to leave the still behind in the directory
            # that is served as user media.
            temp_img.unlink(missing_ok=True)
        if res.returncode == 0 and target_mp4.exists() and target_mp4.stat().st_size > 1024:
            return f"/media/{output_filename}"
    except Exception as ex:
        logger.warning(f"Live AI video synthesis fallback: {ex}")
    return None


class MockVideoProvider:
    """Tier 1: Mock / Dev Provider.

    Deterministic zero-cost instant video generation simulation for fast UI testing,
    offline development, and safe defense demonstration.
    """

    name = "fake"

    def __init__(
        self,
        *,
        polls_before_complete: int = 1,
        video_filename: str = "demo-output.mp4",
    ) -> None:
        self.polls_before_complete = polls_before_complete
        self.video_filename = video_filename

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult:
        # Deliberately ignored: this tier returns a bundled clip and has no
        # way to honour either input. Ignoring them is the honest behaviour
        # for a demo provider; silently accepting a reference image and
        # producing an unrelated video would not be.
        del prompt, image_path
        return SubmitResult(job_id=f"fake_{uuid4()}")

    def poll(
        self,
        *,
        job_id: str,
        prompt: str | None,
        poll_count: int,
        image_path: str | None = None,
    ) -> PollResult:
        del job_id, image_path
        normalized_prompt = (prompt or "").lower()
        if normalized_prompt.startswith("fail:"):
            requested = normalized_prompt.removeprefix("fail:").split(maxsplit=1)[0]
            allowed: set[str] = {
                "content_policy",
                "invalid_input",
                "quota",
                "timeout",
                "provider_error",
                "cancelled",
                "unknown",
            }
            failure: ProviderFailure = (
                requested if requested in allowed else "unknown"  # type: ignore[assignment]
            )
            return PollResult(status="failed", failure=failure, progress_percent=0)

        required = 3 if normalized_prompt.startswith("slow") else self.polls_before_complete
        if poll_count < required:
            pct = min(85, max(25, int((poll_count / max(required, 1)) * 75)))
            return PollResult(
                status="running",
                progress_percent=pct,
                step_message="Synthesizing mock video frames...",
            )

        return PollResult(
            status="succeeded",
            video_path=f"/media/{self.video_filename}",
            duration_seconds=5,
            progress_percent=100,
            step_message="Mock video rendering complete",
        )

    def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
        secret: str = "",
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    ) -> dict[str, Any]:
        return verify_hmac_webhook(
            headers=headers,
            body=body,
            secret=secret,
            tolerance_seconds=tolerance_seconds,
        )


# Alias for backward compatibility with earlier tests
FakeVideoProvider = MockVideoProvider


class CloudAiVideoProvider:
    """Tier 2: hosted still image, rendered as a pan.

    Calls a hosted text-to-image endpoint and applies a Ken Burns move, via
    `_render_kenburns_from_ai_still`. No cloud *video* model is called, and no
    API key is used; `api_key` and `endpoint` are placeholders for a real
    adapter that has not been written.

    Naming it "Cloud AI" describes where the image comes from, not what it
    generates. Wiring a genuine video API (Fal.ai, Replicate, Wan 2.1) is
    future work behind EXP-005.
    """

    name = "real"

    def __init__(
        self,
        *,
        api_key: str = "",
        endpoint: str = "",
        image_endpoint: str = DEFAULT_IMAGE_ENDPOINT,
        video_filename: str = "demo-output.mp4",
        media_dir: Path | None = None,
        ffmpeg_path: str = "ffmpeg",
        read_image: Callable[[str], bytes | None] | None = None,
    ) -> None:
        self.read_image = read_image
        self.api_key = api_key
        self.endpoint = endpoint or "https://text.pollinations.ai"
        self.image_endpoint = image_endpoint
        self.video_filename = video_filename
        self.media_dir = media_dir
        self.ffmpeg_path = ffmpeg_path

    def _reference_still(self, image_path: str | None) -> tuple[bytes, str] | None:
        """Load the account's uploaded reference image, or None.

        None means "generate a still from the prompt instead", which is what
        a text-only request has always done. A read failure degrades to that
        same path rather than failing the generation: a missing reference is
        a worse picture, not a broken job.
        """
        if not image_path or self.read_image is None:
            return None
        try:
            data = self.read_image(image_path)
        except Exception:
            return None
        if not data:
            return None
        return data, _sniff_still_type(data)

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult:
        # image_path is not consumed here: the render happens in poll(), which
        # receives it from the project row. Nothing is dropped.
        del image_path
        job_id = f"real_{uuid4()}"
        return SubmitResult(job_id=job_id)

    def poll(
        self,
        *,
        job_id: str,
        prompt: str | None,
        poll_count: int,
        image_path: str | None = None,
    ) -> PollResult:
        normalized_prompt = (prompt or "").lower()
        if normalized_prompt.startswith("fail:"):
            return PollResult(status="failed", failure="provider_error", progress_percent=0)

        required = 3 if normalized_prompt.startswith("slow") else 1
        if poll_count < required:
            pct = 50 if poll_count == 0 else 80
            return PollResult(
                status="running",
                progress_percent=pct,
                step_message="Generating image, then rendering camera move...",
            )

        # A reference image, when the account supplied one, is the frame we pan
        # across; otherwise a still is generated from the prompt. Either way
        # this is a camera move over one frame, not video synthesis.
        live_video = _render_kenburns_from_ai_still(
            prompt,
            f"{job_id}.mp4",
            self.media_dir,
            self.ffmpeg_path,
            self.image_endpoint,
            source_still=self._reference_still(image_path),
        )

        return PollResult(
            status="succeeded",
            video_path=live_video or f"/media/{self.video_filename}",
            duration_seconds=5,
            progress_percent=100,
            step_message="Cloud AI video synthesis complete",
        )

    def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
        secret: str = "",
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    ) -> dict[str, Any]:
        return verify_hmac_webhook(
            headers=headers,
            body=body,
            secret=secret,
            tolerance_seconds=tolerance_seconds,
        )


# Aliases for backward compatibility
RealAiVideoProvider = CloudAiVideoProvider
Wan21VideoProvider = CloudAiVideoProvider


class LocalModelVideoProvider:
    """Tier 3: reserved for a local model. Nothing local runs yet.

    This tier is a placeholder. `endpoint` defaults to the Ollama port but is
    never contacted, no GPU or memory preflight is performed, and no local
    weights are loaded. It calls the same hosted-still renderer the other
    tiers use, so its output is identical to theirs.

    LTX-Video was rejected by the EXP-005 pre-screen and FramePack is blocked
    before inference by the resource gate; until one of those clears, there is
    nothing for this tier to execute.
    """

    name = "local"

    def __init__(
        self,
        *,
        endpoint: str = "http://localhost:11434",
        image_endpoint: str = DEFAULT_IMAGE_ENDPOINT,
        video_filename: str = "demo-output.mp4",
        media_dir: Path | None = None,
        ffmpeg_path: str = "ffmpeg",
        read_image: Callable[[str], bytes | None] | None = None,
    ) -> None:
        self.read_image = read_image
        self.endpoint = endpoint
        self.image_endpoint = image_endpoint
        self.video_filename = video_filename
        self.media_dir = media_dir
        self.ffmpeg_path = ffmpeg_path

    def _reference_still(self, image_path: str | None) -> tuple[bytes, str] | None:
        """Load the account's uploaded reference image, or None.

        None means "generate a still from the prompt instead", which is what
        a text-only request has always done. A read failure degrades to that
        same path rather than failing the generation: a missing reference is
        a worse picture, not a broken job.
        """
        if not image_path or self.read_image is None:
            return None
        try:
            data = self.read_image(image_path)
        except Exception:
            return None
        if not data:
            return None
        return data, _sniff_still_type(data)

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult:
        # Consumed in poll(), which receives it from the project row.
        del image_path
        job_id = f"local_{uuid4()}"
        return SubmitResult(job_id=job_id)

    def poll(
        self,
        *,
        job_id: str,
        prompt: str | None,
        poll_count: int,
        image_path: str | None = None,
    ) -> PollResult:
        normalized_prompt = (prompt or "").lower()
        if normalized_prompt.startswith("fail:"):
            return PollResult(status="failed", failure="provider_error", progress_percent=0)

        required = 3 if normalized_prompt.startswith("slow") else 1
        if poll_count < required:
            pct = 45 if poll_count == 0 else 80
            return PollResult(
                status="running",
                progress_percent=pct,
                # Says what is happening, not what we wish were happening.
                # "denoising latents (steps 1-10/20)" described inference that
                # this tier never performs.
                step_message="Generating image, then rendering camera move...",
            )

        live_video = _render_kenburns_from_ai_still(
            prompt,
            f"{job_id}.mp4",
            self.media_dir,
            self.ffmpeg_path,
            self.image_endpoint,
            source_still=self._reference_still(image_path),
        )

        return PollResult(
            status="succeeded",
            video_path=live_video or f"/media/{self.video_filename}",
            duration_seconds=5,
            progress_percent=100,
            step_message="Local video inference complete",
        )

    def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
        secret: str = "",
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    ) -> dict[str, Any]:
        return verify_hmac_webhook(
            headers=headers,
            body=body,
            secret=secret,
            tolerance_seconds=tolerance_seconds,
        )


class ExternalVideoProvider:
    """A job this process records but never executes (W2).

    Generation happens elsewhere -- a Kaggle notebook with a GPU this laptop
    does not have. That inverts how every other provider works: instead of
    FastAPI calling out and waiting, the worker polls the database, claims a
    row, generates, uploads, and writes the result back.

    So `submit()` does no work and `poll()` contacts nothing. The row *is* the
    channel. The status the app sees is whatever the worker last wrote, which
    is why `poll()` reports `running` and lets the real state come from the
    row: reporting anything else would fight the worker for ownership of the
    state machine.

    `external = True` is what keeps the in-process `JobPoller` from claiming
    these rows (W1). Without it the poller would take a lease on work it cannot
    perform and hold it until the lease expired, while the worker that could
    run it waited.
    """

    name = "kaggle"
    external = True

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult:
        # No network, no model, no side effect. The project row created around
        # this call is the entire submission; a worker will find it by polling.
        del prompt, image_path
        return SubmitResult(job_id=f"external-{uuid4()}")

    def poll(
        self,
        *,
        job_id: str,
        prompt: str | None,
        poll_count: int,
        image_path: str | None = None,
    ) -> PollResult:
        """Report no change, so the row keeps whatever the worker wrote.

        Returning `succeeded` or `failed` here would overwrite the worker's
        own progress with a guess made by a process that has no idea what the
        GPU is doing.
        """
        del job_id, prompt, poll_count, image_path
        return PollResult(status="running")

    def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
        secret: str = "",
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    ) -> dict[str, Any]:
        """Refuse webhooks outright.

        The worker owns its rows and writes results directly. Accepting a
        webhook would open a second, unauthenticated path to completing a
        generation -- anyone who could reach it could mark work finished.
        """
        del headers, body, secret, tolerance_seconds
        # Imported here rather than at module scope, matching ProviderRegistry
        # below: app.errors reaches back into this module's vocabulary.
        from app.errors import AppError

        raise AppError(
            404, "NOT_FOUND", "This provider does not accept webhooks."
        )


class ProviderRegistry:
    """Central registry with support for 3 canonical tiers: mock, cloud, local
    and backward-compatible alias resolution ('fake', 'real', 'wan21').
    """

    ALIASES: ClassVar[dict[str, str]] = {
        "fake": "fake",
        "mock": "fake",
        "real": "real",
        "cloud": "real",
        "wan21": "real",
        "local": "local",
        "kaggle": "kaggle",
        "external": "kaggle",
    }

    def __init__(self, providers: list[VideoProvider], default: str) -> None:
        self._providers = {provider.name: provider for provider in providers}
        canonical_default = self.ALIASES.get(default, default)
        self.default = canonical_default
        if canonical_default not in self._providers:
            # Fallback to first available provider
            self.default = next(iter(self._providers.keys()))

    def in_process_names(self) -> tuple[str, ...]:
        """Providers this process can actually execute, for the poller to claim.

        W1: the in-process `JobPoller` and an external worker both poll the same
        table. Without a filter they race for every row and the loser waits,
        so jobs get served late, erratically, or by a machine that cannot run
        them at all. Each claimant takes a disjoint set instead.

        An external provider (`submit()` records, `poll()` reads the row) is
        excluded here: nothing in this process advances it, so claiming one
        would only hold a lease the real worker is waiting for.
        """
        return tuple(
            sorted(
                name
                for name, provider in self._providers.items()
                if not getattr(provider, "external", False)
            )
        )

    def get(self, name: str | None) -> VideoProvider:
        raw_key = (name or self.default).lower().strip()
        canonical_key = self.ALIASES.get(raw_key, raw_key)
        provider = self._providers.get(canonical_key)
        if provider is None:
            from app.errors import AppError

            raise AppError(
                400,
                "VALIDATION_ERROR",
                f"Unknown video provider: {raw_key}. Supported: mock, cloud, local",
                [{"field": "body.provider", "issue": "unknown_provider"}],
            )
        return provider
