import { getRequest, postRequest, putRequest, patchRequest, deleteRequest } from '@/basic/RequestService'
import { BROWSER_AGENT_ENDPOINT } from '@/basic/Constants'
import type {
  BrowserTask,
  BrowserAgentSettings,
  TabArchiveArchiveResult,
  TabArchiveHealthCheckJob,
  TabArchiveHealthCheckResult,
  TabArchiveLabel,
  TabArchiveRestoreResult,
  TabArchiveSortBy,
  TabArchiveSortOrder,
  TabArchiveSafePreview,
  TabArchiveSnapshot,
  TabArchiveRecord,
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
  semantic?: boolean
  semantic_top_k?: number
} = {}): Promise<TabArchiveSnapshot> {
  return getRequest<TabArchiveSnapshot>(`${BROWSER_AGENT_ENDPOINT}/tab-archive/snapshot`, params)
}

export async function tabArchiveSafePreview(includePinned = false): Promise<TabArchiveSafePreview> {
  return postRequest<TabArchiveSafePreview>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/archive-safe-preview`, {}, {
      include_pinned: includePinned,
    })
}

export async function tabArchiveSelected(tabIds: number[]): Promise<TabArchiveArchiveResult> {
  return postRequest<TabArchiveArchiveResult>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/archive-selected`, {}, {
      tab_ids: tabIds,
    })
}

export async function tabArchiveSafeRun(includePinned = false): Promise<TabArchiveArchiveResult> {
  return postRequest<TabArchiveArchiveResult>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/archive-safe-run`, {}, {
      include_pinned: includePinned,
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

export async function tabArchiveHealthCheck(payload: {
  record_ids?: number[]
  limit?: number
} = {}): Promise<TabArchiveHealthCheckResult> {
  return postRequest<TabArchiveHealthCheckResult>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/health-check`,
    {},
    payload,
  )
}

export async function tabArchiveHealthCheckStart(payload: {
  record_ids?: number[]
  limit?: number
  batch_size?: number
} = {}): Promise<{ job: TabArchiveHealthCheckJob }> {
  return postRequest<{ job: TabArchiveHealthCheckJob }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/health-check/start`,
    {},
    payload,
  )
}

export async function tabArchiveHealthCheckStatus(jobId?: string): Promise<{
  exists: boolean
  job: TabArchiveHealthCheckJob | null
}> {
  const params = jobId ? { job_id: jobId } : {}
  return getRequest<{ exists: boolean; job: TabArchiveHealthCheckJob | null }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/health-check/status`,
    params,
  )
}

export async function tabArchiveHealthCheckCancel(jobId?: string): Promise<{
  exists: boolean
  job: TabArchiveHealthCheckJob | null
}> {
  return postRequest<{ exists: boolean; job: TabArchiveHealthCheckJob | null }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-archive/health-check/cancel`,
    {},
    jobId ? { job_id: jobId } : {},
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

export interface TrainingSample {
  filename: string
  image_base64: string
  answer_hint: string
  glyph_count: number
}
export interface TrainingList {
  samples: TrainingSample[]
  template_counts: Record<string, number>
}
export async function fetchTrainingList(): Promise<TrainingList> {
  return getRequest<TrainingList>(`${BROWSER_AGENT_ENDPOINT}/captcha-training/list`)
}
export async function saveTrainingLabel(filename: string, expression: string): Promise<{
  saved?: number; glyph_count?: number; expected_glyph_count?: number; error?: string
}> {
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/captcha-training/save`, {},
                     { filename, expression })
}
export async function deleteTrainingSample(filename: string): Promise<{ deleted?: boolean; error?: string }> {
  return postRequest(`${BROWSER_AGENT_ENDPOINT}/captcha-training/delete`, {},
                     { filename })
}
