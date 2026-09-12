export interface RawFragment {
  id: number
  content: string
  note: string
  raw_text: string
  kind: string
  created_at: string
  archived: number
  last_accessed: string | null
  label_ids: number[]
  freshness: 'fresh' | 'aging' | 'stale'
  score?: number
}

export interface Label {
  id: number
  name: string
  color: string
}

export interface AnalyzedFragment {
  content: string
  note: string
  kind: string
  _keep?: boolean   // client-side selection in the preview
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface KnowledgeVaultSettings {
  ai_model: string
}
