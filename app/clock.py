from datetime import UTC, datetime


def now_utc() -> str:
    return datetime.now(UTC).isoformat()
