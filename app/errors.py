from typing import Any


class Problem(Exception):
    def __init__(
        self, status: int, code: str, detail: str, *, extra: dict[str, Any] | None = None
    ) -> None:
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra or {}
        super().__init__(code)
