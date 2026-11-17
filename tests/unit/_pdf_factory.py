"""Synthetic PDF builder for tests. Writes minimal, valid PDF 1.4 files by hand.

No copyrighted content and no third-party PDF writer: each page is described by
text runs (Helvetica, WinAnsi-safe ASCII) and optional opaque grey images.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import zlib


@dataclass
class Text:
    x: float  # PDF user-space baseline origin (points, bottom-left origin)
    y: float
    text: str
    size: float = 12.0
    angle: int = 0  # counter-clockwise text rotation in user space (0, 90, 180, 270)
    bold: bool = False


@dataclass
class Image:
    x: float
    y: float
    width: float
    height: float
    gray: tuple[int, int, bytes] | None = None  # (width_px, height_px, 8-bit pixels); default 2x2 grey


@dataclass
class PageSpec:
    width: float = 612.0
    height: float = 792.0
    texts: list[Text] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    rotate: int | None = None
    crop_box: tuple[float, float, float, float] | None = None
    raw_content: bytes | None = None  # overrides texts/images content stream
    extra: str = ""  # additional content-stream operators drawn after images, before text


_MATRIX = {0: "1 0 0 1", 90: "0 1 -1 0", 180: "-1 0 0 -1", 270: "0 -1 1 0"}


def upright_text(rotation: int, x: float, y: float, text: str, size: float = 12.0) -> Text:
    """Text drawn counter-rotated so it reads upright on a page with /Rotate ``rotation``."""
    return Text(x, y, text, size, angle=rotation % 360)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(
    pages: list[PageSpec],
    *,
    page_labels: str | None = None,
    encrypt: bool = False,
) -> bytes:
    objects: list[bytes] = []  # object n is objects[n-1]

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # placeholder, filled later
    pages_obj = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    pixels = zlib.compress(bytes([90, 160, 200, 40]))
    image = add(b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray "
                b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % len(pixels)
                + pixels + b"\nendstream")

    kids: list[int] = []
    for spec in pages:
        xobjects = {"Im1": image}
        if spec.raw_content is not None:
            content = spec.raw_content
        else:
            parts = []
            for n, i in enumerate(spec.images):
                name = "Im1"
                if i.gray is not None:
                    w, h, data = i.gray
                    packed = zlib.compress(data)
                    name = f"Img{n}"
                    xobjects[name] = add(
                        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
                        b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (w, h, len(packed))
                        + packed + b"\nendstream")
                parts.append(f"q {i.width} 0 0 {i.height} {i.x} {i.y} cm /{name} Do Q")
            if spec.extra:
                parts.append(spec.extra)
            parts += [f"BT /{'F2' if t.bold else 'F1'} {t.size} Tf {_MATRIX[t.angle]} {t.x} {t.y} Tm "
                      f"({_esc(t.text)}) Tj ET" for t in spec.texts]
            content = "\n".join(parts).encode("latin-1")
        stream = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        extra = ""
        if spec.rotate is not None:
            extra += f" /Rotate {spec.rotate}"
        if spec.crop_box is not None:
            extra += " /CropBox [%s]" % " ".join(str(v) for v in spec.crop_box)
        page = add((
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {spec.width} {spec.height}]{extra}"
            f" /Resources << /Font << /F1 {font} 0 R /F2 {bold} 0 R >> /XObject << "
            + " ".join(f"/{k} {v} 0 R" for k, v in xobjects.items()) + " >> >>"
            f""
            f" /Contents {stream} 0 R >>").encode())
        kids.append(page)

    labels = f" /PageLabels {page_labels}" if page_labels else ""
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R{labels} >>".encode()
    objects[pages_obj - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>").encode()

    encrypt_ref = ""
    if encrypt:
        # Standard security handler with a non-empty (unknown) user password:
        # readers cannot open it without the password.
        enc = add(b"<< /Filter /Standard /V 1 /R 2 /O <" + b"11" * 32 + b"> /U <" + b"22" * 32
                  + b"> /P -44 >>")
        encrypt_ref = f" /Encrypt {enc} 0 R /ID [<{'ab' * 16}> <{'ab' * 16}>]"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R{encrypt_ref} >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def write_pdf(path: Path, pages: list[PageSpec], **kwargs: object) -> Path:
    path.write_bytes(build_pdf(pages, **kwargs))  # type: ignore[arg-type]
    return path
