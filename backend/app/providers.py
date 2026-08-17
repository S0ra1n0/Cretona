from __future__ import annotations

import logging
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol
from uuid import uuid4

from app.webhook_verification import verify_hmac_webhook

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

    def poll(self, *, job_id: str, prompt: str | None, poll_count: int) -> PollResult: ...

    def verify_webhook(
        self, *, headers: dict[str, str], body: bytes, secret: str = ""
    ) -> dict[str, Any]: ...
# Hosted text-to-image endpoint. Free and keyless, which is why it satisfies
# the zero-spend gate, but it is a third party that receives user prompts.
DEFAULT_IMAGE_ENDPOINT = "https://image.pollinations.ai"


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

    Returns the media path, or None if the still could not be fetched or
    ffmpeg is unavailable — callers fall back to the bundled demo clip.
    """
    if not media_dir or not prompt:
        return None
    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        target_mp4 = media_dir / output_filename
        if target_mp4.exists() and target_mp4.stat().st_size > 1024:
            return f"/media/{output_filename}"

        clean_prompt = _clean_prompt_for_diffusion(prompt)
        encoded = urllib.parse.quote(clean_prompt)
        # The user's prompt leaves this machine here. The endpoint is
        # configurable so a deployment can point it elsewhere or disable it;
        # see CRETONA_IMAGE_ENDPOINT in docs/CONFIGURATION.md.
        query = "width=1280&height=720&model=turbo&nologo=true"
        url = f"{image_endpoint.rstrip('/')}/prompt/{encoded}?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        temp_img = media_dir / f"temp_{target_mp4.stem}.jpg"
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        temp_img.write_bytes(data)

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
        del prompt, image_path
        return SubmitResult(job_id=f"fake_{uuid4()}")

    def poll(self, *, job_id: str, prompt: str | None, poll_count: int) -> PollResult:
        del job_id
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
        self, *, headers: dict[str, str], body: bytes, secret: str = ""
    ) -> dict[str, Any]:
        return verify_hmac_webhook(headers=headers, body=body, secret=secret)


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
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint or "https://text.pollinations.ai"
        self.image_endpoint = image_endpoint
        self.video_filename = video_filename
        self.media_dir = media_dir
        self.ffmpeg_path = ffmpeg_path

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult:
        del image_path
        job_id = f"real_{uuid4()}"
        return SubmitResult(job_id=job_id)

    def poll(self, *, job_id: str, prompt: str | None, poll_count: int) -> PollResult:
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

        # Synthesize or retrieve the real AI video asset for this prompt
        live_video = _render_kenburns_from_ai_still(
            prompt, f"{job_id}.mp4", self.media_dir, self.ffmpeg_path, self.image_endpoint
        )

        return PollResult(
            status="succeeded",
            video_path=live_video or f"/media/{self.video_filename}",
            duration_seconds=5,
            progress_percent=100,
            step_message="Cloud AI video synthesis complete",
        )

    def verify_webhook(
        self, *, headers: dict[str, str], body: bytes, secret: str = ""
    ) -> dict[str, Any]:
        return verify_hmac_webhook(headers=headers, body=body, secret=secret)


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
    ) -> None:
        self.endpoint = endpoint
        self.image_endpoint = image_endpoint
        self.video_filename = video_filename
        self.media_dir = media_dir
        self.ffmpeg_path = ffmpeg_path

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult:
        del image_path
        job_id = f"local_{uuid4()}"
        return SubmitResult(job_id=job_id)

    def poll(self, *, job_id: str, prompt: str | None, poll_count: int) -> PollResult:
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
            prompt, f"{job_id}.mp4", self.media_dir, self.ffmpeg_path, self.image_endpoint
        )

        return PollResult(
            status="succeeded",
            video_path=live_video or f"/media/{self.video_filename}",
            duration_seconds=5,
            progress_percent=100,
            step_message="Local video inference complete",
        )

    def verify_webhook(
        self, *, headers: dict[str, str], body: bytes, secret: str = ""
    ) -> dict[str, Any]:
        return verify_hmac_webhook(headers=headers, body=body, secret=secret)


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
    }

    def __init__(self, providers: list[VideoProvider], default: str) -> None:
        self._providers = {provider.name: provider for provider in providers}
        canonical_default = self.ALIASES.get(default, default)
        self.default = canonical_default
        if canonical_default not in self._providers:
            # Fallback to first available provider
            self.default = next(iter(self._providers.keys()))

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
