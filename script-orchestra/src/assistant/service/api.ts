/**
 * Assistant API Service
 */

const getBaseURL = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const backendHost = hostname === 'localhost' || hostname === '127.0.0.1'
    ? 'localhost'
    : hostname
  return `${protocol}//${backendHost}:50001/assistant/assistant`
}

const BASE_URL = getBaseURL()

export type ModelAlias = 'auto' | 'haiku' | 'sonnet' | 'opus'
export type Complexity = 'simple' | 'medium' | 'hard' | null

export interface ConversationSummary {
  id: string
  title: string
  model_alias: ModelAlias
  kb_enabled?: boolean
  pinned?: boolean
  archived?: boolean
  created_at: string
  updated_at: string
}

export interface Conversation extends ConversationSummary {
  system_prompt: string
  kb_enabled: boolean
  pinned: boolean
  archived: boolean
}

export interface Message {
  id: number
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  model: string | null
  complexity: Complexity
  input_tokens: number | null
  output_tokens: number | null
  created_at: string
  attachments?: AttachmentSummary[]
}

export interface AttachmentSummary {
  id: string
  kind: 'image' | 'document' | 'text'
  mime_type: string
  filename: string
  byte_size: number
}

export interface Attachment extends AttachmentSummary {
  conversation_id: string
  message_id: number | null
  sha256: string
  created_at: string
}

export interface ChatReply {
  message: Message
  model: string
  complexity: Complexity
  input_tokens: number | null
  output_tokens: number | null
}

export interface ModelsInfo {
  default: ModelAlias
  aliases: ModelAlias[]
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, init)
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ message: response.statusText }))
    throw new Error(errBody.message || `Request failed: ${response.status}`)
  }
  return response.json()
}

export const getModels = () => req<ModelsInfo>('/models')

export const listConversations = () =>
  req<ConversationSummary[]>('/conversations')

export const createConversation = (payload: {
  title?: string
  system_prompt?: string
  model_alias?: ModelAlias
}) => req<Conversation>('/conversations', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

export const getConversation = (id: string) =>
  req<Conversation>(`/conversations/${id}`)

export const updateConversation = (id: string, payload: {
  title?: string
  system_prompt?: string
  model_alias?: ModelAlias
  kb_enabled?: boolean
  pinned?: boolean
  archived?: boolean
}) => req<Conversation>(`/conversations/${id}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

export const deleteConversation = (id: string) =>
  req<{ message: string }>(`/conversations/${id}`, { method: 'DELETE' })

export const listMessages = (id: string) =>
  req<Message[]>(`/conversations/${id}/messages`)

export const editUserMessage = (convId: string, messageId: number, content: string) =>
  req<Message>(`/conversations/${convId}/messages/${messageId}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })

/**
 * Stream a fresh assistant reply for the current tail of a conversation.
 * No new user message is inserted (used after edit / retry).
 */
export async function streamRegenerate(
  id: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE_URL}/conversations/${id}/regenerate/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
  })
  if (!response.ok || !response.body) {
    const errBody = await response.json().catch(() => ({ message: response.statusText }))
    throw new Error(errBody.message || `Regenerate failed: ${response.status}`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const raw of parts) {
      const line = raw.split('\n').find(l => l.startsWith('data: '))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice('data: '.length)) as StreamEvent)
      } catch (err) {
        console.error('[assistant] failed to parse SSE payload', err)
      }
    }
  }
}

export const sendChat = (id: string, content: string, attachmentIds: string[] = []) =>
  req<ChatReply>(`/conversations/${id}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, attachment_ids: attachmentIds }),
  })

export async function uploadAttachment(
  convId: string,
  file: File,
): Promise<Attachment> {
  const form = new FormData()
  form.append('file', file, file.name)
  const response = await fetch(`${BASE_URL}/conversations/${convId}/attachments`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ message: response.statusText }))
    throw new Error(errBody.message || `Upload failed: ${response.status}`)
  }
  return response.json()
}

export function attachmentRawUrl(id: string): string {
  return `${BASE_URL.replace(/\/assistant\/assistant$/, '/assistant/assistant')}/attachments/${id}/raw`
}


// ── Usage stats ───────────────────────────────────────────

export interface UsageBucket {
  input: number
  output: number
  message_count: number
}

export interface ModelUsage extends UsageBucket {
  model: string
}

export interface UsageStats {
  conversation_count: number
  overall: UsageBucket
  today: UsageBucket
  last_7_days: UsageBucket
  by_model: ModelUsage[]
}

export const getUsageStats = () => req<UsageStats>('/stats/usage')


// ── Export ────────────────────────────────────────────────

export async function downloadExport(id: string, title: string): Promise<void> {
  const response = await fetch(`${BASE_URL}/conversations/${id}/export`)
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const safe = title.replace(/[^\w-]+/g, '_').replace(/^_+|_+$/g, '') || 'conversation'
  a.download = `${safe}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}


// ── Search ────────────────────────────────────────────────

export interface SearchHit {
  message_id: number
  conversation_id: string
  conversation_title: string
  role: 'user' | 'assistant'
  created_at: string
  model: string | null
  snippet: string
  score: number
}

export interface SearchResponse {
  query: string
  hits: SearchHit[]
}

export const searchMessages = (query: string, limit: number = 30) =>
  req<SearchResponse>(`/search?q=${encodeURIComponent(query)}&limit=${limit}`)


