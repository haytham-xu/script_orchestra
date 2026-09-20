import { getRequest, postRequest, putRequest, patchRequest, deleteRequest } from '@/basic/RequestService'
import { BROWSER_AGENT_ENDPOINT } from '@/basic/Constants'
import type {
  BrowserTask,
  BrowserAgentSettings,
  TabArchiveArchiveResult,
  TabArchiveGroup,
  TabArchiveLabel,
  TabArchiveRestoreResult,
  TabArchiveSortBy,
  TabArchiveSortOrder,
  TabArchiveSnapshot,
  TabArchiveRecord,
  TabArchiveReplaceUrlResult,
  ShelfItem,
} from './Model'

export async function getTasks(): Promise<BrowserTask[]> {
  const res = await getRequest<{ tasks: BrowserTask[] }>(`${BROWSER_AGENT_ENDPOINT}/tasks`)
  return res.tasks
}

export async function retryTask(id: number) {
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/tasks/${id}/retry`, {}, {})
}

export async function deleteTask(id: number) {
  return deleteRequest(`${BROWSER_AGENT_ENDPOINT}/tasks/${id}`)
}

export async function getSettings(): Promise<BrowserAgentSettings> {
  const res = await getRequest<{ settings: BrowserAgentSettings }>(
    `${BROWSER_AGENT_ENDPOINT}/settings`)
  return res.settings
}

export async function updateSettings(
  patch: Partial<BrowserAgentSettings>,
): Promise<BrowserAgentSettings> {
  const res = await putRequest<{ settings: BrowserAgentSettings }>(
    `${BROWSER_AGENT_ENDPOINT}/settings`, {}, patch)
  return res.settings
}

// --- Tab dedup tool -------------------------------------------------------

export interface TabInfo {
  id: number
  title: string
  url: string
  windowId: number
  active: boolean
  pinned: boolean
  favIconUrl: string
}

export async function listTabs(): Promise<TabInfo[]> {
  const res = await postRequest<{ tabs: TabInfo[] }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-dedup/list-tabs`, {}, {})
  return res.tabs || []
}

export interface CloseTabsResult {
  closed: number
  closed_ids?: number[]
  failed?: Array<{ tab_id: number; error: string }>
}

export async function closeTabs(tabIds: number[]): Promise<CloseTabsResult> {
  return postRequest<CloseTabsResult>(
    `${BROWSER_AGENT_ENDPOINT}/tab-dedup/close-tabs`, {}, { tab_ids: tabIds })
}

export async function mergeTabs(): Promise<{ moved: number; windowId: number | null }> {
  return postRequest<{ moved: number; windowId: number | null }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-dedup/merge-tabs`, {}, {})
}

export async function groupTabsByDomain(): Promise<{ grouped: number; windowId: number | null }> {
  return postRequest<{ grouped: number; windowId: number | null }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-dedup/group-tabs`, {}, {})
}

// --- Tab archive ----------------------------------------------------------

export async function tabArchiveSnapshot(params: {
  q?: string
  scope?: 'all' | 'live' | 'archive'
  include_live_urls?: boolean
  sort_by?: TabArchiveSortBy
  sort_order?: TabArchiveSortOrder
} = {}): Promise<TabArchiveSnapshot> {
  return getRequest<TabArchiveSnapshot>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/snapshot`, params)
}

export async function tabArchiveSelected(tabIds: number[]): Promise<TabArchiveArchiveResult> {
  return postRequest<TabArchiveArchiveResult>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/archive-selected`, {}, {
      tab_ids: tabIds,
    })
}

export async function tabArchiveRestore(
  recordIds: number[],
  destination: 'new_window' | 'current_window',
): Promise<TabArchiveRestoreResult> {
  return postRequest<TabArchiveRestoreResult>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/restore`, {}, {
      record_ids: recordIds,
      destination,
    })
}

export async function tabArchiveUpdateRecord(
  recordId: number,
  patch: { title?: string; comment?: string; eternal?: boolean },
): Promise<TabArchiveRecord> {
  const res = await patchRequest<{ record: TabArchiveRecord }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/records/${recordId}`,
    {},
    patch,
  )
  return res.record
}

