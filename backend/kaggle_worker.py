"""Claim Cretona jobs from Supabase and render them with Wan2.1 on Kaggle.

Run from a private Kaggle notebook. Secrets come only from environment
variables/Kaggle Secrets; this module never needs a Supabase service-role key.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

MODEL_REPO = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
MODEL_REVISION = "0fad780a534b6463e45facd96134c9f345acfa5b"
NEGATIVE_PROMPT = (
    "blurry, low quality, distorted anatomy, duplicate subjects, static frame, "
    "watermark, text, logo"
)
FPS = 16
STEPS = 25
# Audio is opt-in. An older bundle, or a notebook that never sets the flag,
# behaves exactly as it does today: silent video, which is what
# PROJECT-PROPOSAL.md still calls the scope.
AUDIO_ENV_VAR = "CRETONA_WORKER_AUDIO"
AUDIO_TIMEOUT_SECONDS = 600
# MMAudio's own defaults are 25 steps at cfg 4.5 with an empty negative prompt.
# The negative prompt is the one worth setting: on quiet ambient clips the model
# tends to invent a music bed or a voice, and either is instantly recognisable
# as wrong for a four-second scene with nobody speaking in it.
# "static" and "hum" were here to suppress noise artefacts and had to go: they
# denote broadband noise, which is acoustically what a waterfall, rain, wind and
# a river all are. Negative-prompting them fought the most common subjects this
# app generates. What EXP-006 actually validated was the music/voice half.
AUDIO_NEGATIVE_PROMPT = "music, soundtrack, speech, voice, narration, singing"
# Tuned on a T4 against EXP-006, 2026-09-03. MMAudio defaults to 25 steps at
# cfg 4.5; both were raised because a 4-second clip finished in 91 s against a
# 300 s budget, so the quality was there to buy. 50 steps costs about 180 s and
# still clears the budget. Both moved in one run, so which one carries the
# improvement is untested -- revisit only if the time ever needs winning back.
AUDIO_STEPS = 50
AUDIO_CFG_STRENGTH = 6.0
# A stream copy of a four-second clip finishes in well under a second; this
# only has to be long enough that a busy Kaggle box is never the reason a
# soundtrack is thrown away.
AUDIO_MUX_TIMEOUT_SECONDS = 120
# MMAudio writes around -25 to -32 LUFS. Streaming and mobile sit between -14
# and -23, so its output is 7-16 dB below anything a phone speaker makes
# audible: measured on four real clips, and the reason the first listener said
# they could barely hear it.
AUDIO_TARGET_LUFS = -16.0
AUDIO_TARGET_PEAK_DBTP = -1.5
AUDIO_TARGET_LRA = 11.0
# Below this the track is closer to silence than to a soundtrack, and lifting
# it to the target would amplify a noise floor rather than a sound. Leave those
# alone: quiet is a better failure than loud hiss.
AUDIO_LOUDNESS_FLOOR_LUFS = -45.0
# A reference still is a phone photo at worst. Anything larger than this is not
# a still, and downloading it onto a Kaggle box is not worth the wait.
REFERENCE_MAX_BYTES = 25 * 1024 * 1024
REFERENCE_TIMEOUT_SECONDS = 120
GUIDANCE_SCALE = 5.0
LEASE_SECONDS = 180
HEARTBEAT_SECONDS = 45
ASPECT_DIMENSIONS = {"16:9": (832, 480), "9:16": (480, 832), "1:1": (640, 640)}

logger = logging.getLogger("cretona.kaggle_worker")


class LeaseLostError(RuntimeError):
    """Another worker owns the project; this process must stop writing."""


class CompletionRefusedError(RuntimeError):
    """The lease is still held, but the database refused to complete the job.

    Since MIG-015 completion also refuses when a canonical object is missing
    from Storage, which is this worker's own failure and must refund, unlike a
    lost lease where another worker owns the outcome.
    """


@dataclass(frozen=True)
class WorkerConfig:
    database_url: str
    supabase_url: str
    publishable_key: str
    worker_email: str
    worker_password: str
    output_dir: Path
    poll_seconds: int = 15

    @classmethod
    def from_env(cls) -> WorkerConfig:
        required = {
            "database_url": "CRETONA_WORKER_DATABASE_URL",
            "supabase_url": "CRETONA_SUPABASE_URL",
            "publishable_key": "CRETONA_SUPABASE_PUBLISHABLE_KEY",
            "worker_email": "CRETONA_WORKER_EMAIL",
            "worker_password": "CRETONA_WORKER_PASSWORD",
        }
        values: dict[str, str] = {}
        missing: list[str] = []
        for field, name in required.items():
            value = os.environ.get(name, "").strip()
            if not value:
                missing.append(name)
            values[field] = value
        if missing:
            raise ValueError(f"Missing Kaggle Secrets: {', '.join(sorted(missing))}")

        database = urllib.parse.urlparse(values["database_url"])
        if database.scheme not in {"postgres", "postgresql"} or not database.hostname:
            raise ValueError("CRETONA_WORKER_DATABASE_URL must be a PostgreSQL URL.")
        project = urllib.parse.urlparse(values["supabase_url"])
        if project.scheme != "https" or not (project.hostname or "").endswith(".supabase.co"):
            raise ValueError("CRETONA_SUPABASE_URL must be the HTTPS project URL.")

        output = Path(os.environ.get("CRETONA_WORKER_OUTPUT_DIR", "/kaggle/working/cretona"))
        return cls(**values, output_dir=output)


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    user_id: UUID
    expires_at: float


@dataclass(frozen=True)
class Job:
    project_id: UUID
    user_id: UUID
    prompt: str
    duration_seconds: int
    aspect_ratio: str
    #: Object name in the private `uploads` bucket, or None for a text-only
    #: job. Shaped `<user_id>/<yyyy-mm-dd>/<uuid>.jpg`, which is deliberately
    #: not the thumbnail shape -- see supabase/016.
    image_path: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Job:
        duration = int(row["duration_seconds"])
        aspect = str(row["aspect_ratio"])
        if duration not in range(2, 6):
            raise ValueError("Kaggle jobs must request between 2 and 5 seconds.")
        if aspect not in ASPECT_DIMENSIONS:
            raise ValueError(f"Unsupported aspect ratio: {aspect}")
        prompt = str(row["prompt"] or "").strip()
        if not prompt:
            raise ValueError("Kaggle jobs require a text prompt.")
        # `image_path` is absent from an older claim function's result, and that
        # must stay a text-only job rather than an error: a worker bundle can be
        # newer than the database it claims from.
        image_path = str(row.get("image_path") or "").strip() or None
        if image_path is not None and not image_path.startswith(f"{row['user_id']}/"):
            # The path is the owner's folder by construction. A row that says
            # otherwise is not something to download on the strength of.
            raise ValueError("Reference image does not belong to the job owner.")
        return cls(
            project_id=UUID(str(row["project_id"])),
            user_id=UUID(str(row["user_id"])),
            prompt=prompt,
            duration_seconds=duration,
            aspect_ratio=aspect,
            image_path=image_path,
        )


class SupabaseWorkerClient:
    def __init__(self, config: WorkerConfig) -> None:
        self.config = config
        self._session: AuthSession | None = None

    def session(self) -> AuthSession:
        if self._session and self._session.expires_at - time.monotonic() > 300:
            return self._session
        url = f"{self.config.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
        body = self._json_request(
            url,
            {"email": self.config.worker_email, "password": self.config.worker_password},
            {"apikey": self.config.publishable_key},
        )
        token = str(body.get("access_token") or "")
        user_id = str((body.get("user") or {}).get("id") or "")
        if not token or not user_id:
            raise RuntimeError("Supabase Auth returned an incomplete worker session.")
        self._session = AuthSession(
            access_token=token,
            user_id=UUID(user_id),
            expires_at=time.monotonic() + int(body.get("expires_in") or 3600),
        )
        return self._session

    def _upload(
        self,
        session: AuthSession,
        bucket: str,
        path: str,
        source: Path,
        content_type: str,
    ) -> None:
        encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
        url = f"{self.config.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{encoded_path}"
        request = urllib.request.Request(
            url,
            data=source.read_bytes(),
            method="POST",
            headers={
                "apikey": self.config.publishable_key,
                "Authorization": f"Bearer {session.access_token}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                if response.status >= 300:
                    raise RuntimeError(f"Storage upload returned HTTP {response.status}.")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Storage upload returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Storage upload could not reach Supabase.") from exc

    def download_reference(self, session: AuthSession, path: str, destination: Path) -> None:
        """Fetch the job's reference still from the private `uploads` bucket.

        Reachable only while this worker holds the project's lease: the read is
        gated by `private.cretona_kaggle_can_read_reference`, which matches the
        object name against `video_projects.image_path` of the leased row
        (supabase/016). An expired lease turns this into an HTTP 400, which is
        the correct answer rather than a surprise.
        """
        encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
        url = f"{self.config.supabase_url.rstrip('/')}/storage/v1/object/uploads/{encoded_path}"
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "apikey": self.config.publishable_key,
                "Authorization": f"Bearer {session.access_token}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REFERENCE_TIMEOUT_SECONDS) as response:
                if response.status >= 300:
                    raise RuntimeError(f"Reference download returned HTTP {response.status}.")
                # Read one byte past the cap so an oversized object is refused
                # rather than streamed onto the box in full.
                payload = response.read(REFERENCE_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Reference download returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Reference download could not reach Supabase.") from exc

        if not payload:
            raise RuntimeError("Reference image is empty.")
        if len(payload) > REFERENCE_MAX_BYTES:
            raise RuntimeError(f"Reference image exceeds {REFERENCE_MAX_BYTES} bytes.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    def upload_video(self, session: AuthSession, path: str, source: Path) -> None:
        self._upload(session, "videos", path, source, "video/mp4")

    def upload_thumbnail(self, session: AuthSession, path: str, source: Path) -> None:
        self._upload(session, "uploads", path, source, "image/jpeg")

    @staticmethod
    def _json_request(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={**headers, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Supabase Auth returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Supabase Auth could not be reached.") from exc


class WorkerDatabase:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def claim(self, owner: UUID) -> Job | None:
        row = self._fetchone(
            "select * from private.cretona_kaggle_claim_job(%s, %s)",
            (owner, LEASE_SECONDS),
        )
        if not row:
            return None
        try:
            return Job.from_row(row)
        except (KeyError, TypeError, ValueError) as exc:
            project_id = UUID(str(row["project_id"]))
            failed = self._fetchone(
                "select private.cretona_kaggle_fail(%s, %s, %s, %s) as ok",
                (owner, project_id, "invalid_input", "Unsupported Kaggle job options."),
            )
            if not failed or not failed["ok"]:
                raise RuntimeError("Could not reject a malformed claimed Kaggle job.") from exc
            logger.error("Rejected malformed project %s", project_id)
            return None

    def heartbeat(self, owner: UUID, job: Job, progress: int, message: str) -> bool:
        row = self._fetchone(
            "select private.cretona_kaggle_heartbeat(%s, %s, %s, %s, %s) as ok",
            (owner, job.project_id, LEASE_SECONDS, progress, message),
        )
        return bool(row and row["ok"])

    def complete(self, owner: UUID, job: Job, sha256: str) -> bool:
        row = self._fetchone(
            "select private.cretona_kaggle_complete(%s, %s, %s) as ok",
            (owner, job.project_id, sha256),
        )
        return bool(row and row["ok"])

    def fail(self, owner: UUID, job: Job, code: str, message: str) -> bool:
        row = self._fetchone(
            "select private.cretona_kaggle_fail(%s, %s, %s, %s) as ok",
            (owner, job.project_id, code, message),
        )
        return bool(row and row["ok"])

    def _fetchone(self, statement: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        with psycopg.connect(
            self.database_url,
            autocommit=True,
            connect_timeout=15,
            sslmode="require",
            row_factory=dict_row,
            application_name="cretona_kaggle_worker",
        ) as connection:
            return connection.execute(statement, parameters).fetchone()


class Progress:
    def __init__(self, value: int = 2, message: str = "Preparing Wan2.1") -> None:
        self._lock = threading.Lock()
        self._value = value
        self._message = message

    def set(self, value: int, message: str) -> None:
        with self._lock:
            self._value = max(1, min(95, value))
            self._message = message[:200]

    def get(self) -> tuple[int, str]:
        with self._lock:
            return self._value, self._message


class LeaseHeartbeat:
    def __init__(self, database: WorkerDatabase, owner: UUID, job: Job, progress: Progress) -> None:
        self.database = database
        self.owner = owner
        self.job = job
        self.progress = progress
        self.stop_event = threading.Event()
        self.lost_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="lease-heartbeat", daemon=True)

    def __enter__(self) -> LeaseHeartbeat:
        value, message = self.progress.get()
        if not self.database.heartbeat(self.owner, self.job, value, message):
            raise LeaseLostError("The project lease was lost before generation started.")
        self.thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)

    def assert_owned(self) -> None:
        if self.lost_event.is_set():
            raise LeaseLostError("The project lease is no longer owned by this worker.")

    def _run(self) -> None:
        failures = 0
        while not self.stop_event.wait(HEARTBEAT_SECONDS):
            value, message = self.progress.get()
            try:
                if not self.database.heartbeat(self.owner, self.job, value, message):
                    self.lost_event.set()
                    return
                failures = 0
            except psycopg.Error:
                failures += 1
                logger.warning(
                    "Heartbeat failed for project %s (%d/3)", self.job.project_id, failures
                )
                if failures >= 3:
                    self.lost_event.set()
                    return


def frame_count(duration_seconds: int) -> int:
    if duration_seconds not in range(2, 6):
        raise ValueError("duration_seconds must be between 2 and 5")
    return duration_seconds * FPS + 1  # Wan requires 4n+1 frames.


def dimensions(aspect_ratio: str) -> tuple[int, int]:
    try:
        return ASPECT_DIMENSIONS[aspect_ratio]
    except KeyError as exc:
        raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}") from exc


def storage_path(job: Job) -> str:
    return f"{job.user_id}/{job.project_id}/video.mp4"


def thumbnail_path(job: Job) -> str:
    return f"{job.user_id}/{job.project_id}/thumbnail.jpg"


def _free_accelerator() -> None:
    gc.collect()
    try:
        import torch

        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    except Exception:
        pass


def _embedding_cache(job: Job, cache_dir: Path) -> Path:
    material = f"worker-v1|{MODEL_REPO}|{MODEL_REVISION}|{NEGATIVE_PROMPT}|{job.prompt}"
    digest = hashlib.sha256(material.encode()).hexdigest()[:20]
    return cache_dir / f"embeds-{digest}.pt"


def _encode_prompt(job: Job, cache_dir: Path, progress: Progress) -> tuple[Any, Any]:
    import torch
    from diffusers import WanPipeline

    cache = _embedding_cache(job, cache_dir)
    if cache.is_file():
        positive, negative = torch.load(cache, map_location="cpu", weights_only=True)
        if torch.isfinite(positive).all() and torch.isfinite(negative).all():
            progress.set(12, "Loaded cached prompt embeddings")
            return positive, negative
        cache.unlink(missing_ok=True)

    progress.set(4, "Loading Wan2.1 text encoder on CPU")
    pipe = None
    try:
        _free_accelerator()
        pipe = WanPipeline.from_pretrained(
            MODEL_REPO,
            revision=MODEL_REVISION,
            transformer=None,
            torch_dtype=torch.bfloat16,
        )
        encoder = pipe.text_encoder
        if (
            encoder is not None
            and hasattr(encoder, "shared")
            and hasattr(encoder, "encoder")
            and encoder.encoder.embed_tokens.weight.data_ptr() != encoder.shared.weight.data_ptr()
        ):
            encoder.encoder.embed_tokens.weight = encoder.shared.weight

        probe_a, _ = pipe.encode_prompt(
            prompt="a red cube on a table",
            negative_prompt="",
            do_classifier_free_guidance=True,
            device=torch.device("cpu"),
            dtype=torch.bfloat16,
        )
        probe_b, _ = pipe.encode_prompt(
            prompt="an astronaut riding a horse on mars",
            negative_prompt="",
            do_classifier_free_guidance=True,
            device=torch.device("cpu"),
            dtype=torch.bfloat16,
        )
        a, b = probe_a.float()[0], probe_b.float()[0]
        live = (a.abs().sum(-1) > 1e-6) | (b.abs().sum(-1) > 1e-6)
        cosine = torch.nn.functional.cosine_similarity(
            a[live].flatten(), b[live].flatten(), dim=0
        ).item()
        if not int(live.sum()) or cosine > 0.999:
            raise RuntimeError("Wan2.1 text encoder self-test failed.")

        progress.set(8, "Encoding project prompt")
        positive, negative = pipe.encode_prompt(
            prompt=job.prompt,
            negative_prompt=NEGATIVE_PROMPT,
            do_classifier_free_guidance=True,
            device=torch.device("cpu"),
            dtype=torch.bfloat16,
        )
        result = positive.to("cpu", torch.float16), negative.to("cpu", torch.float16)
        torch.save(result, cache)
        return result
    finally:
        del pipe
        _free_accelerator()


def generate_video(
    job: Job,
    output: Path,
    progress: Progress,
    assert_owned: Callable[[], None],
) -> None:
    import torch
    from diffusers import AutoModel, WanPipeline
    from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
    from diffusers.utils import export_to_video

    output.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = output.parent / "embeddings"
    cache_dir.mkdir(exist_ok=True)
    positive, negative = _encode_prompt(job, cache_dir, progress)
    assert_owned()

    width, height = dimensions(job.aspect_ratio)
    progress.set(14, "Loading Wan2.1 generator on GPU")
    pipe = None
    vae = None
    frames = None
    try:
        vae = AutoModel.from_pretrained(
            MODEL_REPO,
            subfolder="vae",
            revision=MODEL_REVISION,
            torch_dtype=torch.float32,
        )
        pipe = WanPipeline.from_pretrained(
            MODEL_REPO,
            revision=MODEL_REVISION,
            vae=vae,
            text_encoder=None,
            tokenizer=None,
            torch_dtype=torch.float16,
        )
        pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=5.0)
        pipe.to("cuda")
        generator = torch.Generator(device="cuda").manual_seed(job.project_id.int % (2**31))

        def on_step_end(_pipe: Any, step: int, _timestep: Any, kwargs: dict[str, Any]):
            assert_owned()
            percent = 15 + int(((step + 1) / STEPS) * 75)
            progress.set(percent, f"Wan2.1 denoising step {step + 1}/{STEPS}")
            return kwargs

        frames = pipe(
            prompt_embeds=positive.to("cuda"),
            negative_prompt_embeds=negative.to("cuda"),
            width=width,
            height=height,
            num_frames=frame_count(job.duration_seconds),
            num_inference_steps=STEPS,
            guidance_scale=GUIDANCE_SCALE,
            generator=generator,
            callback_on_step_end=on_step_end,
        ).frames[0]
        assert_owned()
        progress.set(92, "Encoding MP4")
        export_to_video(frames, str(output), fps=FPS)
        if not output.is_file() or output.stat().st_size <= 1024:
            raise RuntimeError("Wan2.1 produced no usable MP4.")
    finally:
        del frames, pipe, vae, positive, negative
        _free_accelerator()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


#: Visual-only clauses `compose_enhanced_prompt` appends for Wan2.1. They steer
#: a picture, not a soundtrack, and "Studio Ghibli style lighting" pushes an
#: audio model toward the music bed the negative prompt is trying to suppress.
_VISUAL_ONLY_MARKERS = (
    "camera ",
    "in vibrant anime",
    "in cyberpunk",
    "in 3d animation",
    "in vintage 35mm",
    "in 8k hyperrealistic",
    "cinematic 16:9",
    "octane render",
    "depth of field",
    "lens blur",
    "color grading",
    "lighting",
    "aesthetic",
    "hand-drawn",
    "detailed textures",
    "imax",
    "grain",
    "subsurface scattering",
    "character rendering",
    "hyperrealistic",
    # Boilerplate the prompt enhancer appends to every job. None of it
    # describes a sound, and leaving it in was worse than useless: it was the
    # only thing MMAudio received once the subject had been filtered away.
    "subject motion",
    "coherent environment",
    "consistent details",
    "visual quality",
    "no text",
    "watermark",
)

#: `PromptService` emits "Cinematic <ratio> video of <subject>. <boilerplate>".
#: The subject is the one part a soundtrack can act on, and it is glued to a
#: visual marker, so it has to be lifted out before any clause filtering.
_TEMPLATE_PREFIX = re.compile(r"^\s*cinematic\s+\S+\s+video\s+of\s+", re.IGNORECASE)
#: Setting words are kept on purpose even when they arrive inside a style
#: directive: "futuristic cityscape" tells a soundtrack more than it costs.


def audio_prompt(video_prompt: str) -> str:
    """Reduce a Wan2.1 prompt to the part a soundtrack can act on.

    The prompt the job carries was written for a video model and had style and
    camera directives appended to it. Handing that to MMAudio asks it to
    sonify instructions about framing and grain. Dropping those clauses leaves
    the subject and setting, which is what a listener would expect to hear.

    The subject is extracted before anything is filtered. Splitting on commas
    alone destroyed it: the enhancer writes "Cinematic 16:9 video of Waterfall.
    Clear subject motion" as one comma-clause, so a filter that drops any clause
    containing "cinematic 16:9" drops the word "Waterfall" with it. Two real
    jobs shipped with MMAudio conditioned on nothing but "coherent environment,
    consistent details, high visual quality, no text or watermark", which is why
    their soundtracks had no relationship to the picture.

    Falls back to the original when filtering would leave nothing: a
    scene-shaped prompt beats an empty one.
    """
    text = video_prompt.strip()
    if not text:
        return text

    # An enhanced prompt has its subject in the first sentence; a raw one has no
    # sentence break and is filtered clause by clause as before.
    head, separator, tail = text.partition(".")
    subject = _TEMPLATE_PREFIX.sub("", head).strip() if separator else ""
    remainder = tail if separator else text

    kept = [
        clause
        for clause in (clause.strip() for clause in remainder.split(","))
        if clause and not any(marker in clause.lower() for marker in _VISUAL_ONLY_MARKERS)
    ]
    parts = ([subject] if subject else []) + kept
    return ", ".join(parts) if parts else text


def audio_enabled() -> bool:
    return os.environ.get(AUDIO_ENV_VAR, "").strip().lower() in {"1", "true", "yes"}


def _ffmpeg_executable() -> str | None:
    """Find an ffmpeg binary without adding a dependency.

    `imageio-ffmpeg` is already pinned in `requirements-kaggle.txt` because
    `export_to_video` needs it, and it ships its own binary, so muxing costs
    nothing new. `shutil.which` covers a host that has ffmpeg on PATH instead.
    """
    import shutil

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _measure_loudness(source: Path) -> dict[str, str] | None:
    """Run `loudnorm`'s analysis pass and return what it found.

    Two passes beat one here. Single-pass `loudnorm` guesses as it goes and
    pumps on a four-second clip; measuring first lets the second pass apply a
    known, linear gain. Both passes are sub-second on a clip this short.

    Returns None whenever the answer cannot be trusted, so the caller falls
    back to copying the stream untouched.
    """
    import json
    import subprocess

    ffmpeg = _ffmpeg_executable()
    if ffmpeg is None:
        return None
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-i",
                str(source),
                "-filter:a",
                f"loudnorm=I={AUDIO_TARGET_LUFS}:TP={AUDIO_TARGET_PEAK_DBTP}"
                f":LRA={AUDIO_TARGET_LRA}:print_format=json",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=AUDIO_MUX_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Loudness measurement skipped: %s", type(exc).__name__)
        return None
    if completed.returncode != 0:
        logger.warning("Loudness measurement skipped: ffmpeg exited %s", completed.returncode)
        return None

    text = completed.stderr or ""
    start, end = text.rfind("{"), text.rfind("}")
    if start < 0 or end < start:
        logger.warning("Loudness measurement skipped: no JSON in ffmpeg output")
        return None
    try:
        measured = json.loads(text[start : end + 1])
        source_lufs = float(measured["input_i"])
    except (ValueError, KeyError, TypeError):
        logger.warning("Loudness measurement skipped: unreadable ffmpeg output")
        return None

    if source_lufs < AUDIO_LOUDNESS_FLOOR_LUFS:
        logger.info(
            "Loudness normalisation skipped: source is %.1f LUFS, below the %.1f floor",
            source_lufs,
            AUDIO_LOUDNESS_FLOOR_LUFS,
        )
        return None
    return measured


def loudnorm_filter(measured: dict[str, str]) -> str:
    """Second-pass `loudnorm` arguments built from the first pass's numbers."""
    return (
        f"loudnorm=I={AUDIO_TARGET_LUFS}:TP={AUDIO_TARGET_PEAK_DBTP}:LRA={AUDIO_TARGET_LRA}"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true"
    )


