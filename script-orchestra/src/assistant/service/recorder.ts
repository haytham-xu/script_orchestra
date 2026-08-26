/**
 * useRecorder — a tiny wrapper around MediaRecorder for press-and-hold
 * or click-to-record patterns. Produces a single Blob when stopped.
 *
 * Usage:
 *   const rec = useRecorder()
 *   await rec.start()
 *   const blob = await rec.stop()  // resolves with the audio blob
 */
import { ref } from 'vue'

export interface RecorderState {
  isRecording: boolean
  isSupported: boolean
  mimeType: string | null
}

function pickMimeType(): string | null {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ]
  for (const t of candidates) {
    if (typeof MediaRecorder !== 'undefined'
        && MediaRecorder.isTypeSupported
        && MediaRecorder.isTypeSupported(t)) {
      return t
    }
  }
  return null
}

export function useRecorder() {
  const isRecording = ref(false)
  const isSupported = ref(
    typeof navigator !== 'undefined'
    && !!navigator.mediaDevices?.getUserMedia
    && typeof MediaRecorder !== 'undefined',
  )
  const error = ref<string | null>(null)

  let mediaRecorder: MediaRecorder | null = null
  let mediaStream: MediaStream | null = null
  let chunks: BlobPart[] = []
  let stopPromise: Promise<Blob> | null = null

  async function start(): Promise<void> {
    if (!isSupported.value) {
      throw new Error('MediaRecorder is not supported in this browser')
    }
    if (isRecording.value) return
    error.value = null
    chunks = []

    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mimeType = pickMimeType() || undefined
    mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : {})

    mediaRecorder.ondataavailable = (evt) => {
      if (evt.data && evt.data.size > 0) chunks.push(evt.data)
    }

    stopPromise = new Promise<Blob>((resolve, reject) => {
      if (!mediaRecorder) {
        reject(new Error('MediaRecorder not initialized'))
        return
      }
      mediaRecorder.onstop = () => {
        try {
          const type = mediaRecorder?.mimeType || 'audio/webm'
          const blob = new Blob(chunks, { type })
          resolve(blob)
        } catch (err) {
          reject(err)
        } finally {
          mediaStream?.getTracks().forEach(t => t.stop())
          mediaStream = null
          mediaRecorder = null
          chunks = []
        }
      }
      mediaRecorder.onerror = (e) => {
        reject(new Error(`MediaRecorder error: ${(e as any).error?.message || 'unknown'}`))
      }
    })

    mediaRecorder.start()
    isRecording.value = true
  }

  async function stop(): Promise<Blob | null> {
    if (!isRecording.value || !mediaRecorder) return null
    const p = stopPromise
    isRecording.value = false
    try {
      mediaRecorder.stop()
    } catch (err: any) {
      error.value = err?.message || String(err)
    }
    return p ? await p : null
  }

  function cancel(): void {
    if (!isRecording.value || !mediaRecorder) return
    isRecording.value = false
    try { mediaRecorder.stop() } catch { /* ignored */ }
    // Discard: don't await stopPromise result
    stopPromise = null
    chunks = []
  }

  return { isRecording, isSupported, error, start, stop, cancel }
}
