import json
import logging
from collections.abc import Mapping
from typing import Any

DENIED = {
    "text",
    "question",
    "body",
    "password",
    "api_key",
    "token",
    "authorization",
    "cookie",
    "secret",
    "email",
}


def scrub(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): scrub(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in DENIED)
        }
    if isinstance(value, (list, tuple)):
        return [scrub(item) for item in value]
    return value


def log_event(**fields: Any) -> None:
    logging.getLogger("pathya").info(json.dumps(scrub(fields), separators=(",", ":")))


def configure_logging() -> None:
    logger = logging.getLogger("pathya")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