def mux_audio(
    silent: Path,
    composited: Path,
    destination: Path,
    audio_filter: str | None = None,
) -> bool:
    """Put `silent`'s picture and `composited`'s soundtrack in one container.

    Both streams are **copied**, never re-encoded, so this is a repackaging
    step rather than a conversion. Returns whether `destination` is now a
    usable clip; on any failure it removes the partial file and reports False,
    leaving the caller free to keep what MMAudio produced.

    `+faststart` moves the index to the front of the file. Playback happens
    over a signed URL through a tunnel, where a player that has to fetch the
    tail before it can start is a visible delay.
    """
    import subprocess

    ffmpeg = _ffmpeg_executable()
    if ffmpeg is None:
        logger.warning("Mux skipped: no ffmpeg binary is available")
        return False

    destination.unlink(missing_ok=True)
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-y",
                "-i",
                str(silent),
                "-i",
                str(composited),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                *(
                    ["-filter:a", audio_filter, "-c:a", "aac", "-b:a", "128k"]
                    if audio_filter
                    else ["-c:a", "copy"]
                ),
                # No `-shortest`. MMAudio returns 4.040 s of sound for a
                # 4.0625 s clip, and `-shortest` answered that mismatch by
                # dropping four frames -- 65 became 61, measured. The picture
                # is the graded artefact and the soundtrack sits on top of it,
                # so a slightly short track is the right thing to tolerate.
                "-movflags",
                "+faststart",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=AUDIO_MUX_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Mux skipped: %s", type(exc).__name__)
        destination.unlink(missing_ok=True)
        return False

    if completed.returncode != 0:
        # `-map 1:a:0` fails loudly when MMAudio produced no audio stream,
        # which is the case worth distinguishing from a broken binary.
        logger.warning(
            "Mux skipped: ffmpeg exited %s: %s",
            completed.returncode,
            (completed.stderr or "").strip()[-300:],
        )
        destination.unlink(missing_ok=True)
        return False

    if not destination.is_file() or destination.stat().st_size <= 1024:
        logger.warning("Mux skipped: ffmpeg wrote no usable file")
        destination.unlink(missing_ok=True)
        return False

    return True


