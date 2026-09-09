import { getRequest, putRequest, patchRequest } from '@/basic/RequestService'
import { DASHBOARD_ENDPOINT } from '@/basic/Constants'

const B = DASHBOARD_ENDPOINT

// A layout item is either a tool (by code-defined key) or a folder of tool keys.
export interface ToolItem { type: 'tool'; key: string }
export interface FolderItem { type: 'folder'; id: string; name: string; keys: string[] }
export type LayoutItem = ToolItem | FolderItem

export async function getLayout(): Promise<{ items: LayoutItem[] }> {
  return (await getRequest<{ layout: { items: LayoutItem[] } }>(`${B}/layout`)).layout
}

export async function saveLayout(items: LayoutItem[]): Promise<{ items: LayoutItem[] }> {
  return (await putRequest<{ layout: { items: LayoutItem[] } }>(`${B}/layout`, {}, { items })).layout
}

export type ToolStatus = 'normal' | 'needs_improvement' | 'pending_verification' | 'deprecated' | 'in_progress'

export interface ToolMeta {
  status?: ToolStatus
  last_opened?: string
  comment?: string
}

export async function getToolMeta(): Promise<Record<string, ToolMeta>> {
  return (await getRequest<{ meta: Record<string, ToolMeta> }>(`${B}/tool-meta`)).meta
}

export async function patchToolMeta(key: string, patch: Partial<ToolMeta>): Promise<Record<string, ToolMeta>> {
  return (await patchRequest<{ meta: Record<string, ToolMeta> }>(`${B}/tool-meta/${key}`, {}, patch)).meta
}
