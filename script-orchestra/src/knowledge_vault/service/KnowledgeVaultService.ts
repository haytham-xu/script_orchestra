import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { KNOWLEDGE_VAULT_ENDPOINT } from '@/basic/Constants'
import type {
  RawFragment, KnowledgeVaultSettings,
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
export async function batchChat(
  messages: { role: 'user' | 'assistant'; content: string }[],
  currentFragments: AnalyzedFragment[],
): Promise<{ reply: string; fragments: AnalyzedFragment[]; suggested_labels: string[] }> {
  return await postRequest(`${B}/fragments/batch-chat`, {}, {
    messages, current_fragments: currentFragments,
  }) as { reply: string; fragments: AnalyzedFragment[]; suggested_labels: string[] }
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
// Duplicate detection (on-demand). Vector pairs are zero-cost; ai-check spends tokens.
export interface DupFrag { id: number; content: string; note: string; kind: string }
export interface DupPair { a: DupFrag; b: DupFrag; sim: number }
export interface DuplicatesResult { confident: DupPair[]; fuzzy: DupPair[] }
export async function findDuplicates(): Promise<DuplicatesResult> {
  return await getRequest<DuplicatesResult>(`${B}/duplicates`)
}
export async function aiCheckDuplicates(pairs: [number, number][]): Promise<[number, number][]> {
  return (await postRequest(`${B}/duplicates/ai-check`, {}, { pairs }) as { duplicates: [number, number][] }).duplicates
}
export async function resolveDuplicate(keepId: number, dropId: number): Promise<DuplicatesResult> {
  return await postRequest(`${B}/duplicates/resolve`, {}, { keep_id: keepId, drop_id: dropId }) as DuplicatesResult
}
export async function getSettings(): Promise<KnowledgeVaultSettings> {
  return (await getRequest<{ settings: KnowledgeVaultSettings }>(`${B}/settings`)).settings
}
export async function updateSettings(patch: Partial<KnowledgeVaultSettings>): Promise<KnowledgeVaultSettings> {
  return (await putRequest<{ settings: KnowledgeVaultSettings }>(`${B}/settings`, {}, patch)).settings
}