// ── Fork ──────────────────────────────────────────────────

export type ForkMode = 'up-to' | 'before'

export const forkConversation = (
  id: string,
  messageId: number,
  mode: ForkMode,
  title?: string,
) => req<Conversation>(`/conversations/${id}/fork`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message_id: messageId,
    mode,
    ...(title ? { title } : {}),
  }),
})


// ── Knowledge Base ────────────────────────────────────────

export interface KbSource {
  id: string
  name: string
  path: string
  enabled: number
  last_scanned_at: string | null
  file_count: number
  chunk_count: number
  created_at: string
}

export interface KbHit {
  chunk_id: number
  document_id: string
  source_id: string
  source_name: string
  relpath: string
  ordinal: number
  text: string
  score: number
}

export const listKbSources = () =>
  req<KbSource[]>('/kb/sources')

export const createKbSource = (name: string, path: string) =>
  req<KbSource>('/kb/sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, path }),
  })

export const updateKbSource = (id: string, payload: {
  name?: string
  enabled?: boolean
}) => req<KbSource>(`/kb/sources/${id}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

export const deleteKbSource = (id: string) =>
  req<{ message: string }>(`/kb/sources/${id}`, { method: 'DELETE' })

export interface KbRefreshResult {
  source_id: string
  added: number
  changed: number
  unchanged: number
  deleted: number
  file_count: number
  chunk_count: number
}

export const refreshKbSource = (id: string) =>
  req<KbRefreshResult>(`/kb/sources/${id}/refresh`, { method: 'POST' })


// ── Wake word ─────────────────────────────────────────────

export interface WakeStatus {
  running: boolean
  keyword: string
  threshold: number
  keywords_available: string[]
  last_error: string | null
}

export const getWakeStatus = () => req<WakeStatus>('/wake/status')

export const startWake = (payload: {
  keyword?: string
  threshold?: number
}) => req<WakeStatus>('/wake/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

export const stopWake = () =>
  req<WakeStatus>('/wake/stop', { method: 'POST' })

/**
 * SSE event payloads pushed by /chat/stream.
 */
export type StreamEvent =
  | { type: 'start'; model: string; complexity: Complexity; kb_hits?: KbHit[] }
  | { type: 'delta'; text: string }
  | {
      type: 'done'
      message: Message
      model: string
      complexity: Complexity
      input_tokens: number | null
      output_tokens: number | null
    }
  | { type: 'error'; message: string }

/**
 * POST to the streaming chat endpoint and invoke `onEvent` for each SSE
 * event as it arrives. Resolves after the stream closes.
 */
export async function streamChat(
  id: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  options: { attachmentIds?: string[]; signal?: AbortSignal } = {},
): Promise<void> {
  const response = await fetch(`${BASE_URL}/conversations/${id}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      attachment_ids: options.attachmentIds ?? [],
    }),
    signal: options.signal,
  })

  if (!response.ok || !response.body) {
    const errBody = await response.json().catch(() => ({ message: response.statusText }))
    throw new Error(errBody.message || `Stream failed: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE events are separated by a blank line ("\n\n").
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const raw of parts) {
      const line = raw.split('\n').find(l => l.startsWith('data: '))
      if (!line) continue
      const payload = line.slice('data: '.length)
      try {
        const evt = JSON.parse(payload) as StreamEvent
        onEvent(evt)
      } catch (err) {
        console.error('[assistant] failed to parse SSE payload', payload, err)
      }
    }
  }
}


// ── Voice ─────────────────────────────────────────────────

export type WhisperModel = 'medium' | 'large-v3'
export type TTSEngine = 'say' | 'kokoro'

export interface VoiceConfig {
  whisper_model: WhisperModel
  asr_language: string
  compute_type: string
  tts_engine: TTSEngine
  whisper_models: Record<string, string>
  tts_engines: Record<string, string>
}

export interface TranscribeResult {
  text: string
  language: string
  language_probability: number
  duration: number
  segments: Array<{ id: number; start: number; end: number; text: string }>
  whisper_model: string
}

export const getVoiceConfig = () => req<VoiceConfig>('/voice/config')

export const updateVoiceConfig = (payload: Partial<{
  whisper_model: WhisperModel
  tts_engine: TTSEngine
  asr_language: string
  compute_type: string
}>) => req<VoiceConfig>('/voice/config', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

/**
 * Upload an audio blob and return the transcription. Uses multipart
 * form-data so a filename hint can travel with the payload.
 */
export async function transcribeAudio(
  blob: Blob,
  filename: string = 'clip.webm',
  language?: string,
): Promise<TranscribeResult> {
  const form = new FormData()
  form.append('audio', blob, filename)
  if (language) form.append('language', language)

  const response = await fetch(`${BASE_URL}/voice/transcribe`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ message: response.statusText }))
    throw new Error(errBody.message || `Transcribe failed: ${response.status}`)
  }
  return response.json()
}

/**
 * Synthesize `text` to speech and return an object URL you can attach to
 * an <audio> element. Caller should revoke the URL when done.
 */
export async function synthesizeSpeech(
  text: string,
  engine?: TTSEngine,
): Promise<string> {
  const response = await fetch(`${BASE_URL}/voice/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(engine ? { text, engine } : { text }),
  })
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ message: response.statusText }))
    throw new Error(errBody.message || `TTS failed: ${response.status}`)
  }
  const audioBlob = await response.blob()
  return URL.createObjectURL(audioBlob)
}