export async function tabArchiveDeleteRecord(recordId: number): Promise<{ deleted: boolean }> {
  return deleteRequest<{ deleted: boolean }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/records/${recordId}`)
}

export async function tabArchiveSetRecordLabels(
  recordId: number,
  labelIds: number[],
): Promise<TabArchiveRecord> {
  const res = await putRequest<{ record: TabArchiveRecord }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/records/${recordId}/labels`,
    {},
    { label_ids: labelIds },
  )
  return res.record
}

export async function tabArchiveListLabels(): Promise<TabArchiveLabel[]> {
  const res = await getRequest<{ labels: TabArchiveLabel[] }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/labels`)
  return res.labels || []
}

export async function tabArchiveCreateLabel(name: string): Promise<TabArchiveLabel> {
  const res = await postRequest<{ label: TabArchiveLabel }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/labels`,
    {},
    { name },
  )
  return res.label
}

export async function tabArchiveDeleteLabel(labelId: number): Promise<{ deleted: boolean }> {
  return deleteRequest<{ deleted: boolean }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/labels/${labelId}`)
}

// --- Tab archive groups ---------------------------------------------------

export type GroupScope = 'live' | 'archive' | 'shelf'

export async function tabArchiveGetGroupTree(scope: GroupScope = 'archive'): Promise<TabArchiveGroup[]> {
  const res = await getRequest<{ tree: TabArchiveGroup[] }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/group-tree`, { scope })
  return res.tree || []
}

export async function tabArchiveListGroups(
  parentId?: number | null,
  scope: GroupScope = 'archive',
): Promise<TabArchiveGroup[]> {
  const params: Record<string, unknown> = { scope }
  if (parentId != null) params.parent_id = parentId
  const res = await getRequest<{ groups: TabArchiveGroup[] }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/groups`, params)
  return res.groups || []
}

export async function tabArchiveCreateGroup(
  name: string,
  parentId?: number | null,
  scope: GroupScope = 'archive',
  displayOrder?: number,
): Promise<TabArchiveGroup> {
  const res = await postRequest<{ group: TabArchiveGroup }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/groups`, {}, {
      name,
      parent_id: parentId ?? null,
      scope,
      display_order: displayOrder,
    })
  return res.group
}

export async function tabArchiveRenameGroup(groupId: number, name: string, scope: GroupScope): Promise<TabArchiveGroup> {
  const res = await patchRequest<{ group: TabArchiveGroup }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/groups/${groupId}`, {}, { name, scope })
  return res.group
}

export async function tabArchiveMoveGroup(
  groupId: number,
  newParentId: number | null,
  newDisplayOrder: number,
  scope: GroupScope,
): Promise<TabArchiveGroup> {
  const res = await patchRequest<{ group: TabArchiveGroup }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/groups/${groupId}`, {}, {
      new_parent_id: newParentId,
      new_display_order: newDisplayOrder,
      scope,
    })
  return res.group
}

export async function tabArchiveDeleteGroup(groupId: number, scope: GroupScope): Promise<{ deleted: boolean }> {
  return deleteRequest<{ deleted: boolean }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/groups/${groupId}?scope=${scope}`)
}

export async function tabArchiveSetRecordGroup(
  recordId: number,
  groupId: number | null,
): Promise<TabArchiveRecord> {
  const res = await patchRequest<{ record: TabArchiveRecord }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/records/${recordId}/group`, {}, { group_id: groupId })
  return res.record
}

export async function tabArchiveReorderRecord(recordId: number, displayOrder: number): Promise<void> {
  await postRequest(`${BROWSER_AGENT_ENDPOINT}/tab-archive/records/reorder`, {}, { record_id: recordId, display_order: displayOrder })
}

export async function tabArchiveSetLiveTabsGroup(
  tabIds: number[],
  groupId: number | null,
): Promise<{ updated: number }> {
  return postRequest<{ updated: number }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/set-group`, {}, { tab_ids: tabIds, group_id: groupId })
}

export async function tabArchiveSetLiveTabOrder(
  tabId: number,
  groupId: number | null,
  displayOrder: number,
): Promise<{ ok: boolean }> {
  return patchRequest<{ ok: boolean }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/${tabId}/order`, {}, {
      group_id: groupId,
      display_order: displayOrder,
    })
}

