"""Render one displayed PDF page in the preview subprocess."""

import importlib
import math
import sys


def main() -> None:
    path, page_index, max_side = sys.argv[1:]
    pdfium = importlib.import_module("pypdfium2")
    with pdfium.PdfDocument(path) as document:
        page = document[int(page_index)]
        try:
            width, height = page.get_size()
            if not all(math.isfinite(value) and value > 0 for value in (width, height)):
                raise ValueError("Invalid page size.")
            bitmap = page.render(scale=int(max_side) / max(width, height), may_draw_forms=False)
            try:
                image = bitmap.to_pil()
                image.thumbnail((int(max_side), int(max_side)))
                image.save(sys.stdout.buffer, format="PNG")
            finally:
                bitmap.close()
        finally:
            page.close()


if __name__ == "__main__":
    main()
