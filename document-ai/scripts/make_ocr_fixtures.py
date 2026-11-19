"""Regenerate synthetic OCR fixture images in tests/fixtures/ocr/.

Pillow in this environment has no complex-text shaping (libraqm), which would
draw Devanagari vowel signs in the wrong place. A headless Chromium-based
browser (Edge or Chrome) shapes the text correctly with the Windows "Nirmala
UI" font, so fixtures are rendered as browser screenshots. All text is
original sample sentences, not textbook content.

Usage: .venv\\Scripts\\python.exe scripts\\make_ocr_fixtures.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "ocr"
BROWSERS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]

FIXTURES: dict[str, list[str]] = {
    "english": [
        "The speed of the car is 4.5 metres per second.",
        "Net change = 7.25 - 2.50 = 4.75",
    ],
    "hindi": [
        "प्रकाश का परावर्तन",
        "विद्यार्थी किताब पढ़ते हैं।",
        "सूर्य पूर्व में उगता है।",
    ],
    "mixed": [
        "आपतन कोण (angle of incidence)",
        "Mirror दर्पण 2024",
    ],
}


def _browser() -> Path:
    for candidate in BROWSERS:
        if candidate.is_file():
            return candidate
    raise SystemExit("No Edge/Chrome executable found for rendering fixtures.")


def render(name: str, lines: list[str], browser: Path, workdir: Path) -> Path:
    body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    page = workdir / f"{name}.html"
    page.write_text(
        "<!doctype html><meta charset='utf-8'><style>html,body{margin:0;background:#fff}"
        "body{padding:40px 60px;font:44px 'Nirmala UI',Arial,sans-serif;color:#111}"
        "p{margin:0 0 36px 0;white-space:nowrap}</style>" + body, encoding="utf-8")
    target = OUT / f"{name}.png"
    height = 80 + len(lines) * 100
    subprocess.run(
        [str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
         f"--user-data-dir={workdir / 'profile'}", "--force-device-scale-factor=1",
         f"--window-size=1400,{height}", f"--screenshot={target}", page.as_uri()],
        check=True, timeout=60, capture_output=True)
    return target


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    browser = _browser()
    workdir = Path(tempfile.mkdtemp(prefix="pathya_fixtures_"))
    try:
        for name, lines in FIXTURES.items():
            print("wrote", render(name, lines, browser, workdir))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    (OUT / "expected.json").write_text(json.dumps(FIXTURES, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
