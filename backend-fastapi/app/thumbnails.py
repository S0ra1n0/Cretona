from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("cretona.thumbnails")

TIMEOUT_SECONDS = 20


class ThumbnailGenerator:
    """Extracts a still from a finished video using ffmpeg.

    ffmpeg is an external binary, not a Python dependency, so it may simply not
    be installed. A missing thumbnail is a cosmetic loss and `thumbnailUrl` is
    nullable by contract, so absence degrades to None rather than failing a
    generation that otherwise succeeded.
    """

    def __init__(self, *, ffmpeg_path: str, enabled: bool, seek_seconds: float) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.enabled = enabled
        self.seek_seconds = seek_seconds

    def available(self) -> bool:
        return self.enabled and shutil.which(self.ffmpeg_path) is not None

    def build_command(self, source: Path, target: Path) -> list[str]:
        return [
            self.ffmpeg_path,
            "-nostdin",
            "-y",
            # Seeking before -i is the fast path; it decodes from the nearest
            # keyframe rather than walking the file.
            "-ss",
            str(self.seek_seconds),
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(target),
        ]

    def extract(self, source: Path, target: Path) -> bool:
        if not self.available():
            return False

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            # An argv list, never a shell string, so a crafted path cannot
            # become a command.
            result = subprocess.run(
                self.build_command(source, target),
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            logger.warning("thumbnail_failed", extra={"source": str(source)})
            return False

        # A zero exit with no file is still a failure: a shorter-than-seek
        # video produces no frame.
        if result.returncode != 0 or not target.exists():
            logger.warning(
                "thumbnail_failed",
                extra={"source": str(source), "exitCode": result.returncode},
            )
            return False
        return True
