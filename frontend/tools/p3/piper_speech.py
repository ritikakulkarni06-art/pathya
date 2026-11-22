"""Piper speech adapter for the Role 3 backend: free, offline, runs on a laptop CPU.

Copy this file to app/adapters/piper_speech.py in the backend, then:

    pip install piper-tts==1.3.0 (or newer)
    python -m piper.download_voices en_US-lessac-medium --download-dir voices
    python -m piper.download_voices hi_IN-pratham-medium --download-dir voices

and set
    SPEECH_PROVIDER=python:app.adapters.piper_speech:PiperSpeech
    PIPER_VOICE_DIR=<folder with the .onnx and .onnx.json files>
    SEGMENTER=pathya

The language picks the model: en -> en_US-lessac-medium, hi -> hi_IN-pratham-medium. Override with
PIPER_VOICE_EN / PIPER_VOICE_HI. The `voice` argument is used as the model name when such a model exists in
PIPER_VOICE_DIR; otherwise ("default") the language model is used. Clips are real narration, never synthetic.
"""

import io
import os
import wave
from pathlib import Path

from piper import PiperVoice

from app.adapters.speech import SpeechClip, SpeechUnavailable, SpeechUnit

DEFAULTS = {"en": "en_US-lessac-medium", "hi": "hi_IN-pratham-medium"}


class PiperSpeech:
    paid = False

    def __init__(self) -> None:
        self.folder = Path(os.environ.get("PIPER_VOICE_DIR", "voices"))
        self.models = {
            lang: os.environ.get(f"PIPER_VOICE_{lang.upper()}", name) for lang, name in DEFAULTS.items()
        }
        self.loaded: dict[str, PiperVoice] = {}
        # Changing a model changes the version, so P3's cache key never reuses clips from another voice.
        self.engine_version = "piper-1/" + "+".join(f"{k}={v}" for k, v in sorted(self.models.items()))

    def _voice(self, name: str) -> PiperVoice:
        if name not in self.loaded:
            path = self.folder / f"{name}.onnx"
            if not path.is_file():
                raise SpeechUnavailable()
            self.loaded[name] = PiperVoice.load(str(path))
        return self.loaded[name]

    def synthesize(self, units: list[SpeechUnit], voice: str, language: str) -> list[SpeechClip]:
        if (self.folder / f"{voice}.onnx").is_file():
            name = voice
        elif language in self.models:
            name = self.models[language]
        else:
            raise SpeechUnavailable()
        model = self._voice(name)
        clips = []
        for unit in units:
            out = io.BytesIO()
            with wave.open(out, "wb") as stream:
                model.synthesize_wav(unit.text, stream)
            out.seek(0)
            with wave.open(out, "rb") as stream:
                duration = round(stream.getnframes() * 1000 / stream.getframerate())
            clips.append(SpeechClip(unit.unit_id, out.getvalue(), "audio/wav", duration))
        return clips
