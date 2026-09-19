export type BlockType = 'text' | 'code' | 'url' | 'long'

export interface ContentBlock {
  type: BlockType
  body: string
  lang?: string   // for code blocks
  subtitle?: string  // optional one-line description for any block
}

export interface RawFragment {
  id: number
  blocks: ContentBlock[]
  note: string
  raw_text: string
  kind: string
  created_at: string
  archived: number
  last_accessed: string | null
  header?: string
  label_ids: number[]
  freshness: 'fresh' | 'aging' | 'stale'
  group_id?: number | null
  score?: number
}

export interface Label {
  id: number
  name: string
  color: string
}

export interface KnowledgeVaultSettings {
  ai_model: string
  embed_model: string
}

export interface FragmentGroup {
  id: number
  name: string
  note: string
  parent_id: number | null
  created_at: string
  label_ids: number[]
  children?: FragmentGroup[]
  fragments?: RawFragment[]
}

/** Returns a one-line display summary for a fragment (header or first block text) */
export function fragmentSummary(f: RawFragment): string {
  if (f.header) return f.header
  const first = f.blocks?.[0]
  if (!first) return '(empty)'
  const body = first.body || ''
  return body.length > 80 ? body.slice(0, 80) + '…' : body
}
