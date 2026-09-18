import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { KNOWLEDGE_VAULT_ENDPOINT } from '@/basic/Constants'
import type {
  RawFragment, KnowledgeVaultSettings,
  Label, FragmentGroup, ContentBlock,
} from './Model'

const B = KNOWLEDGE_VAULT_ENDPOINT

export async function getFragments(ungroupedOnly = false, archivedOnly = false): Promise<RawFragment[]> {
  const params: Record<string, number> = {}
  if (ungroupedOnly) params.ungrouped_only = 1
  if (archivedOnly) params.archived = 1
  return (await getRequest<{ fragments: RawFragment[] }>(`${B}/fragments`, params)).fragments
}
export async function getAllFragments(archivedOnly = false): Promise<RawFragment[]> {
  const params = archivedOnly ? { archived: 1 } : {}
  return (await getRequest<{ fragments: RawFragment[] }>(`${B}/fragments`, params)).fragments
}
export async function archiveFragment(id: number): Promise<RawFragment> {
  return (await putRequest<{ fragment: RawFragment }>(`${B}/fragments/${id}/archive`, {}, {})).fragment
}
export async function unarchiveFragment(id: number): Promise<RawFragment> {
  return (await deleteRequest<{ fragment: RawFragment }>(`${B}/fragments/${id}/archive`)).fragment
}
export async function addFragment(
  blocks: ContentBlock[], note = '', labelIds: number[] = [], header = ''
): Promise<RawFragment> {
  return (await postRequest(`${B}/fragments`, {}, { blocks, note, label_ids: labelIds, header }) as { fragment: RawFragment }).fragment
}
export async function updateFragment(
  id: number,
  patch: { blocks?: ContentBlock[]; note?: string; label_ids?: number[]; header?: string }
): Promise<RawFragment> {
  return (await putRequest<{ fragment: RawFragment }>(`${B}/fragments/${id}`, {}, patch)).fragment
}
export async function deleteFragment(id: number) {
  return deleteRequest(`${B}/fragments/${id}`)
}
export async function getLabels(): Promise<Label[]> {
  return (await getRequest<{ labels: Label[] }>(`${B}/labels`)).labels
}
export async function createLabel(name: string, color = '#8e8e93'): Promise<Label> {
  return (await postRequest(`${B}/labels`, {}, { name, color }) as { label: Label }).label
}
export async function updateLabel(id: number, name: string, color: string): Promise<Label> {
  return (await putRequest<{ label: Label }>(`${B}/labels/${id}`, {}, { name, color })).label
}
export async function deleteLabel(id: number) {
  return deleteRequest(`${B}/labels/${id}`)
}
export async function search(q: string, topK = 10): Promise<RawFragment[]> {
  return (await getRequest<{ results: RawFragment[] }>(`${B}/query`, { q, top_k: topK })).results
}
export async function reindexAll(): Promise<{ message: string }> {
  return await postRequest(`${B}/query/reindex`, {}, {}) as { message: string }
}
export async function getReindexStatus(): Promise<{ running: boolean; total: number; indexed: number }> {
  return getRequest(`${B}/query/reindex/status`)
}
export async function getSettings(): Promise<KnowledgeVaultSettings> {
  return (await getRequest<{ settings: KnowledgeVaultSettings }>(`${B}/settings`)).settings
}
export async function updateSettings(patch: Partial<KnowledgeVaultSettings>): Promise<KnowledgeVaultSettings> {
  return (await putRequest<{ settings: KnowledgeVaultSettings }>(`${B}/settings`, {}, patch)).settings
}

// ---- Fragment Groups --------------------------------------------------

export async function getGroups(): Promise<FragmentGroup[]> {
  return (await getRequest<{ groups: FragmentGroup[] }>(`${B}/fragment-groups`)).groups
}
export async function createGroup(name: string, note = '', parentId?: number | null): Promise<FragmentGroup> {
  return (await postRequest(`${B}/fragment-groups`, {}, { name, note, parent_id: parentId ?? null }) as { group: FragmentGroup }).group
}
export async function updateGroup(id: number, patch: { name?: string; note?: string; parent_id?: number | null }): Promise<FragmentGroup> {
  return (await putRequest<{ group: FragmentGroup }>(`${B}/fragment-groups/${id}`, {}, patch)).group
}
export async function deleteGroup(id: number): Promise<void> {
  await deleteRequest(`${B}/fragment-groups/${id}`)
}
export async function setGroupMembers(groupId: number, fragmentIds: number[]): Promise<number[]> {
  return (await putRequest<{ fragment_ids: number[] }>(`${B}/fragment-groups/${groupId}/members`, {}, { fragment_ids: fragmentIds })).fragment_ids
}
export async function getGroupMembers(groupId: number): Promise<number[]> {
  return (await getRequest<{ fragment_ids: number[] }>(`${B}/fragment-groups/${groupId}/members`)).fragment_ids
}
