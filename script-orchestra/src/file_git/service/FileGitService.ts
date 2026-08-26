/**
 * File-Git Service — HTTP client for the 17 file-git endpoints.
 *
 * The backend (REQUIREMENTS §3.7, §3.13) exposes these operations:
 *
 *   Repo CRUD:        list, add, get, delete, open-folder, status, config
 *   Sync:             push, pull, resume
 *   Manual upload:    manual-upload, post-manual-upload
 *   Manual download:  pre-manual-download, post-manual-download
 *   Read/utility:     diff, rebuild-local-index, rebuild-cloud-index (estimate + run), cleanup (dry + run)
 *   Global settings:  get, put
 */
import axios from 'axios'
import {
  BACKEND_BASE_URL,
  FILE_GIT_ENDPOINT_REPOS,
  FILE_GIT_ENDPOINT_SETTINGS,
} from '@/basic/Constants'

// ---------------------------------------------------------------------
// Common types
// ---------------------------------------------------------------------

export type RepoMode = 'ORIGINAL' | 'ENCRYPTED'
export type RepoStatusValue = 'ready' | 'syncing' | 'error' | 'locked'

export interface Repository {
  id: string
  name: string
  local_path: string
  mode: RepoMode
  created_at: string
  last_updated: string
  initialized: boolean
  status: RepoStatusValue
}

export interface RepoConfig {
  mode: RepoMode
  local_path: string
  remote_path: string
  password_set: boolean            // server never echoes the password
  baidu_cloud?: Record<string, string>
  hook_retention_days?: number
}

export interface QueueStatus {
  lock: boolean
  action_folder: string | null
  action_type: string | null
  pending_count: number             // items in current queue.json
  pending_upload_count: number      // entries in pending_upload.json
}

export interface RepoStatusResponse {
  success: boolean
  repo: Repository
  queue: QueueStatus
  error?: string
}

export interface Envelope<T = {}> {
  success: boolean
  message?: string
  error?: string
  data?: T
}

// ---- diff -----------------------------------------------------------

export interface DiffEntry {
  middle_path: string
  size: number
}

export interface DiffResponse {
  success: boolean
  message?: string
  added: DiffEntry[]
  modified: DiffEntry[]
  deleted: DiffEntry[]
  total_local: number
  total_cloud: number
}

// ---- push / pull / resume -------------------------------------------

export interface SyncCounters {
  uploaded?: number
  downloaded?: number
  local_deleted?: number
  remote_deleted?: number
  errors?: number
}

export interface SyncResponse extends SyncCounters {
  success: boolean
  message?: string
  action_folder?: string | null
  error?: string
}

// ---- manual upload / download ---------------------------------------

export interface ManualUploadResponse {
  success: boolean
  message?: string
  buffer_dir?: string | null
  file_count?: number
  action_folder?: string | null
  error?: string
}

export interface PostManualUploadResponse {
  success: boolean
  message?: string
  confirmed?: number
  missing?: string[]
  action_folder?: string | null
  error?: string
}

export interface PreManualDownloadResponse {
  success: boolean
  message?: string
  buffer_dir?: string | null
  action_folder?: string | null
  error?: string
}

export interface PostManualDownloadResponse {
  success: boolean
  message?: string
  decrypted?: number
  unmapped?: string[]
  action_folder?: string | null
  error?: string
}

// ---- rebuild --------------------------------------------------------

export interface RebuildLocalIndexResponse {
  success: boolean
  message?: string
  count?: number
  error?: string
}

export interface RebuildCloudIndexEstimateResponse {
  success: boolean
  message?: string
  remote_root?: string
  approximate_file_count?: number
  error?: string
}

export interface RebuildCloudIndexResponse {
  success: boolean
  message?: string
  count?: number
  unknown?: string[]
  error?: string
}

// ---- cleanup --------------------------------------------------------

export type CleanupMode = 'expired' | 'all'

export interface CleanupDryRunResponse {
  success: boolean
  message?: string
  trash_candidates?: string[]
  action_candidates?: string[]
  error?: string
}

export interface CleanupResponse {
  success: boolean
  message?: string
  trash_removed?: number
  action_removed?: number
  error?: string
}

// ---- settings -------------------------------------------------------

export interface GlobalSettings {
  baidu_cloud?: Record<string, string>
  use_mock_baidu?: boolean
  default_password?: string
}

export interface SettingsResponse {
  success: boolean
  settings?: GlobalSettings
  message?: string
  error?: string
}

export type SyncFilterKind = 'both' | 'local-only' | 'remote-only'

export interface SyncFilterChild {
  name: string
  path: string          // middle_path relative to remote_path
  is_dir: boolean
  kind: SyncFilterKind
  synced: boolean       // remote has it (backed up)
  checked: boolean      // current sync decision
}

// ---------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------

function repoUrl(repoId: string, suffix: string = ''): string {
  return `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}${suffix}`
}

const jsonHeaders = { headers: { 'Content-Type': 'application/json' } }

export class FileGitService {

  // ---- repo CRUD -----------------------------------------------------

  static async listRepos(): Promise<{ success: boolean; repos: Repository[]; error?: string }> {
    const { data } = await axios.get(BACKEND_BASE_URL + FILE_GIT_ENDPOINT_REPOS)
    return data
  }

  static async addRepo(
    localPath: string,
    mode: RepoMode,
    skipInit: boolean = false,
  ): Promise<{ success: boolean; repo?: Repository; message?: string; error?: string }> {
    const { data } = await axios.post(
      BACKEND_BASE_URL + FILE_GIT_ENDPOINT_REPOS,
      { local_path: localPath, mode, skip_init: skipInit },
      jsonHeaders,
    )
    return data
  }

