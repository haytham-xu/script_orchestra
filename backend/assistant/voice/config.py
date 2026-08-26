"""
Voice config

Runtime-switchable engine selection is persisted in a tiny JSON file so
UI changes survive server restarts. Model download caches use the default
HuggingFace / library locations under ~/.cache.
"""
import json
from pathlib import Path
from typing import Dict

_MODULE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = _MODULE_DIR.parent / "voice_config.json"

# Whisper: model tag → human notes shown in the switcher UI
WHISPER_MODELS = {
    "medium":   "~770 MB · fast · CJK ok · daily use",
    "large-v3": "~1.5 GB · slower · best CJK / mixed accuracy",
}
DEFAULT_WHISPER_MODEL = "medium"

# TTS engines
TTS_ENGINES = {
    "say":    "macOS built-in · offline · zero-config · lower fidelity",
    "kokoro": "local neural TTS · ~330 MB · natural voices · first load slow",
}
DEFAULT_TTS_ENGINE = "say"

# Language hint given to Whisper. `auto` lets it detect.
DEFAULT_ASR_LANGUAGE = "auto"

# CTranslate2 compute type. `int8` is a good CPU default on Mac (RAM/speed
# trade-off); large-v3 users on M2/M3 with plenty of RAM can bump to
# `int8_float16`.
DEFAULT_COMPUTE_TYPE = "int8"

# Max upload size (25 MB) for transcription — matches OpenAI's public API
# and prevents accidental multi-gig uploads.
MAX_AUDIO_BYTES = 25 * 1024 * 1024


def _defaults() -> Dict:
    return {
        "whisper_model": DEFAULT_WHISPER_MODEL,
        "asr_language": DEFAULT_ASR_LANGUAGE,
        "compute_type": DEFAULT_COMPUTE_TYPE,
        "tts_engine": DEFAULT_TTS_ENGINE,
    }


def load_config() -> Dict:
    """Return the persisted config, filling in defaults for missing keys."""
    cfg = _defaults()
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        except Exception:
            pass
    # Guard against a corrupted whisper model / tts engine name.
    if cfg.get("whisper_model") not in WHISPER_MODELS:
        cfg["whisper_model"] = DEFAULT_WHISPER_MODEL
    if cfg.get("tts_engine") not in TTS_ENGINES:
        cfg["tts_engine"] = DEFAULT_TTS_ENGINE
    return cfg


def save_config(new_values: Dict) -> Dict:
    """Merge `new_values` into the persisted config and return the result."""
    current = load_config()
    for key in ("whisper_model", "asr_language", "compute_type", "tts_engine"):
        if key in new_values:
            current[key] = new_values[key]
    # Validate again after the merge.
    if current["whisper_model"] not in WHISPER_MODELS:
        raise ValueError(
            f"whisper_model must be one of {list(WHISPER_MODELS.keys())}"
        )
    if current["tts_engine"] not in TTS_ENGINES:
        raise ValueError(
            f"tts_engine must be one of {list(TTS_ENGINES.keys())}"
        )
    CONFIG_PATH.write_text(json.dumps(current, indent=2))
    return current
