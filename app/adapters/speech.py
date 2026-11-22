import importlib
import io
import re
import wave
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from app.config import Settings
from app.errors import Problem
from app.services.sentences import sentence_ranges


@dataclass(frozen=True)
class SpeechUnit:
    unit_id: str
    block_id: str
    text: str
    lang: str
    offset_start: int
    offset_end: int
    alias_applied: bool = False


@dataclass(frozen=True)
class SpeechClip:
    unit_id: str
    audio_bytes: bytes
    mime: str
    duration_ms: int


class SpeechUnavailable(Problem):
    def __init__(self, code: str = "voice_unavailable") -> None:
        super().__init__(503, code, "This voice is unavailable. Continue reading the text.")


class SpeechProvider(Protocol):
    engine_version: str
    paid: bool

    def synthesize(
        self, units: list[SpeechUnit], voice: str, language: str
    ) -> list[SpeechClip]: ...


class DisabledSpeechProvider:
    engine_version = "disabled"
    paid = False

    def synthesize(self, units: list[SpeechUnit], voice: str, language: str) -> list[SpeechClip]:
        raise SpeechUnavailable()


class StubSpeechProvider:
    """Deterministic silence for tests/demos; never presented as real narration."""

    engine_version = "stub-silence-v1"
    paid = False

    def synthesize(self, units: list[SpeechUnit], voice: str, language: str) -> list[SpeechClip]:
        if voice == "unavailable":
            raise SpeechUnavailable()
        clips = []
        for unit in units:
            duration = max(100, min(3000, len(unit.text) * 20))
            output = io.BytesIO()
            with wave.open(output, "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(b"\x00\x00" * (duration * 8))
            clips.append(SpeechClip(unit.unit_id, output.getvalue(), "audio/wav", duration))
        return clips


class ExternalSpeechProvider:
    def __init__(self, specification: str, engine_version: str) -> None:
        try:
            module, attribute = specification.removeprefix("python:").split(":", 1)
            self.implementation = getattr(importlib.import_module(module), attribute)()
        except (ValueError, ImportError, AttributeError, TypeError):
            raise Problem(
                503,
                "speech_configuration",
                "The speech adapter could not be loaded. Text remains available.",
            ) from None
        self.engine_version = str(getattr(self.implementation, "engine_version", engine_version))
        if not self.engine_version:
            raise Problem(
                503,
                "speech_configuration",
                "Configure the speech engine version before building audio.",
            )
        self.paid = bool(getattr(self.implementation, "paid", True))

    def synthesize(self, units: list[SpeechUnit], voice: str, language: str) -> list[SpeechClip]:
        result = self.implementation.synthesize(units, voice, language)
        if not isinstance(result, list) or not all(isinstance(clip, SpeechClip) for clip in result):
            raise Problem(
                502,
                "invalid_speech_output",
                "The speech adapter returned an unsupported result. Read the text while the adapter is checked.",
            )
        return result


def provider(settings: Settings) -> SpeechProvider:
    if settings.speech_provider == "disabled":
        return DisabledSpeechProvider()
    if settings.speech_provider == "stub":
        if settings.pathya_env == "prod":
            raise Problem(
                503, "synthetic_audio_forbidden", "Synthetic silent audio is for development only."
            )
        return StubSpeechProvider()
    if settings.speech_provider.startswith("python:"):
        return ExternalSpeechProvider(settings.speech_provider, settings.speech_engine_version)
    raise Problem(503, "speech_configuration", "Select a supported speech adapter.")


def segment(block: dict[str, Any], settings: Settings) -> list[SpeechUnit]:
    if settings.segmenter == "pathya":
        text: str = block["text_current"]
        return [
            SpeechUnit(str(uuid4()), block["id"], text[start:end], block["lang"], start, end)
            for start, end in sentence_ranges(text)
            if text[start:end].strip()
        ]
    if settings.segmenter:
        try:
            module, attribute = settings.segmenter.removeprefix("python:").split(":", 1)
            result = getattr(importlib.import_module(module), attribute)(block)
        except (ValueError, ImportError, AttributeError):
            raise Problem(
                503, "segmenter_configuration", "The sentence segmenter could not be loaded."
            ) from None
        if not isinstance(result, list) or not all(isinstance(unit, SpeechUnit) for unit in result):
            raise Problem(
                502, "invalid_speech_units", "The segmenter returned unsupported sentence units."
            )
        return result
    if settings.pathya_env == "prod":
        raise Problem(
            503,
            "segmenter_required",
            "Configure Person 2's tested sentence segmenter before generating narration.",
        )
    units = []
    for match in re.finditer(r"[^.!?\u0964]+[.!?\u0964]?", block["text_current"]):
        text = match.group()
        leading = len(text) - len(text.lstrip())
        trailing = len(text.rstrip())
        if text.strip():
            units.append(
                SpeechUnit(
                    str(uuid4()),
                    block["id"],
                    text.strip(),
                    block["lang"],
                    match.start() + leading,
                    match.start() + trailing,
                )
            )
    return units
