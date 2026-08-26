/**
 * usePlayer — singleton audio player for TTS clips.
 *
 * `speak(text)` synthesises via /voice/tts, plays the returned blob, and
 * revokes the object URL when done. A second call while something is
 * still playing interrupts the previous playback.
 *
 * Also exposes `stop()` to explicitly cancel current playback.
 */
import { ref } from 'vue'
import { synthesizeSpeech, type TTSEngine } from './api'

const audio = new Audio()
audio.preload = 'auto'

const isSpeaking = ref(false)
const isBusy = ref(false)     // true from request start until playback ends
let currentObjectUrl: string | null = null
let currentToken = 0

function cleanupObjectUrl() {
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl)
    currentObjectUrl = null
  }
}

audio.addEventListener('ended', () => {
  isSpeaking.value = false
  isBusy.value = false
  cleanupObjectUrl()
})

audio.addEventListener('error', () => {
  isSpeaking.value = false
  isBusy.value = false
  cleanupObjectUrl()
})

/**
 * Strip markdown markers so TTS doesn't read out backticks / asterisks
 * / heading hashes. Fenced code blocks are dropped entirely to avoid
 * reading source code aloud.
 */
export function textForSpeech(md: string): string {
  return md
    // Drop fenced code blocks entirely
    .replace(/```[\s\S]*?```/g, ' ')
    // Inline code → keep content
    .replace(/`([^`]+)`/g, '$1')
    // Bold / italic markers
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    // Headings → strip leading hashes
    .replace(/^#{1,6}\s+/gm, '')
    // Links [text](url) → text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Horizontal rules
    .replace(/^-{3,}$/gm, ' ')
    // Bullet markers
    .replace(/^\s*[-*+]\s+/gm, '')
    // Numbered list markers
    .replace(/^\s*\d+\.\s+/gm, '')
    // Blockquote markers
    .replace(/^\s*>\s+/gm, '')
    // Collapse whitespace
    .replace(/\s+/g, ' ')
    .trim()
}

export function usePlayer() {
  async function speak(text: string, engine?: TTSEngine): Promise<void> {
    const cleaned = textForSpeech(text)
    if (!cleaned) return

    stop()
    const token = ++currentToken
    isBusy.value = true

    let url: string
    try {
      url = await synthesizeSpeech(cleaned, engine)
    } catch (err) {
      isBusy.value = false
      throw err
    }

    // Another call landed while we were waiting for the network — abandon.
    if (token !== currentToken) {
      URL.revokeObjectURL(url)
      return
    }

    cleanupObjectUrl()
    currentObjectUrl = url
    audio.src = url
    try {
      await audio.play()
      isSpeaking.value = true
    } catch (err) {
      isSpeaking.value = false
      isBusy.value = false
      cleanupObjectUrl()
      throw err
    }
  }

  function stop(): void {
    currentToken++
    if (!audio.paused) {
      try { audio.pause() } catch { /* noop */ }
      audio.currentTime = 0
    }
    isSpeaking.value = false
    isBusy.value = false
    cleanupObjectUrl()
  }

  return { speak, stop, isSpeaking, isBusy }
}