  static async getRepo(
    repoId: string,
  ): Promise<{ success: boolean; repo?: Repository; error?: string }> {
    const { data } = await axios.get(repoUrl(repoId))
    return data
  }

  static async deleteRepo(
    repoId: string,
  ): Promise<{ success: boolean; message?: string; error?: string }> {
    const { data } = await axios.delete(repoUrl(repoId))
    return data
  }

  static async openFolder(
    repoId: string,
  ): Promise<{ success: boolean; message?: string; error?: string }> {
    const { data } = await axios.post(repoUrl(repoId, '/open-folder'))
    return data
  }

  static async getStatus(repoId: string): Promise<RepoStatusResponse> {
    const { data } = await axios.get(repoUrl(repoId, '/status'))
    return data
  }

  // ---- config --------------------------------------------------------

  static async getConfig(
    repoId: string,
  ): Promise<{ success: boolean; config?: RepoConfig; error?: string }> {
    const { data } = await axios.get(repoUrl(repoId, '/config'))
    return data
  }

  static async updateConfig(
    repoId: string,
    patch: Partial<RepoConfig> & { password?: string },
  ): Promise<{ success: boolean; message?: string; error?: string }> {
    const { data } = await axios.put(repoUrl(repoId, '/config'), patch, jsonHeaders)
    return data
  }

  // ---- push / pull / resume -----------------------------------------

  static async push(repoId: string): Promise<SyncResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/push'))
    return data
  }

  static async pull(repoId: string): Promise<SyncResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/pull'))
    return data
  }

  static async resume(repoId: string): Promise<SyncResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/resume'))
    return data
  }

  // ---- manual upload / download -------------------------------------

  static async manualUpload(
    repoId: string,
    subpath: string = '',
  ): Promise<ManualUploadResponse> {
    const { data } = await axios.post(
      repoUrl(repoId, '/manual-upload'),
      { subpath },
      jsonHeaders,
    )
    return data
  }

  static async postManualUpload(repoId: string): Promise<PostManualUploadResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/post-manual-upload'))
    return data
  }

  static async preManualDownload(repoId: string): Promise<PreManualDownloadResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/pre-manual-download'))
    return data
  }

  static async postManualDownload(repoId: string): Promise<PostManualDownloadResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/post-manual-download'))
    return data
  }

  // ---- diff / rebuild -----------------------------------------------

  static async diff(repoId: string): Promise<DiffResponse> {
    const { data } = await axios.get(repoUrl(repoId, '/diff'))
    return data
  }

  static async rebuildLocalIndex(repoId: string): Promise<RebuildLocalIndexResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/rebuild-local-index'))
    return data
  }

  static async estimateRebuildCloudIndex(
    repoId: string,
  ): Promise<RebuildCloudIndexEstimateResponse> {
    const { data } = await axios.get(repoUrl(repoId, '/rebuild-cloud-index'))
    return data
  }

  static async rebuildCloudIndex(repoId: string): Promise<RebuildCloudIndexResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/rebuild-cloud-index'))
    return data
  }

  // ---- cleanup -------------------------------------------------------

  static async cleanupDryRun(
    repoId: string,
    mode: CleanupMode = 'expired',
  ): Promise<CleanupDryRunResponse> {
    const { data } = await axios.get(repoUrl(repoId, '/cleanup'), { params: { mode } })
    return data
  }

  static async cleanup(
    repoId: string,
    mode: CleanupMode = 'expired',
  ): Promise<CleanupResponse> {
    const { data } = await axios.post(repoUrl(repoId, '/cleanup'), { mode }, jsonHeaders)
    return data
  }

  // ---- global settings ----------------------------------------------

  static async getSettings(): Promise<SettingsResponse> {
    const { data } = await axios.get(BACKEND_BASE_URL + FILE_GIT_ENDPOINT_SETTINGS)
    return data
  }

  static async updateSettings(patch: Partial<GlobalSettings>): Promise<SettingsResponse> {
    const { data } = await axios.put(
      BACKEND_BASE_URL + FILE_GIT_ENDPOINT_SETTINGS,
      patch,
      jsonHeaders,
    )
    return data
  }

  // ---- Baidu OAuth --------------------------------------------------

  static async getBaiduAuthUrl(): Promise<{ success: boolean; url?: string; error?: string }> {
    const { data } = await axios.get(BACKEND_BASE_URL + '/file-git/baidu/auth-url')
    return data
  }

  static async getBaiduStatus(): Promise<{
    success: boolean
    connected?: boolean
    baidu_name?: string
    expires_at?: number
    error?: string
  }> {
    const { data } = await axios.get(BACKEND_BASE_URL + '/file-git/baidu/status')
    return data
  }

  // ---- Sync filter (selective sync) ---------------------------------

  static async getSyncFilter(repoId: string): Promise<{
    success: boolean
    filter?: { checked_prefixes: string[]; unchecked_overrides: string[] }
    children?: SyncFilterChild[]
    error?: string
  }> {
    const { data } = await axios.get(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}/sync-filter`)
    return data
  }

  static async getSyncFilterChildren(repoId: string, path: string): Promise<{
    success: boolean
    children?: SyncFilterChild[]
    error?: string
  }> {
    const { data } = await axios.get(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}/sync-filter/children`,
      { params: { path } })
    return data
  }

  static async updateSyncFilter(
    repoId: string,
    decision: { checked_prefixes: string[]; unchecked_overrides: string[] },
  ): Promise<{ success: boolean; message?: string; error?: string }> {
    const { data } = await axios.put(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}/sync-filter`,
      decision,
      jsonHeaders)
    return data
  }
}
