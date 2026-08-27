# Voice Engines — Comparison & Selection

The Assistant tool ships two switchable implementations for both ASR
(speech → text) and TTS (text → speech). This document focuses on **resource
cost** — latency, memory, disk, CPU.

*Target platform: macOS on Apple Silicon (M1/M2/M3).*

---

## ASR: Whisper `medium` vs `large-v3`

Both run through `faster-whisper` (CTranslate2 backend) with
`compute_type=int8` on CPU.

| Dimension | **medium** | **large-v3** |
|---|---|---|
| Model weights (int8) | **~770 MB** | **~1.5 GB** |
| First-time download | 30–60 s | 60–120 s |
| Resident memory (inference) | **~1.5–2 GB** | **~3–4 GB** |
| Transcribe 5s audio | **~0.4–0.7 s** | **~1.0–1.6 s** |
| Transcribe 30s audio | **~2–3 s** | **~5–8 s** |
| CPU peak (during transcription) | 300–500 % | 500–800 % |
| CJK recognition quality | good | **excellent** |
| Mixed-language input | usable | **noticeably more stable** |
| Numbers / proper nouns / names | fair | **good** |
| Long audio (>5 min) stability | good | **excellent** |

### When to use medium

- Short phrases, everyday conversation, quick Q&A
- Tight on memory (many apps open at once)
- Latency-sensitive (want results the moment you stop speaking)

### When to use large-v3

- Heavy mixed-language input, strong accents, many names/terms
- Meeting notes, podcasts, long recordings
- 8+ GB free memory and a 1–2 s wait is acceptable

### Rule of thumb

Default to `medium` for everyday use; switch to `large-v3` when proper nouns
are misrecognized or a name is wrong several times in a row. The difference is
less about the accuracy number (both are 90%+) and more about **whether the
specific errors are tolerable for your use**.

Switching is a dropdown in the UI; the backend **unloads the old model and
loads the new one** without a service restart. The first load of a new model
has a 5–10 s gap.

---

## TTS: `say` vs `kokoro`

| Dimension | **say** (macOS system command) | **kokoro** (local neural TTS) |
|---|---|---|
| Install | **none** — built into macOS | `pip install "kokoro>=0.9.4" soundfile` |
| Model weights | 0 | **~330 MB** |
| First-call latency | **50–150 ms** | 3–8 s (first weight load) |
| Subsequent latency | **50–150 ms** | 200–600 ms |
| Resident memory | 0 | **~500 MB–1 GB** |
| CPU peak | <10 % | 100–300 % |
| Non-English support | ✅ (system voices) | limited (English-first by default) |
| Audio quality | clear but robotic | **natural, near-human** |
| Output format | AIFF | WAV |

### When to use say

- You just need intelligible output, not a human-like voice
- Want it working immediately with nothing to install/download
- Need non-English output via the built-in system voices

### When to use kokoro

- You want the assistant's voice to sound more natural
- Output is primarily English
- 500 MB–1 GB resident memory and a slow first load are acceptable

### Note on kokoro & non-English

Kokoro defaults to English voices; non-English output has a noticeable English
accent. If the assistant is used mostly in another language, **staying on
`say` is currently recommended**. Revisit when Kokoro ships better multilingual
voices, or switch to a TTS better suited for the target language (e.g. XTTS-v2,
GPT-SoVITS).

---

## Quick decision matrix

| Need | ASR | TTS |
|---|---|---|
| Default (quick start) | `medium` | `say` |
| Heavy mixed-language, many names | `large-v3` | `say` |
| English-first, quality-focused | `medium` | `kokoro` |
| Meeting notes, long recordings | `large-v3` | *(usually no TTS)* |
| Tight on memory | `medium` | `say` |

---

## How to switch

**In the UI**: Assistant → Settings drawer → Voice engines dropdown.

**Via API**:
```bash
# Read current config + options
curl http://localhost:50001/assistant/assistant/voice/config

# Switch models
curl -X PUT http://localhost:50001/assistant/assistant/voice/config \
     -H "Content-Type: application/json" \
     -d '{"whisper_model":"large-v3","tts_engine":"kokoro"}'
```

**Where config is stored**: `backend/assistant/voice_config.json` (auto-generated;
no need to edit by hand).

---

## FAQ

**Q: Does switching the Whisper model require a backend restart?**
A: No. The next `/voice/transcribe` call releases the old model and loads the
new one; the first call waits 5–10 s.

**Q: Kokoro is installed but errors out — what now?**
A: `say` is the always-available fallback. The API returns 400 with a clear
reason (e.g. "Kokoro is not installed"). The frontend should offer `say` as a
downgrade option.

**Q: Where are model files stored, and can they be pre-downloaded?**
A: Faster-Whisper uses the HuggingFace cache at `~/.cache/huggingface/hub/`.
You can pre-download with
`huggingface-cli download Systran/faster-whisper-large-v3`.

**Q: Why `int8` compute_type?**
A: On Apple Silicon CPUs, `int8` is the best balance of speed/memory/accuracy.
With ample free memory, try `int8_float16` (slightly faster, slightly more
memory) via the same API: `PUT /voice/config` with `{"compute_type": "int8_float16"}`.
