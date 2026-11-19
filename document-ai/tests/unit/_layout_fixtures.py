"""Synthetic textbook-like pages for layout tests (original text, no textbook content)."""

from __future__ import annotations

from pathlib import Path
import textwrap

from _pdf_factory import Image, PageSpec, Text, write_pdf

LEFT, RIGHT, TOP = 72.0, 540.0, 740.0
BODY = 11.0
LEADING = 14.5

PARA_A = ("Motion is the change in position of an object over time. When a bicycle moves along a "
          "straight road, its position changes with respect to a fixed point on the roadside. Scientists "
          "describe motion using distance, displacement, speed and velocity.")
PARA_B = ("Speed tells us how fast an object moves, while velocity also tells us the direction of motion. "
          "Two cyclists may have the same speed but different velocities if they ride in opposite "
          "directions along the same road.")
PARA_C = ("Acceleration measures how quickly velocity changes. A car that starts from rest and reaches a "
          "steady speed has accelerated during that interval of time.")


def _paragraph(text: str, x: float, y: float, width_chars: int, size: float = BODY) -> tuple[list[Text], float]:
    lines = textwrap.wrap(text, width_chars)
    texts = [Text(x, y - i * LEADING, line, size) for i, line in enumerate(lines)]
    return texts, y - len(lines) * LEADING - 10


def single_column_page() -> PageSpec:
    texts = [Text(LEFT, TOP, "Chapter 4 Motion", 20, bold=True)]
    y = TOP - 36
    texts.append(Text(LEFT, y, "4.1 Describing Motion", 14, bold=True))
    y -= 24
    for para in (PARA_A, PARA_B):
        chunk, y = _paragraph(para, LEFT, y, 92)
        texts += chunk
    texts.append(Text(LEFT, y - 6, "Key ideas", 13, bold=True))
    y -= 30
    for n, item in enumerate(["Distance is the length of the path travelled.",
                              "Displacement is the shortest distance between two points.",
                              "Speed is distance travelled per unit time."], start=1):
        texts.append(Text(LEFT + 14, y, f"{n}. {item}", BODY))
        y -= LEADING + 4
    chunk, _ = _paragraph(PARA_C, LEFT, y - 10, 92)
    return PageSpec(texts=texts + chunk)


def two_column_page() -> PageSpec:
    texts = [Text(LEFT, TOP, "4.2 Speed and Velocity", 18, bold=True)]
    gutter_left, gutter_right = 296.0, 316.0
    left_y = right_y = TOP - 40
    for para in (PARA_A, PARA_B, PARA_C):
        chunk, left_y = _paragraph(para, LEFT, left_y, 44)
        texts += chunk
    for para in (PARA_C, PARA_A, PARA_B):
        chunk, right_y = _paragraph(para.replace("Motion", "Movement"), gutter_right, right_y, 44)
        texts += chunk
    assert gutter_left < gutter_right
    return PageSpec(texts=texts)


def table_page() -> PageSpec:
    texts = [Text(LEFT, TOP, "4.3 Units of Measurement", 16, bold=True)]
    rows = [("Quantity", "SI unit", "Symbol"), ("Distance", "metre", "m"),
            ("Time", "second", "s"), ("Speed", "metre per second", "m/s")]
    x_edges = [100.0, 240.0, 420.0, 520.0]
    top, row_h = 640.0, 26.0
    ops = ["0.6 w 0 G"]
    for r in range(len(rows) + 1):
        y = top - r * row_h
        ops.append(f"{x_edges[0]} {y} m {x_edges[-1]} {y} l S")
    for x in x_edges:
        ops.append(f"{x} {top} m {x} {top - len(rows) * row_h} l S")
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            texts.append(Text(x_edges[c] + 8, top - r * row_h - 18, cell, BODY, bold=(r == 0)))
    texts.append(Text(100, top - len(rows) * row_h - 24, "Table 4.1 Quantities and their SI units", 10))
    chunk, _ = _paragraph(PARA_B, LEFT, 470, 92)
    return PageSpec(texts=texts + chunk, extra="\n".join(ops))


def _figure_pixels(w: int = 240, h: int = 160) -> tuple[int, int, bytes]:
    data = bytearray()
    for y in range(h):
        for x in range(w):
            inside = (x - w / 2) ** 2 / (w / 3) ** 2 + (y - h / 2) ** 2 / (h / 3) ** 2 < 1
            stripe = (x // 12) % 2 == 0
            data.append(60 if inside else (200 if stripe else 235))
    return w, h, bytes(data)


def figure_page() -> PageSpec:
    texts = [Text(LEFT, TOP, "4.4 Graphs of Motion", 16, bold=True)]
    chunk, _ = _paragraph(PARA_A, LEFT, TOP - 30, 92)
    texts += chunk
    texts.append(Text(170, 330, "Figure 4.2 Distance-time graph of a moving bicycle", 10))
    return PageSpec(texts=texts, images=[Image(170, 350, 280, 190, gray=_figure_pixels())])


def equation_page() -> PageSpec:
    texts = [Text(LEFT, TOP, "4.5 Equations of Motion", 16, bold=True)]
    chunk, y = _paragraph(PARA_C, LEFT, TOP - 30, 92)
    texts += chunk
    texts.append(Text(250, y - 20, "v = u + a t", 16))
    texts.append(Text(480, y - 20, "(4.1)", 11))
    chunk, _ = _paragraph(PARA_B, LEFT, y - 60, 92)
    return PageSpec(texts=texts + chunk)


def scanned_page_from_image(gray: tuple[int, int, bytes], width: float = 612, height: float = 792) -> PageSpec:
    w, h, _ = gray
    scale = min((width - 72) / w, (height - 72) / h)
    return PageSpec(images=[Image(36, height - 36 - h * scale, w * scale, h * scale, gray=gray)])


def write_textbook(path: Path) -> Path:
    """Five pages: single column, two columns, table, figure, equation."""
    return write_pdf(path, [single_column_page(), two_column_page(), table_page(), figure_page(), equation_page()])
