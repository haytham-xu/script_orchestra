"""
Wake-word listener service — background microphone thread + detector.

State machine:

    IDLE ── start() ──> LISTENING
                            │
                            │ score >= threshold  →  RECORDING
                            │
                            │ (VAD tail or timeout) →  TRANSCRIBE → EMIT → LISTENING
                            │
    LISTENING ── stop() ──> IDLE

Only one listener runs at a time. `sounddevice.RawInputStream` gives us
raw int16 frames from the default input device.
"""
import io
import logging
import threading
import time
import wave
from typing import Dict, List, Optional

import numpy as np

from ..voice import asr as voice_asr
from .config import (
    BUILTIN_KEYWORDS,
    COOLDOWN_SECONDS,
    DEFAULT_KEYWORD,
    DEFAULT_THRESHOLD,
    FRAME_SAMPLES,
    MIN_UTTERANCE_SECONDS,
    POST_WAKE_MAX_SECONDS,
    SAMPLE_RATE,
    SILENCE_RMS_THRESHOLD,
    SILENCE_TAIL_SECONDS,
)

logger = logging.getLogger("assistant.wake")


class WakeService:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._keyword = DEFAULT_KEYWORD
        self._threshold = DEFAULT_THRESHOLD
        self._model = None
        self._broadcaster = None
        self._last_error: Optional[str] = None

    # ── Public API ─────────────────────────────────────────

    def register_broadcaster(self, fn) -> None:
        """Callable used to push events (dict) to WebSocket clients."""
        self._broadcaster = fn

    def get_status(self) -> Dict:
        return {
            "running": self._running,
            "keyword": self._keyword,
            "threshold": self._threshold,
            "keywords_available": BUILTIN_KEYWORDS,
            "last_error": self._last_error,
        }

    def start(self, keyword: Optional[str] = None,
              threshold: Optional[float] = None) -> Dict:
        with self._lock:
            if self._running:
                raise RuntimeError("wake listener is already running")

            if keyword and keyword not in BUILTIN_KEYWORDS:
                raise ValueError(
                    f"keyword must be one of {BUILTIN_KEYWORDS}"
                )
            if keyword:
                self._keyword = keyword
            if threshold is not None:
                self._threshold = float(threshold)

            self._last_error = None
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop, daemon=True
            )
            self._running = True
            self._thread.start()

        self._emit("status", {"running": True, "keyword": self._keyword})
        return self.get_status()

    def stop(self) -> Dict:
        with self._lock:
            if not self._running:
                return self.get_status()
            self._stop_event.set()
        # Don't hold the lock while joining — the thread may need to emit.
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._running = False
        self._emit("status", {"running": False, "keyword": self._keyword})
        return self.get_status()

    # ── Internals ─────────────────────────────────────────

    def _emit(self, event_type: str, payload: Dict) -> None:
        if self._broadcaster:
            try:
                self._broadcaster({"type": event_type, **payload})
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[wake] broadcaster failed: {exc}")

    def _load_model(self):
        if self._model is not None:
            return self._model
        from openwakeword.model import Model
        logger.info(f"[wake] loading openWakeWord model for '{self._keyword}'")
        # Loading only the one keyword keeps memory & CPU minimal.
        self._model = Model(
            wakeword_models=[self._keyword],
            inference_framework="onnx",
        )
        return self._model

    def _run_loop(self) -> None:
        """Listen for the wake word, then record + transcribe on trigger."""
        try:
            import sounddevice as sd
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"sounddevice unavailable: {exc}"
            self._emit("error", {"message": self._last_error})
            self._running = False
            return

        try:
            model = self._load_model()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"failed to load model: {exc}"
            self._emit("error", {"message": self._last_error})
            self._running = False
            return

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
            ) as stream:
                self._listen_forever(stream, model)
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"audio stream failed: {exc}"
            self._emit("error", {"message": self._last_error})
        finally:
            self._running = False

    def _listen_forever(self, stream, model) -> None:
        keyword = self._keyword
        threshold = self._threshold
        cooldown_until = 0.0

        while not self._stop_event.is_set():
            raw, overflowed = stream.read(FRAME_SAMPLES)
            if overflowed:
                # Not fatal — just means we were slow.
                logger.debug("[wake] audio overflow")

            frame = np.frombuffer(bytes(raw), dtype=np.int16)
            scores = model.predict(frame)
            score = float(scores.get(keyword, 0.0))

            if time.time() >= cooldown_until and score >= threshold:
                self._emit("wake", {"keyword": keyword, "score": round(score, 3)})
                logger.info(f"[wake] triggered on '{keyword}' (score={score:.3f})")

                utterance = self._record_utterance(stream)
                if utterance is None:
                    self._emit("cancelled", {"reason": "too short or silent"})
                else:
                    self._emit("transcribing", {})
                    try:
                        result = voice_asr.transcribe(
                            utterance,
                            filename_hint="wake.wav",
                        )
                        self._emit("transcript", {
                            "text": result.get("text", ""),
                            "language": result.get("language"),
                            "duration": result.get("duration"),
                        })
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("[wake] transcribe failed")
                        self._emit("error", {"message": f"transcribe: {exc}"})

                # Reset detector so a rescored frame doesn't immediately
                # re-fire on the leftover activation.
                try:
                    model.reset()
                except Exception:  # noqa: BLE001
                    pass
                cooldown_until = time.time() + COOLDOWN_SECONDS

    def _record_utterance(self, stream) -> Optional[bytes]:
        """
        Read frames until either the user goes silent for
        `SILENCE_TAIL_SECONDS` or we hit the hard duration cap. Returns a
        WAV blob (16-bit mono 16 kHz) or None if the clip is too short.
        """
        pcm_chunks: List[bytes] = []
        started_at = time.time()
        last_voice_at = started_at
        while True:
            if self._stop_event.is_set():
                return None
            raw, _ = stream.read(FRAME_SAMPLES)
            pcm = bytes(raw)
            pcm_chunks.append(pcm)

            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
            now = time.time()
            if rms >= SILENCE_RMS_THRESHOLD:
                last_voice_at = now

            elapsed = now - started_at
            silence = now - last_voice_at
            if elapsed >= POST_WAKE_MAX_SECONDS:
                break
            if elapsed > MIN_UTTERANCE_SECONDS and silence >= SILENCE_TAIL_SECONDS:
                break

        duration = time.time() - started_at
        if duration < MIN_UTTERANCE_SECONDS:
            return None

        pcm = b"".join(pcm_chunks)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm)
        return buf.getvalue()


_service_instance: Optional[WakeService] = None


def get_service() -> WakeService:
    global _service_instance
    if _service_instance is None:
        _service_instance = WakeService()
    return _service_instance
