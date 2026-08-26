"""
Wake-word config
"""

SAMPLE_RATE = 16000     # openWakeWord + Whisper both expect 16 kHz mono
FRAME_SAMPLES = 1280    # 80 ms at 16 kHz (openWakeWord's native frame size)

# Default keywords shipped by openWakeWord. Users can pick from this list.
BUILTIN_KEYWORDS = [
    "alexa",
    "hey_jarvis",
    "hey_mycroft",
    "hey_rhasspy",
]
DEFAULT_KEYWORD = "hey_jarvis"

# Detection sensitivity (score threshold). Higher = fewer false positives
# but easier to miss real wakes. 0.5 is openWakeWord's suggested sweet
# spot; expose it later if we want a slider.
DEFAULT_THRESHOLD = 0.5

# After a wake trigger:
#   - `POST_WAKE_MAX_SECONDS`: hard cap on the follow-up recording.
#   - `SILENCE_TAIL_SECONDS`: cut recording after this many seconds of
#     sustained silence (below `SILENCE_RMS_THRESHOLD`).
#   - `MIN_UTTERANCE_SECONDS`: refuse very-short blips (probably noise).
POST_WAKE_MAX_SECONDS = 20.0
SILENCE_TAIL_SECONDS = 1.2
SILENCE_RMS_THRESHOLD = 0.010    # 0..1 range; empirical for a quiet room
MIN_UTTERANCE_SECONDS = 0.4

# After a successful detection + transcription, ignore further wake-word
# hits for this long so a follow-up utterance can't re-trigger.
COOLDOWN_SECONDS = 2.0
