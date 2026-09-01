import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { BROWSER_AGENT_ENDPOINT } from '@/basic/Constants'
import type { BrowserTask, BrowserAgentSettings } from './Model'

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

export async function closeTabs(tabIds: number[]): Promise<{ closed: number }> {
  return postRequest<{ closed: number }>(
    `${BROWSER_AGENT_ENDPOINT}/tab-dedup/close-tabs`, {}, { tab_ids: tabIds })
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
