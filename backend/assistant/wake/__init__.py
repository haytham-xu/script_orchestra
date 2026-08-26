"""
Wake-word listener sub-module.

Runs a background thread that opens the default microphone at 16 kHz
mono, streams frames through openWakeWord's neural network, and — when
a keyword score crosses the threshold — records the following audio
(bounded by voice-activity detection), transcribes it via the existing
Whisper wrapper, and emits a WebSocket event to the UI.

Design choices:

  * `openwakeword` ships a handful of pre-trained keywords. No token,
    no cloud dependency.
  * Recording after wake: fixed max-duration + VAD trailing silence
    (webrtcvad-free simple energy gate to stay dependency-light).
  * Whisper transcription is delegated to `voice.asr.transcribe` so the
    model choice (medium / large-v3) stays consistent with the manual
    mic button.
"""
