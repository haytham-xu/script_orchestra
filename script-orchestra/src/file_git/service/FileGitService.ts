/**
 * File-Git Service - API calls for repository management
 */
import axios from 'axios'
import { BACKEND_BASE_URL, FILE_GIT_ENDPOINT_REPOS, FILE_GIT_ENDPOINT_SETTINGS } from '@/basic/Constants'

export interface Repository {
  id: string
  name: string
  local_path: string
  mode: 'ORIGINAL' | 'ENCRYPTED'
  created_at: string
  last_updated: string
  initialized: boolean
  status: 'ready' | 'syncing' | 'error'
}

export interface ReposListResponse {
  success: boolean
  repos: Repository[]
  error?: string
}

export interface RepoResponse {
  success: boolean
  repo?: Repository
  message?: string
  error?: string
}

export interface FileChange {
  middle_path: string
  size: number
  mtime: number
  old_size?: number
  old_mtime?: number
}

export interface RepoStatus {
  added: FileChange[]
  modified: FileChange[]
  deleted: FileChange[]
  total_files: number
}

export interface RepoStatusResponse {
  success: boolean
  status?: RepoStatus
  error?: string
}

export interface BaiduCloudCredentials {
  app_id: string
  secret_key: string
  app_key: string
  sign_code: string
  expires_in: string
  refresh_token: string
  access_token: string
}

export interface Settings {
  baidu_cloud: BaiduCloudCredentials
  use_mock_baidu: boolean
  default_password: string
}

export interface SettingsResponse {
  success: boolean
  settings?: Settings
  message?: string
  error?: string
}

export interface PushResponse {
  success: boolean
  uploaded: number
  deleted: number
  errors?: Array<{ file: string; operation: string; error: string }>
  message?: string
  error?: string
}

export interface PullResponse {
  success: boolean
  downloaded: number
  message?: string
  error?: string
}

export class FileGitService {
  /**
   * List all repositories
   */
  static async listRepos(): Promise<ReposListResponse> {
    const response = await axios.get<ReposListResponse>(
      BACKEND_BASE_URL + FILE_GIT_ENDPOINT_REPOS
    )
    return response.data
  }

  /**
   * Add new repository
   */
  static async addRepo(
    localPath: string,
    mode: 'ORIGINAL' | 'ENCRYPTED',
    skipInit: boolean = false
  ): Promise<RepoResponse> {
    const response = await axios.post<RepoResponse>(
      BACKEND_BASE_URL + FILE_GIT_ENDPOINT_REPOS,
      { local_path: localPath, mode, skip_init: skipInit },
      {
        headers: {
          'Content-Type': 'application/json'
        }
      }
    )
    return response.data
  }

  /**
   * Get repository by ID
   */
  static async getRepo(repoId: string): Promise<RepoResponse> {
    const response = await axios.get<RepoResponse>(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}`
    )
    return response.data
  }

  /**
   * Delete repository
   */
  static async deleteRepo(repoId: string): Promise<RepoResponse> {
    const response = await axios.delete<RepoResponse>(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}`
    )
    return response.data
  }

  /**
   * Open repository folder in system file manager
   */
  static async openFolder(repoId: string): Promise<RepoResponse> {
    const response = await axios.post<RepoResponse>(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}/open-folder`
    )
    return response.data
  }

  /**
   * Get repository file status (changes)
   */
  static async getRepoStatus(repoId: string): Promise<RepoStatusResponse> {
    const response = await axios.get<RepoStatusResponse>(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}/status`
    )
    return response.data
  }

  /**
   * Get global settings
   */
  static async getSettings(): Promise<SettingsResponse> {
    const response = await axios.get<SettingsResponse>(
      BACKEND_BASE_URL + FILE_GIT_ENDPOINT_SETTINGS
    )
    return response.data
  }

  /**
   * Update global settings
   */
  static async updateSettings(settings: Partial<Settings>): Promise<SettingsResponse> {
    const response = await axios.put<SettingsResponse>(
      BACKEND_BASE_URL + FILE_GIT_ENDPOINT_SETTINGS,
      settings,
      {
        headers: {
          'Content-Type': 'application/json'
        }
      }
    )
    return response.data
  }

  /**
   * Push changes to cloud
   */
  static async pushRepo(repoId: string): Promise<PushResponse> {
    const response = await axios.post<PushResponse>(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}/push`
    )
    return response.data
  }

  /**
   * Pull changes from cloud
   */
  static async pullRepo(repoId: string): Promise<PullResponse> {
    const response = await axios.post<PullResponse>(
      `${BACKEND_BASE_URL}${FILE_GIT_ENDPOINT_REPOS}/${repoId}/pull`
    )
    return response.data
  }
}
