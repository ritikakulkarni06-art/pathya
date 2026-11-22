"""Synthesise many sentences with one Piper model load. Reads JSON lines {"text", "out"} on stdin."""
import json, sys, wave
from piper import PiperVoice

voice = PiperVoice.load(sys.argv[1])
sys.stdin.reconfigure(encoding="utf-8")
for line in sys.stdin:
    job = json.loads(line)
    with wave.open(job["out"], "wb") as w:
        voice.synthesize_wav(job["text"], w)
    print(job["out"], flush=True)
