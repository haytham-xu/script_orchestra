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

export interface KnowledgeNode {
  id: number
  title: string
  summary: string
  kind: string
  fragment_ids: number[]
  label_ids?: number[]   // union of source fragments' labels (aggregated by /nodes)
  freshness: 'fresh' | 'aging' | 'stale'
  updated_at: string
}

export interface KnowledgeEdge {
  id: number
  source_id: number
  target_id: number
  relation: string
  weight: number
}

export interface KnowledgeVaultSettings {
  auto_build: boolean
  embed_model: string
  relate_top_k: number
  stale_days: number
  link_check_enabled: boolean
}

export interface BuildStatus {
  running: boolean
  phase: string
  nodes: number
  edges: number
  last_run: string | null
}
