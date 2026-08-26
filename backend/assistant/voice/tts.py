"""
TTS engines

Two implementations behind a common `synthesize` function:
  - `say`   → macOS built-in, no dependency, no download.
  - `kokoro`→ local neural voice, ~330 MB weights downloaded on first use.

Return format is always `(audio_bytes, mime_type)` so the controller
doesn't need to care which engine produced it.

The Kokoro path is best-effort: it imports lazily and returns a clear
error if the package isn't installed, so the module still loads on a
machine without it.
"""
import io
import logging
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Tuple

from .config import load_config

logger = logging.getLogger("assistant.voice.tts")


class TTSError(RuntimeError):
    """Raised when TTS synthesis fails or an engine is unavailable."""


# ── macOS `say` ───────────────────────────────────────────

_SAY_VOICE_ZH = "Tingting"     # Simplified Chinese
_SAY_VOICE_EN = "Samantha"     # US English fallback


def _looks_chinese(text: str) -> bool:
    for ch in text:
        if '一' <= ch <= '鿿':
            return True
    return False


def _synth_say(text: str) -> Tuple[bytes, str]:
    voice = _SAY_VOICE_ZH if _looks_chinese(text) else _SAY_VOICE_EN
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        # `say -o path -v voice text` writes AIFF PCM audio.
        proc = subprocess.run(
            ["say", "-v", voice, "-o", tmp_path, text],
            check=False,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise TTSError(
                f"say failed: {proc.stderr.decode('utf-8', 'ignore')}"
            )
        data = Path(tmp_path).read_bytes()
        return data, "audio/aiff"
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


# ── Kokoro (local neural TTS) ─────────────────────────────

_kokoro_lock = threading.Lock()
_kokoro_pipeline = None


def _get_kokoro():
    """Lazily import and load the Kokoro pipeline. Raises TTSError if the
    package isn't installed or the model can't be downloaded."""
    global _kokoro_pipeline
    with _kokoro_lock:
        if _kokoro_pipeline is not None:
            return _kokoro_pipeline
        try:
            from kokoro import KPipeline  # type: ignore
        except ImportError as exc:
            raise TTSError(
                "Kokoro is not installed. Run: pip install kokoro>=0.9.4 "
                "soundfile"
            ) from exc
        try:
            _kokoro_pipeline = KPipeline(lang_code="a")  # 'a' = auto/american
        except Exception as exc:  # noqa: BLE001
            raise TTSError(f"Failed to load Kokoro model: {exc}") from exc
        return _kokoro_pipeline


def _synth_kokoro(text: str) -> Tuple[bytes, str]:
    pipeline = _get_kokoro()
    voice = "af_bella"  # a nice-sounding default; can be surfaced later

    try:
        import numpy as np  # noqa: F401
    except ImportError as exc:
        raise TTSError("numpy is required for Kokoro output") from exc

    # KPipeline yields (gs, ps, audio) tuples; concatenate audio chunks.
    audio_chunks = []
    sample_rate = 24000  # Kokoro default
    for _, _, audio in pipeline(text, voice=voice):
        audio_chunks.append(audio)

    if not audio_chunks:
        raise TTSError("Kokoro returned no audio")

    import numpy as np
    joined = np.concatenate(audio_chunks).astype(np.float32)
    # Convert float32 [-1, 1] → int16 PCM WAV in memory.
    pcm16 = (joined.clip(-1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue(), "audio/wav"


# ── Public entry point ────────────────────────────────────

def synthesize(text: str, engine: str = None) -> Tuple[bytes, str]:
    """Turn text into audio bytes. Falls back to config-selected engine."""
    if not text or not text.strip():
        raise TTSError("Empty text")

    if engine is None:
        engine = load_config().get("tts_engine", "say")

    if engine == "say":
        return _synth_say(text)
    if engine == "kokoro":
        return _synth_kokoro(text)
    raise TTSError(f"Unknown TTS engine: {engine}")