def add_audio(video: Path, prompt: str, duration_seconds: int) -> bool:
    """Generate a soundtrack for `video` and replace it in place. Best effort.

    Returns whether the video now has audio. **Never raises**: audio is an
    enhancement on top of the one thing this project is graded on, so a model
    that will not load must leave a silent, complete, uploadable clip behind.
    That is the opposite of the thumbnail rule in migration 015, and
    deliberately so — a missing preview is a defect, a missing soundtrack is
    the documented non-scope behaviour.

    MMAudio checkpoints are CC-BY-NC 4.0: coursework yes, commercial use no.
    """
    import shutil
    import subprocess

    repo = Path(os.environ.get("CRETONA_MMAUDIO_DIR", "/kaggle/working/MMAudio"))
    demo = repo / "demo.py"
    if not demo.is_file():
        logger.warning("Audio skipped: MMAudio is not installed at %s", repo)
        return False

    # Wan2.1 peaks near 12.5 GiB and MMAudio wants about 6; they do not fit on
    # one T4 together, so the transformer has to be gone before this runs.
    _free_accelerator()

    output_dir = repo / "output"
    before = {p for p in output_dir.rglob("*.mp4")} if output_dir.is_dir() else set()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(demo),
                f"--duration={duration_seconds}",
                f"--video={video}",
                f"--prompt={audio_prompt(prompt)}",
                f"--negative_prompt={AUDIO_NEGATIVE_PROMPT}",
                f"--num_steps={AUDIO_STEPS}",
                f"--cfg_strength={AUDIO_CFG_STRENGTH}",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=AUDIO_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Audio skipped: MMAudio exceeded %ss", AUDIO_TIMEOUT_SECONDS)
        return False
    except Exception as exc:
        logger.warning("Audio skipped: %s", type(exc).__name__)
        return False
    finally:
        _free_accelerator()

    if completed.returncode != 0:
        # stderr can carry file paths but not secrets; the tail is enough to
        # tell a missing weight from an out-of-memory kill.
        logger.warning(
            "Audio skipped: MMAudio exited %s: %s",
            completed.returncode,
            (completed.stderr or "").strip()[-300:],
        )
        return False

    produced = [p for p in output_dir.rglob("*.mp4") if p not in before]
    if not produced:
        logger.warning("Audio skipped: MMAudio wrote no video")
        return False

    newest = max(produced, key=lambda p: p.stat().st_mtime)
    if newest.stat().st_size <= 1024:
        logger.warning("Audio skipped: MMAudio output was empty")
        return False

    # MMAudio re-encodes the picture when it composites, at roughly seven times
    # the bitrate Wan2.1 wrote: a 405,459 B clip came back between 2.9 and
    # 5.1 MB, of which the soundtrack was about 64 KB. A second encode cannot
    # restore detail the first one discarded, so copying both streams into a
    # fresh container keeps the sound, keeps the original picture, and drops
    # the file by roughly an order of magnitude. Measurements:
    # docs/evidence/EXP006_FIRST_AUDIO_JOBS_2026-09-03.md.
    #
    # Replace only once the replacement is known good, so a truncated write
    # cannot cost the clip that already generated successfully.
    #
    # The soundtrack is also normalised on the way through. Re-encoding 64 KB of
    # AAC costs nothing next to the picture it travels with, and MMAudio's own
    # level is far too low to hear on a phone.
    composited_bytes = newest.stat().st_size
    muxed = video.with_name(video.name + ".mux.mp4")
    measured = _measure_loudness(newest)
    normalised = measured is not None and mux_audio(
        video, newest, muxed, audio_filter=loudnorm_filter(measured)
    )
    # Normalising is an enhancement on an enhancement. If it fails, mux the
    # stream untouched rather than lose the soundtrack over its volume.
    if normalised or mux_audio(video, newest, muxed):
        muxed_bytes = muxed.stat().st_size
        muxed.replace(video)
        logger.info(
            "Audio muxed %s: %s B rather than MMAudio's %s B",
            "and normalised" if normalised else "without normalisation",
            muxed_bytes,
            composited_bytes,
        )
    else:
        # A larger clip that plays beats a smaller one that is silent, so a
        # failed mux falls back to what MMAudio produced rather than dropping
        # the soundtrack that just cost three minutes of GPU time.
        logger.warning("Mux unavailable; keeping MMAudio's re-encoded clip")
        shutil.copyfile(newest, video)
    newest.unlink(missing_ok=True)
    return True


