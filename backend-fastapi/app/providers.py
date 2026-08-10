from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
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


class FakeVideoProvider:
    """Deterministic provider used for tests and the zero-spend demo."""

    name = "fake"

    def __init__(self, *, polls_before_complete: int, video_filename: str) -> None:
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

