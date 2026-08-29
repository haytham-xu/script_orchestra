import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { KNOWLEDGE_VAULT_ENDPOINT } from '@/basic/Constants'
import type {
  RawFragment, KnowledgeNode, KnowledgeEdge, KnowledgeVaultSettings, BuildStatus,
  Label, AnalyzedFragment,
} from './Model'

const B = KNOWLEDGE_VAULT_ENDPOINT

export async function getFragments(): Promise<RawFragment[]> {
  return (await getRequest<{ fragments: RawFragment[] }>(`${B}/fragments`)).fragments
}
export async function addFragment(content: string, note = '', labelIds: number[] = []): Promise<RawFragment> {
  return (await postRequest(`${B}/fragments`, {}, { content, note, label_ids: labelIds }) as { fragment: RawFragment }).fragment
}
export async function updateFragment(id: number, patch: { content?: string; note?: string; label_ids?: number[] }): Promise<RawFragment> {
  return (await putRequest<{ fragment: RawFragment }>(`${B}/fragments/${id}`, {}, patch)).fragment
}
export async function deleteFragment(id: number) {
  return deleteRequest(`${B}/fragments/${id}`)
}
export async function batchAnalyze(rawText: string): Promise<AnalyzedFragment[]> {
  return (await postRequest(`${B}/fragments/batch-analyze`, {}, { raw_text: rawText }) as { fragments: AnalyzedFragment[] }).fragments
}
export async function batchCommit(fragments: AnalyzedFragment[], labelIds: number[] = []): Promise<number> {
  return (await postRequest(`${B}/fragments/batch`, {}, { fragments, label_ids: labelIds }) as { count: number }).count
}
export async function getLabels(): Promise<Label[]> {
  return (await getRequest<{ labels: Label[] }>(`${B}/labels`)).labels
}
export async function createLabel(name: string, color = '#8e8e93'): Promise<Label> {
  return (await postRequest(`${B}/labels`, {}, { name, color }) as { label: Label }).label
}
export async function deleteLabel(id: number) {
  return deleteRequest(`${B}/labels/${id}`)
}
export async function search(q: string, topK = 10): Promise<RawFragment[]> {
  return (await getRequest<{ results: RawFragment[] }>(`${B}/query`, { q, top_k: topK })).results
}
export async function aiQuery(q: string): Promise<{ answer: string; used: RawFragment[] }> {
  return await postRequest(`${B}/query/ai`, {}, { q }) as { answer: string; used: RawFragment[] }
}
export async function build(useAi = true): Promise<BuildStatus> {
  return await postRequest(`${B}/build`, {}, { use_ai: useAi }) as BuildStatus
}
export async function getBuildStatus(): Promise<BuildStatus> {
  return await getRequest<BuildStatus>(`${B}/build/status`)
}
export async function getNodes(): Promise<KnowledgeNode[]> {
  return (await getRequest<{ nodes: KnowledgeNode[] }>(`${B}/nodes`)).nodes
}
export async function getEdges(): Promise<KnowledgeEdge[]> {
  return (await getRequest<{ edges: KnowledgeEdge[] }>(`${B}/edges`)).edges
}
export async function getStale(): Promise<KnowledgeNode[]> {
  return (await getRequest<{ stale: KnowledgeNode[] }>(`${B}/lifecycle/stale`)).stale
}
export async function getSettings(): Promise<KnowledgeVaultSettings> {
  return (await getRequest<{ settings: KnowledgeVaultSettings }>(`${B}/settings`)).settings
}
export async function updateSettings(patch: Partial<KnowledgeVaultSettings>): Promise<KnowledgeVaultSettings> {
  return (await putRequest<{ settings: KnowledgeVaultSettings }>(`${B}/settings`, {}, patch)).settings
}
