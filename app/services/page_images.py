import io
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import BoundedSemaphore

from PIL import Image

from app.config import Settings
from app.errors import Problem

_PDF_SLOTS = BoundedSemaphore(2)
_MAX_PNG_BYTES = 12 * 1024 * 1024


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        left, top, right, bottom = map(float, value.split(","))
        if 0 <= left < right <= 1 and 0 <= top < bottom <= 1:
            return left, top, right, bottom
    except ValueError:
        pass
    raise Problem(
        422, "invalid_preview_bbox", "Enter four ordered crop coordinates between zero and one."
    )


def _pdf_bytes(path: Path, index: int, settings: Settings) -> bytes:
    command = [
        sys.executable,
        "-m",
        "app.adapters.pdf_preview",
        str(path),
        str(index),
        str(settings.preview_max_side),
    ]
    if settings.pathya_env == "prod":
        unshare = shutil.which("unshare") if sys.platform == "linux" and os.getuid() != 0 else None
        if unshare is None:
            raise Problem(
                503,
                "pdf_preview_unavailable",
                "Open the original PDF page. The image renderer is unavailable.",
            )
        command = [
            unshare,
            "--user",
            "--map-root-user",
            "--net",
            "--",
            sys.executable,
            "-m",
            "app.adapters.sandbox",
            str(math.ceil(settings.preview_render_timeout)),
            str(_MAX_PNG_BYTES),
            "--",
            *command,
        ]
    if not _PDF_SLOTS.acquire(blocking=False):
        raise Problem(
            503,
            "pdf_preview_busy",
            "The image renderer is busy. Try again or open the original PDF page.",
        )
    environment = {
        key: val
        for key, val in os.environ.items()
        if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    try:
        with tempfile.TemporaryFile() as output:
            subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                env=environment,
                timeout=settings.preview_render_timeout,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            output.seek(0)
            data = output.read(_MAX_PNG_BYTES + 1)
            if len(data) > _MAX_PNG_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise OSError("Invalid preview.")
            return data
    except (OSError, subprocess.SubprocessError):
        raise Problem(
            503,
            "pdf_preview_unavailable",
            "Open the original PDF page. The image could not be rendered.",
        ) from None
    finally:
        _PDF_SLOTS.release()


def render_page(
    path: Path,
    mime: str,
    index: int,
    bbox: tuple[float, float, float, float] | None,
    settings: Settings,
) -> bytes:
    source: Path | io.BytesIO = path
    if mime == "application/pdf":
        if not settings.pdf_preview_enabled:
            raise Problem(
                503,
                "pdf_preview_unavailable",
                "Open the original PDF page. Page images are unavailable.",
            )
        data = _pdf_bytes(path, index, settings)
        if bbox is None:
            return data
        source = io.BytesIO(data)
    try:
        with Image.open(source) as opened:
            image: Image.Image = opened
            pixel_limit = (
                settings.preview_max_side**2 if mime == "application/pdf" else settings.max_pixels
            )
            if image.width * image.height > pixel_limit:
                raise OSError("Image too large.")
            if bbox is not None:
                left, top, right, bottom = bbox
                image = image.crop(
                    (
                        math.floor(left * image.width),
                        math.floor(top * image.height),
                        math.ceil(right * image.width),
                        math.ceil(bottom * image.height),
                    )
                )
            image.thumbnail((settings.preview_max_side, settings.preview_max_side))
            image.info.clear()
            output = io.BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise Problem(
            404,
            "page_image_unavailable",
            "This source image is unavailable. Open the source page or read the text.",
        ) from None
