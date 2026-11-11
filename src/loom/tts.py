"""Narration generation: Fish Audio (cloned voice) plus offline preview voices.

Narration is generated per scene and cached by a hash of (provider, voice,
model, speed, text), so editing one scene's text only regenerates that scene.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from .config import Settings
from .media import MediaError, duration, ffmpeg

FISH_TTS_URL = "https://api.fish.audio/v1/tts"
SAMPLE_RATE = 44100


class TTSError(RuntimeError):
    pass


def _normalise_wav(src: Path, dst: Path) -> None:
    """Convert anything to 44.1 kHz mono 16-bit WAV."""
    ffmpeg("-i", str(src), "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(dst))


def fish_tts(text: str, out: Path, s: Settings, client: httpx.Client | None = None) -> None:
    if not s.fish_api_key:
        raise TTSError("FISH_API_KEY is not set (add it to .env)")
    if not s.fish_reference_id:
        raise TTSError("FISH_REFERENCE_ID is not set (your cloned voice model id)")
    body = {
        "text": text,
        "reference_id": s.fish_reference_id,
        "format": "wav",
        "sample_rate": SAMPLE_RATE,
        "normalize": True,
        "latency": s.fish_latency,
        "prosody": {"speed": s.fish_speed},
    }
    headers = {"Authorization": f"Bearer {s.fish_api_key}", "model": s.fish_model}
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(120, connect=15))
    try:
        for attempt in range(5):
            try:
                r = client.post(FISH_TTS_URL, json=body, headers=headers)
            except httpx.TransportError as e:
                err = f"network error: {e}"
            else:
                if r.status_code == 200:
                    tmp = out.with_suffix(".raw.wav")
                    tmp.write_bytes(r.content)
                    try:
                        _normalise_wav(tmp, out)
                    finally:
                        tmp.unlink(missing_ok=True)
                    return
                msg = _fish_error(r)
                if r.status_code in (401, 402, 403, 404, 422):
                    raise TTSError(f"Fish Audio {r.status_code}: {msg}")
                err = f"Fish Audio {r.status_code}: {msg}"
            time.sleep(min(2 ** attempt, 20))
        raise TTSError(f"gave up after retries: {err}")
    finally:
        if own:
            client.close()


def _fish_error(r: httpx.Response) -> str:
    try:
        j = r.json()
        return f"{j.get('message')} {j.get('reason') or ''}".strip()
    except Exception:
        return r.text[:200]


def espeak_tts(text: str, out: Path, s: Settings) -> None:
    if not shutil.which("espeak-ng"):
        raise TTSError("espeak-ng not installed (sudo dnf install espeak-ng)")
    tmp = out.with_suffix(".raw.wav")
    wpm = int(165 * s.fish_speed)
    subprocess.run(["espeak-ng", "-s", str(wpm), "-w", str(tmp), text], check=True)
    try:
        _normalise_wav(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def silent_tts(text: str, out: Path, s: Settings) -> None:
    """Silence of a realistic speaking length; for dry runs and tests."""
    secs = max(1.0, len(text.split()) / 2.6)
    ffmpeg("-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", f"{secs:.2f}",
           "-c:a", "pcm_s16le", str(out))


PROVIDERS = {"fish": fish_tts, "espeak": espeak_tts, "silent": silent_tts}


def voice_key(text: str, s: Settings) -> str:
    ident = {
        "provider": s.tts_provider,
        "voice": s.fish_reference_id if s.tts_provider == "fish" else None,
        "model": s.fish_model if s.tts_provider == "fish" else None,
        "speed": s.fish_speed,
        "text": text,
    }
    return hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()[:16]


def synthesize(text: str, out: Path, s: Settings, force: bool = False) -> dict:
    """Generate `out` (WAV) unless an identical cached version exists.
    Returns metadata including the measured duration."""
    if s.tts_provider not in PROVIDERS:
        raise TTSError(f"unknown tts provider {s.tts_provider!r}")
    meta_path = out.with_suffix(".json")
    key = voice_key(text, s)
    if not force and out.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("key") == key:
            meta["cached"] = True
            return meta
    out.parent.mkdir(parents=True, exist_ok=True)
    PROVIDERS[s.tts_provider](text, out, s)
    try:
        d = duration(out)
    except MediaError as e:
        raise TTSError(f"generated audio is unreadable: {e}") from e
    if d < 0.2:
        raise TTSError(f"generated audio is suspiciously short ({d:.2f}s)")
    meta = {"key": key, "provider": s.tts_provider, "text": text, "duration": round(d, 3),
            "file": out.name, "cached": False}
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta
