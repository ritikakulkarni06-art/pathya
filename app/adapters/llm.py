"""Optional stateless structured generation; no live calls unless explicitly enabled."""

import hashlib
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings
from app.db.connection import Database
from app.logging import log_event
from app.services.costs import PricesUnavailable, load_price, reserve, settle


class LLMUnavailable(Exception):
    def __init__(self, code: str = "assistant_unavailable") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMResult:
    parsed: dict[str, Any]
    usage: Usage
    model_id: str
    raw_text_hash: str


class LLMClient(Protocol):
    def generate_structured(
        self,
        system: str,
        user_payload: dict[str, Any],
        schema: dict[str, Any],
        max_output_tokens: int,
        timeout_s: float,
    ) -> LLMResult: ...


class DisabledLLM:
    def generate_structured(
        self,
        system: str,
        user_payload: dict[str, Any],
        schema: dict[str, Any],
        max_output_tokens: int,
        timeout_s: float,
    ) -> LLMResult:
        raise LLMUnavailable("assistant_disabled")


class FakeLLM:
    """Scripted output is intentionally not validated; the answer pipeline must validate it."""

    def __init__(self, responses: list[dict[str, Any] | LLMUnavailable]) -> None:
        self.responses = iter(responses)
        self.calls = 0

    def generate_structured(
        self,
        system: str,
        user_payload: dict[str, Any],
        schema: dict[str, Any],
        max_output_tokens: int,
        timeout_s: float,
    ) -> LLMResult:
        self.calls += 1
        try:
            result = next(self.responses)
        except StopIteration:
            raise LLMUnavailable() from None
        if isinstance(result, LLMUnavailable):
            raise result
        text = json.dumps(result, ensure_ascii=False)
        return LLMResult(
            result, Usage(0, 0), "fake-scripted-v1", hashlib.sha256(text.encode()).hexdigest()
        )


class Excerpt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    block_id: str = Field(min_length=1, max_length=128)
    rev: int = Field(ge=1)
    text: str = Field(max_length=12000)


class SelectedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question: str = Field(min_length=1, max_length=2000)
    document_revision: int = Field(ge=1)
    evidence: list[Excerpt] = Field(min_length=1, max_length=30)


def usage_counts(body: dict[str, Any]) -> Usage | None:
    usage = body.get("usageMetadata", {})
    if not isinstance(usage, dict):
        return None
    values = [
        usage.get("promptTokenCount"),
        usage.get("candidatesTokenCount"),
        usage.get("thoughtsTokenCount", 0),
    ]
    if any(type(v) is not int or v < 0 for v in values):
        return None
    return Usage(values[0], values[1] + values[2])


class GeminiClient:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        document_id: str,
        user_id: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.document_id = document_id
        self.user_id = user_id
        self.transport = transport

    def generate_structured(
        self,
        system: str,
        user_payload: dict[str, Any],
        schema: dict[str, Any],
        max_output_tokens: int,
        timeout_s: float,
    ) -> LLMResult:
        config = self.settings
        if not config.llm_enabled:
            raise LLMUnavailable("assistant_disabled")
        if config.llm_provider != "gemini" or not re.fullmatch(
            r"[A-Za-z0-9._-]+", config.llm_model_id
        ):
            raise LLMUnavailable("assistant_unavailable")
        try:
            selected = SelectedEvidence.model_validate(user_payload)
        except ValidationError:
            raise LLMUnavailable("invalid_llm_payload") from None
        user_text = json.dumps(selected.model_dump(), ensure_ascii=False, separators=(",", ":"))
        # Conservative local byte bound, not a model tokenizer. Refuse rather than truncate.
        input_bound = len((system + user_text + json.dumps(schema)).encode("utf-8")) + 512
        if input_bound > config.llm_max_input_tokens:
            raise LLMUnavailable("assistant_input_too_long")
        if (
            not 1 <= max_output_tokens <= config.llm_max_output_tokens
            or not 0 < timeout_s <= config.llm_timeout_seconds
        ):
            raise LLMUnavailable("invalid_llm_limits")
        try:
            price = load_price(config)
        except PricesUnavailable:
            raise LLMUnavailable("prices_unverified") from None
        call_id = str(uuid4())
        request = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "maxOutputTokens": max_output_tokens,
                "candidateCount": 1,
            },
        }
        with httpx.Client(
            transport=self.transport, trust_env=False, follow_redirects=False
        ) as client:
            for attempt in range(1, config.llm_max_retries + 2):
                event_id = reserve(
                    self.database, config, price, self.document_id, self.user_id, call_id, attempt
                )
                status = 0
                body: dict[str, Any] = {}
                retryable = False
                try:
                    with client.stream(
                        "POST",
                        "https://generativelanguage.googleapis.com/v1beta/models/"
                        + config.llm_model_id
                        + ":generateContent",
                        headers={"x-goog-api-key": config.gemini_api_key.get_secret_value()},
                        json=request,
                        timeout=timeout_s,
                    ) as response:
                        status = response.status_code
                        retryable = status == 429 or 500 <= status <= 599
                        if status == 200:
                            raw = bytearray()
                            for part in response.iter_bytes():
                                raw.extend(part)
                                if len(raw) > 1_000_000:
                                    raise ValueError("response_too_large")
                            parsed_body = json.loads(raw)
                            if not isinstance(parsed_body, dict):
                                raise ValueError("invalid_response")
                            body = parsed_body
                except (httpx.HTTPError, ValueError, TypeError):
                    # Timeouts/transport failures are ambiguous: no retry and keep worst cost.
                    retryable = False
                usage = usage_counts(body)
                settle(
                    self.database,
                    event_id,
                    price,
                    "response" if status == 200 and body else "failed_unknown_cost",
                    usage.input_tokens if usage else None,
                    usage.output_tokens if usage else None,
                )
                log_event(
                    event="llm_attempt",
                    usage_event_id=event_id,
                    attempt=attempt,
                    status=status,
                    usage_known=usage is not None,
                )
                if status == 200 and body:
                    try:
                        candidate = body["candidates"][0]
                        if candidate.get("finishReason") != "STOP" or usage is None:
                            raise ValueError("incomplete_response")
                        text = "".join(
                            part["text"]
                            for part in candidate["content"]["parts"]
                            if not part.get("thought", False)
                        )
                        output = json.loads(text)
                        if not isinstance(output, dict):
                            raise ValueError("invalid_response")
                        return LLMResult(
                            output,
                            usage,
                            config.llm_model_id,
                            hashlib.sha256(text.encode()).hexdigest(),
                        )
                    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                        raise LLMUnavailable("assistant_invalid_response") from None
                if not retryable or attempt > config.llm_max_retries:
                    break
                time.sleep(random.uniform(0.05, 0.15) * 2 ** (attempt - 1))
        raise LLMUnavailable()