export async function tabArchiveBatchSetLiveTabOrders(
  items: Array<{ tab_id: number; group_id: number | null; display_order: number }>,
): Promise<{ ok: boolean; updated: number }> {
  return patchRequest<{ ok: boolean; updated: number }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/batch-order`, {}, { items })
}

export async function tabArchiveSetLiveTabCustomHeader(
  tabId: number,
  customHeader: string | null,
): Promise<{ ok: boolean }> {
  return patchRequest<{ ok: boolean }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/${tabId}/custom-header`, {}, { custom_header: customHeader })
}

export async function tabArchiveRecordActivations(
  activations: Array<{ url: string; activation_count: number; last_activated_at: string }>,
): Promise<void> {
  await postRequest(`${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/record-activations`, {}, { activations })
}

export async function tabArchiveGroupAsWindow(
  windowId: number,
  groupName: string,
): Promise<{ group: TabArchiveGroup; count: number }> {
  return postRequest<{ group: TabArchiveGroup; count: number }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/group-as-window`, {}, { window_id: windowId, group_name: groupName })
}

// --- Shelf ---------------------------------------------------------------

export async function tabArchiveGetShelf(): Promise<{ items: ShelfItem[]; group_tree: TabArchiveGroup[] }> {
  return getRequest(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf`)
}

export async function tabArchiveCreateShelfItem(payload: {
  url: string
  title?: string
  favicon_url?: string
  group_id?: number | null
  bookmark_id?: string
  display_order?: number
}): Promise<ShelfItem> {
  const res = await postRequest<{ item: ShelfItem }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/items`, {}, payload)
  return res.item
}

export async function tabArchiveDeleteShelfItem(itemId: number): Promise<{ deleted: boolean }> {
  return deleteRequest<{ deleted: boolean }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/items/${itemId}`)
}

export async function tabArchiveSetShelfItemOrder(itemId: number, displayOrder: number): Promise<{ ok: boolean }> {
  return patchRequest<{ ok: boolean }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/items/${itemId}`, {}, { display_order: displayOrder })
}

export async function tabArchiveSetShelfItemGroup(itemId: number, groupId: number | null): Promise<{ ok: boolean }> {
  return patchRequest<{ ok: boolean }>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/items/${itemId}`, {}, { group_id: groupId })
}

export async function tabArchiveOpenShelfItem(itemId: number, destination: 'current_window' | 'new_window' = 'current_window'): Promise<{ ok: boolean; tab_id?: number; error?: string }> {
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/items/${itemId}/open`, {}, { destination })
}

export async function tabArchiveSyncShelfFromBookmarks(
  bookmarkNodes: Array<{ id: string; url?: string; title?: string; parentId?: string; index?: number }>,
): Promise<{ upserted: number }> {
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/sync-from-bookmarks`, {}, { bookmark_nodes: bookmarkNodes })
}

export async function tabArchiveExportBookmarks(): Promise<Array<{ bookmark_id: string | null; url: string; title: string }>> {
  const res = await getRequest<{ items: Array<{ bookmark_id: string | null; url: string; title: string }> }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/export-bookmarks`)
  return res.items || []
}

export async function tabArchiveSyncShelfFromBrowserBookmarks(): Promise<{ upserted?: number; error?: string }> {
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/sync-from-browser-bookmarks`, {}, {})
}

export async function tabArchiveExportShelfToBrowserBookmarks(): Promise<{ ok?: boolean; error?: string }> {
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/tab-archive/shelf/export-to-browser-bookmarks`, {}, {})
}

export async function tabArchiveMoveLiveTab(
  tabId: number,
  index: number,
  windowId?: number,
): Promise<{ ok: boolean; tab_id?: number; new_index?: number; error?: string }> {
  const payload: Record<string, number> = { tab_id: tabId, index }
  if (windowId !== undefined) payload.window_id = windowId
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/move-tab`, {}, payload)
}

export async function tabArchiveSortByGroup(windowId?: number): Promise<{ sorted: number; windowId: number }> {
  return postRequest<{ sorted: number; windowId: number }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/sort-by-group`, {}, { window_id: windowId ?? null })
}

export async function tabArchiveSplitByGroups(): Promise<{ windows_created: number }> {
  return postRequest<{ windows_created: number }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/live-tabs/split-by-groups`, {}, {})
}

