"""
Voice sub-module: ASR (Whisper) + TTS (say / Kokoro).

Kept as a sub-package so assistant/service.py stays focused on chat while
voice-specific dependencies (faster-whisper, kokoro, etc.) live here.
"""