def create_thumbnail(video: Path, thumbnail: Path) -> None:
    import imageio.v2 as imageio

    reader = imageio.get_reader(video)
    try:
        frame = reader.get_data(0)
    finally:
        reader.close()
    imageio.imwrite(thumbnail, frame, format="jpg", quality=85)
    if not thumbnail.is_file() or thumbnail.stat().st_size <= 512:
        raise RuntimeError("Wan2.1 produced no usable thumbnail.")


def run_once(
    config: WorkerConfig,
    database: WorkerDatabase,
    supabase: SupabaseWorkerClient,
    generator: Callable[[Job, Path, Progress, Callable[[], None]], None] = generate_video,
    thumbnailer: Callable[[Path, Path], None] = create_thumbnail,
    audio_generator: Callable[[Path, str, int], bool] = add_audio,
) -> bool:
    session = supabase.session()
    job = database.claim(session.user_id)
    if job is None:
        return False

    logger.info("Claimed project %s", job.project_id)
    output = config.output_dir / f"{job.project_id}.mp4"
    thumbnail = config.output_dir / f"{job.project_id}.jpg"
    progress = Progress()
    try:
        with LeaseHeartbeat(database, session.user_id, job, progress) as heartbeat:
            generator(job, output, progress, heartbeat.assert_owned)
            heartbeat.assert_owned()

            # Between generation and the thumbnail: the clip already exists, so
            # a failure here costs nothing, and the thumbnail is taken from
            # whichever version of the file survives.
            if audio_enabled():
                progress.set(92, "Adding audio")
                # `add_audio` already swallows its own failures, so this guard
                # is for the case it does not: by now the job is worth twenty
                # minutes of GPU time, and letting anything from the soundtrack
                # escape would fail a video that generated correctly and refund
                # a user who is about to receive it.
                try:
                    audio_generator(output, job.prompt, job.duration_seconds)
                except LeaseLostError:
                    raise
                except Exception:
                    logger.exception("Audio step failed; continuing with a silent video")
                heartbeat.assert_owned()

            progress.set(93, "Creating video thumbnail")
            thumbnailer(output, thumbnail)
            progress.set(94, "Uploading video and thumbnail to Supabase Storage")

            last_error: Exception | None = None
            for delay in (0, 2, 5):
                if delay:
                    time.sleep(delay)
                try:
                    fresh_session = supabase.session()
                    if fresh_session.user_id != session.user_id:
                        raise RuntimeError("Worker Auth identity changed during the job.")
                    supabase.upload_video(fresh_session, storage_path(job), output)
                    supabase.upload_thumbnail(
                        fresh_session,
                        thumbnail_path(job),
                        thumbnail,
                    )
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error

            heartbeat.assert_owned()
            if not database.complete(session.user_id, job, sha256_file(output)):
                # A false return meant one thing before MIG-015: the lease had
                # moved. Completion now also refuses when the MP4 or the JPEG
                # is missing from Storage, and the two must not be treated
                # alike — a lost lease belongs to another worker and must not
                # refund, while a missing object is this worker's failure and
                # must. A successful heartbeat still proves ownership here,
                # because completion left the row in `generating`.
                value, _ = progress.get()
                if database.heartbeat(session.user_id, job, min(max(value, 1), 95), "Verifying"):
                    raise CompletionRefusedError(
                        "Completion refused while this worker still held the lease; "
                        "the MP4 or thumbnail is missing from Storage."
                    )
                raise LeaseLostError("Completion refused because the lease changed.")
        logger.info("Completed project %s", job.project_id)
    except LeaseLostError:
        logger.warning("Stopped project %s after losing its lease", job.project_id)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        logger.exception("Project %s failed with %s", job.project_id, type(exc).__name__)
        try:
            failed = database.fail(
                session.user_id,
                job,
                "provider_error",
                "Video generation failed on the Kaggle worker.",
            )
            if not failed:
                logger.warning("Failure update was refused for project %s", job.project_id)
        except psycopg.Error:
            logger.exception("Could not persist failure for project %s", job.project_id)
    finally:
        output.unlink(missing_ok=True)
        thumbnail.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = WorkerConfig.from_env()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    database = WorkerDatabase(config.database_url)
    supabase = SupabaseWorkerClient(config)

    while True:
        processed = run_once(config, database, supabase)
        if args.once:
            return 0
        if not processed:
            time.sleep(config.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
