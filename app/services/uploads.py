import io
import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import Settings
from app.errors import Problem


@dataclass(frozen=True)
class InspectedUpload:
    mime: str
    pages: int
    working_image: bytes | None = None


def inspect_upload(stream: BinaryIO, filename: str | None, settings: Settings) -> InspectedUpload:
    logging.getLogger("pypdf").disabled = True
    stream.seek(0)
    magic = stream.read(8)
    stream.seek(0)
    mime = (
        "application/pdf"
        if magic.startswith(b"%PDF-")
        else "image/png"
        if magic.startswith(b"\x89PNG\r\n\x1a\n")
        else "image/jpeg"
        if magic.startswith(b"\xff\xd8\xff")
        else None
    )
    if mime is None:
        raise Problem(415, "unsupported_type", "Upload a PDF, JPEG or PNG chapter.")
    suffix = Path(filename or "").suffix.lower()
    expected = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    if suffix and expected.get(suffix) != mime:
        raise Problem(
            415,
            "unsupported_type",
            "The filename and file contents disagree. Upload the original file with the correct extension.",
        )
    if mime == "application/pdf":
        try:
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted:
                raise Problem(
                    422,
                    "password_protected",
                    "This PDF has a password. Please upload an unlocked copy.",
                )
            pages = len(reader.pages)
            if pages < 1:
                raise Problem(422, "malformed", "This PDF has no pages. Upload a valid chapter.")
            if pages > settings.max_pages:
                raise Problem(
                    413,
                    "too_many_pages",
                    "This chapter has too many pages. Split it into smaller chapters.",
                )
        except (PdfReadError, ValueError, OSError, KeyError, TypeError):
            raise Problem(
                422, "malformed", "This PDF could not be read. Export a valid copy and retry."
            ) from None
        finally:
            stream.seek(0)
        return InspectedUpload(mime, pages)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                if image.width * image.height > settings.max_pixels:
                    raise Problem(
                        413,
                        "too_many_pixels",
                        "This image is too large. Reduce its dimensions before uploading.",
                    )
                image.verify()
            stream.seek(0)
            with Image.open(stream) as original:
                clean = ImageOps.exif_transpose(original).convert("RGB")
                clean.info.clear()
                output = io.BytesIO()
                clean.save(output, format="PNG")
                return InspectedUpload(mime, 1, output.getvalue())
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise Problem(
            413,
            "too_many_pixels",
            "This image has too many pixels. Reduce its dimensions before uploading.",
        ) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise Problem(
            422, "malformed", "This image could not be read. Export a valid JPEG or PNG and retry."
        ) from None
    finally:
        stream.seek(0)
