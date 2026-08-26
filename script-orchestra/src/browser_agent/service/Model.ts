export enum BrowserTaskStatus {
  Todo = 'TODO',
  InProgress = 'IN_PROGRESS',
  Failed = 'FAILED',
  Completed = 'COMPLETED',
}

export interface BrowserTask {
  id: number
  code: string
  created_at: string
  updated_at: string
  status: BrowserTaskStatus
  retry_times: number
  file_name: string
  size: number
  download_link: string
}

export interface SiteRule {
  coverDomains: string[]
  overviewUriFormat: string
  downloadUriFormat: string
  downloadLinkRegex: string
}

export interface BrowserAgentSettings {
  downloadDir: string
  maxRetries: number
  pollIntervalSec: number
  siteRules: SiteRule[]
}

// Live progress event pushed over WebSocket.
export interface ProgressEvent {
  taskId: number
  status: BrowserTaskStatus
  progress: number
  retryTimes?: number
}