export async function tabArchiveReplaceUrl(payload: {
  find: string
  replace: string
  record_ids?: number[]
  preview: boolean
}): Promise<TabArchiveReplaceUrlResult> {
  return postRequest<TabArchiveReplaceUrlResult>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/records/replace-url`,
    {},
    payload,
  )
}

export interface SendTabsResult {
  message: string
  added: number
  skipped: number
  unmatched: number
}

export async function sendTabsToDownloadQueue(urls: string[]): Promise<SendTabsResult> {
  return postRequest<SendTabsResult>(
    `${BROWSER_AGENT_ENDPOINT}/tabs`, {}, { tabs: urls })
}

// --- Download SSMH ------------------------------------------------------

export interface SSMHCandidate { url: string; aid: string }
export interface SSMHScanResult {
  candidates: SSMHCandidate[]
  total_tabs: number
}

export interface SSMHItem {
  url: string
  status: string   // pending | fetching_source | fetching_download_page | downloading | done | error | unmatched_download_domain
  message: string
  filename: string
  download_url: string
  final_path: string
  bytes_downloaded: number
  bytes_total: number
  speed_bps: number
  progress_percent: number
}

export interface SSMHStatus {
  running: boolean
  total: number
  done: number
  items: SSMHItem[]
}

export async function ssmhScan(): Promise<SSMHScanResult> {
  return postRequest<SSMHScanResult>(
    `${BROWSER_AGENT_ENDPOINT}/download-ssmh/scan`, {}, {})
}

export async function ssmhExecute(urls: string[]): Promise<{ message: string; total: number }> {
  return postRequest<{ message: string; total: number }>(
    `${BROWSER_AGENT_ENDPOINT}/download-ssmh/execute`, {}, { urls })
}

export async function ssmhStatus(): Promise<SSMHStatus> {
  return getRequest<SSMHStatus>(`${BROWSER_AGENT_ENDPOINT}/download-ssmh/status`)
}

// --- Download JM ----------------------------------------------------------

export interface JMCandidate { url: string; album_id: string }
export interface JMScanResult {
  candidates: JMCandidate[]
  total_tabs: number
}

export interface JMItem {
  url: string
  status: string
  message: string
  filename: string
  final_path: string
  chapter_label?: string
  bytes_downloaded: number
  bytes_total: number
  speed_bps: number
  progress_percent: number
}

export interface JMCaptchaPending {
  item_index: number
  image_base64: string
  attempts_left: number
}

export interface JMStatus {
  running: boolean
  total: number
  done: number
  items: JMItem[]
  captcha_pending: JMCaptchaPending | null
}

export interface JMAuthCheck {
  cookie_count?: number
  cookie_names?: string[]
  status?: number
  final_path?: string
  has_logout_marker?: boolean
  still_looks_like_login?: boolean | null
  error?: string
}

export async function jmCheckAuth(): Promise<JMAuthCheck> {
  return getRequest<JMAuthCheck>(`${BROWSER_AGENT_ENDPOINT}/download-jm/check-auth`)
}
export async function jmScan(): Promise<JMScanResult> {
  return postRequest<JMScanResult>(
    `${BROWSER_AGENT_ENDPOINT}/download-jm/scan`, {}, {})
}
export async function jmExecute(urls: string[]): Promise<{ message: string; total: number }> {
  return postRequest<{ message: string; total: number }>(
    `${BROWSER_AGENT_ENDPOINT}/download-jm/execute`, {}, { urls })
}
export async function jmStatus(): Promise<JMStatus> {
  return getRequest<JMStatus>(`${BROWSER_AGENT_ENDPOINT}/download-jm/status`)
}
export async function jmSubmitCaptcha(answer: string): Promise<{ ok?: boolean; error?: string }> {
  return postRequest<{ ok?: boolean; error?: string }>(
    `${BROWSER_AGENT_ENDPOINT}/download-jm/submit-captcha`, {}, { answer })
}

// --- Captcha trainer ------------------------------------------------------
// REMOVED: template-matching training pipeline deleted.
