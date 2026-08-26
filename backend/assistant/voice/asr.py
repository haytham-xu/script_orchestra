"""
ASR (Whisper) wrapper

Wraps `faster-whisper` behind a small, lazy singleton so:
  - the model loads on first use (server startup stays fast),
  - switching model tag (`medium` ↔ `large-v3`) releases the previous
    instance's memory,
  - the API surface stays trivial: `transcribe(audio_bytes) -> dict`.

The model files are downloaded on demand into `~/.cache/huggingface`
(faster-whisper's default), so no per-project cache to manage.
"""
import logging
import tempfile
import threading
from pathlib import Path
from typing import Dict, Optional

from .config import DEFAULT_COMPUTE_TYPE, WHISPER_MODELS, load_config

logger = logging.getLogger("assistant.voice.asr")


_lock = threading.Lock()
_model_instance = None
_model_tag: Optional[str] = None
_compute_type: Optional[str] = None


def _get_model():
    """Return the singleton faster-whisper model, loading it on first use."""
    global _model_instance, _model_tag, _compute_type

    cfg = load_config()
    tag = cfg["whisper_model"]
    compute_type = cfg.get("compute_type", DEFAULT_COMPUTE_TYPE)

    with _lock:
        # Recreate the instance whenever the tag or compute_type changes so
        # a UI switcher takes effect without a server restart.
        if (_model_instance is None
                or _model_tag != tag
                or _compute_type != compute_type):
            from faster_whisper import WhisperModel
            logger.info(
                f"[asr] loading whisper model tag={tag} compute_type={compute_type}"
            )
            # Drop the previous instance BEFORE loading the new one so we
            # don't briefly hold two large models in memory.
            _model_instance = None
            _model_instance = WhisperModel(
                tag,
                device="cpu",
                compute_type=compute_type,
            )
            _model_tag = tag
            _compute_type = compute_type
        return _model_instance, tag


def unload_model() -> None:
    """Release the loaded model (useful before an explicit switch)."""
    global _model_instance, _model_tag, _compute_type
    with _lock:
        _model_instance = None
        _model_tag = None
        _compute_type = None


def transcribe(audio_bytes: bytes,
               filename_hint: str = "audio.webm",
               language: Optional[str] = None) -> Dict:
    """
    Transcribe an audio blob.

    Args:
        audio_bytes: The full audio payload (any format PyAV / ffmpeg can
            demux — webm / wav / mp3 / mp4 all work).
        filename_hint: Only used as the tempfile suffix so PyAV picks the
            right demuxer.
        language: BCP-47-ish language tag. `None` or "auto" ⇒ auto-detect.

    Returns:
        dict with keys `text`, `language`, `duration`, `segments`,
        `whisper_model`.
    """
    if not audio_bytes:
        raise ValueError("audio payload is empty")

    cfg = load_config()
    if not language or language == "auto":
        language = None
    else:
        language = language.strip() or None

    suffix = Path(filename_hint).suffix or ".webm"

    # faster-whisper reads by file path; write the upload to a tempfile so
    # PyAV/ffmpeg can demux any input format transparently.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model, tag = _get_model()
        segments, info = model.transcribe(
            tmp_path,
            language=language,
            vad_filter=True,
            beam_size=5,
        )
        seg_list = []
        for seg in segments:
            seg_list.append({
                "id": seg.id,
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
            })
        full_text = "".join(s["text"] for s in seg_list).strip()

        return {
            "text": full_text,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 3),
            "duration": round(float(info.duration), 3),
            "segments": seg_list,
            "whisper_model": tag,
        }
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


def current_model() -> Optional[str]:
    return _model_tag
