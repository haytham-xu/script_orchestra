import { getRequest, postRequest } from '@/basic/RequestService'
import { FILE_DUPLICATE_ENDPOINT } from '@/basic/Constants'
import type { Settings, GroupsResponse, Stats } from './Model'

const BASE = FILE_DUPLICATE_ENDPOINT

export class FileDuplicateService {
  static getSettings(): Promise<Settings> {
    return getRequest(`${BASE}/settings`)
  }

  static saveSettings(settings: Partial<Settings>): Promise<{ ok: boolean }> {
    return postRequest(`${BASE}/settings`, {}, settings)
  }

  static getStatus(): Promise<any> {
    return getRequest(`${BASE}/status`)
  }

  static getStats(): Promise<Stats> {
    return getRequest(`${BASE}/stats`)
  }

  static startPhase1(): Promise<{ ok: boolean }> {
    return postRequest(`${BASE}/phase1/index`, {}, {})
  }

  static stopPhase1(): Promise<{ ok: boolean }> {
    return postRequest(`${BASE}/phase1/stop`, {}, {})
  }

  static startPhase2(): Promise<{ ok: boolean }> {
    return postRequest(`${BASE}/phase2/hash`, {}, {})
  }

  static stopPhase2(): Promise<{ ok: boolean }> {
    return postRequest(`${BASE}/phase2/stop`, {}, {})
  }

  static startPhase3(): Promise<{ ok: boolean }> {
    return postRequest(`${BASE}/phase3/group`, {}, {})
  }

  static getGroups(params: {
    page?: number
    page_size?: number
    sort_by?: string
    sort_order?: string
    root_id?: number | null
  }): Promise<GroupsResponse> {
    const q = new URLSearchParams()
    if (params.page) q.set('page', String(params.page))
    if (params.page_size) q.set('page_size', String(params.page_size))
    if (params.sort_by) q.set('sort_by', params.sort_by)
    if (params.sort_order) q.set('sort_order', params.sort_order)
    if (params.root_id != null) q.set('root_id', String(params.root_id))
    return getRequest(`${BASE}/groups?${q.toString()}`)
  }

  static moveToTrash(fileIds: number[]): Promise<{ moved: any[]; errors: any[] }> {
    return postRequest(`${BASE}/move-to-trash`, {}, { file_ids: fileIds })
  }

  static resolveGroup(keepIds: number[], trashIds: number[]): Promise<{ moved: any[]; errors: any[] }> {
    return postRequest(`${BASE}/resolve-group`, {}, { keep_ids: keepIds, trash_ids: trashIds })
  }
}
