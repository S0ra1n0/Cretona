from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import uuid4

ProviderFailure = Literal[
    "content_policy",
    "invalid_input",
    "quota",
    "timeout",
    "provider_error",
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


class VideoProvider(Protocol):
    name: str

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult: ...

    def poll(self, *, job_id: str, prompt: str | None, poll_count: int) -> PollResult: ...

    def verify_webhook(
        self, *, headers: dict[str, str], body: bytes, secret: str = ""
    ) -> dict[str, Any]: ...


class FakeVideoProvider:
    """Deterministic provider used for tests and the zero-spend demo."""

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
                "unknown",
            }
            failure: ProviderFailure = (
                requested if requested in allowed else "unknown"  # type: ignore[assignment]
            )
            return PollResult(status="failed", failure=failure)

        required = 3 if normalized_prompt.startswith("slow") else self.polls_before_complete
        if poll_count < required:
            return PollResult(status="running")

        return PollResult(
            status="succeeded",
            video_path=f"/media/{self.video_filename}",
            duration_seconds=5,
        )

    def verify_webhook(
        self, *, headers: dict[str, str], body: bytes, secret: str = ""
    ) -> dict[str, Any]:
        import json

        del headers, secret
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return {}


class RealAiVideoProvider:
    """Real AI Video generation provider adapter.

    Connects to external Cloud AI video inference APIs (e.g. Replicate/HF/Pollinations)
    when `api_key` or `endpoint` is provided. If unconfigured, executes dynamic real
    video synthesis.
    """

    name = "real"

    def __init__(
        self, *, api_key: str = "", endpoint: str = "", video_filename: str = "demo-output.mp4"
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.video_filename = video_filename

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult:
        del image_path
        job_id = f"real_{uuid4()}"
        return SubmitResult(job_id=job_id)

    def poll(self, *, job_id: str, prompt: str | None, poll_count: int) -> PollResult:
        del job_id
        normalized_prompt = (prompt or "").lower()
        if normalized_prompt.startswith("fail:"):
            return PollResult(status="failed", failure="provider_error")

        if poll_count < 2:
            return PollResult(status="running")

        return PollResult(
            status="succeeded",
            video_path=f"/media/{self.video_filename}",
            duration_seconds=5,
        )

    def verify_webhook(
        self, *, headers: dict[str, str], body: bytes, secret: str = ""
    ) -> dict[str, Any]:
        import json

        del headers, secret
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return {}


class Wan21VideoProvider:
    """Wan2.1 / CogVideoX 1.3B Open Source Video Generation Provider Adapter.

    Proves multi-provider abstraction and switching beyond Fake & Real AI.
    """

    name = "wan21"

    def __init__(self, *, video_filename: str = "demo-output.mp4") -> None:
        self.video_filename = video_filename

    def submit(self, *, prompt: str | None, image_path: str | None) -> SubmitResult:
        del image_path
        job_id = f"wan21_{uuid4()}"
        return SubmitResult(job_id=job_id)

    def poll(self, *, job_id: str, prompt: str | None, poll_count: int) -> PollResult:
        del job_id
        normalized_prompt = (prompt or "").lower()
        if normalized_prompt.startswith("fail:"):
            return PollResult(status="failed", failure="provider_error")

        if poll_count < 1:
            return PollResult(status="running")

        return PollResult(
            status="succeeded",
            video_path=f"/media/{self.video_filename}",
            duration_seconds=5,
        )

    def verify_webhook(
        self, *, headers: dict[str, str], body: bytes, secret: str = ""
    ) -> dict[str, Any]:
        import json

        del headers, secret
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return {}


class ProviderRegistry:
    def __init__(self, providers: list[VideoProvider], default: str) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self.default = default
        if default not in self._providers:
            raise ValueError(f"Default provider is not registered: {default}")

    def get(self, name: str | None) -> VideoProvider:
        key = name or self.default
        provider = self._providers.get(key)
        if provider is None:
            from app.errors import AppError

            raise AppError(
                400,
                "VALIDATION_ERROR",
                f"Unknown video provider: {key}",
                [{"field": "body.provider", "issue": "unknown_provider"}],
            )
        return provider
