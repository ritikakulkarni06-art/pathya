"""Shared handling for real-engine availability in integration tests.

By default a missing engine (Tesseract with eng+hin, Docling model weights)
SKIPS the real-engine tests, so a fresh clone still runs the unit suite.
Set PATHYA_REQUIRE_REAL_ENGINES=1 (CI does) to turn those skips into
failures, so a run can never look green just because nothing real executed.
"""

from __future__ import annotations

import os
from typing import NoReturn

import pytest

REQUIRE_ENV = "PATHYA_REQUIRE_REAL_ENGINES"


def unavailable(reason: str) -> NoReturn:
    if os.environ.get(REQUIRE_ENV) == "1":
        pytest.fail(f"{reason} (required because {REQUIRE_ENV}=1)", pytrace=False)
    pytest.skip(reason)
