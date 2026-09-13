export interface Task {
  id: number
  title: string
  description: string
  repo_path: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'stopped'
  created_at: string
  started_at: string | null
  ended_at: string | null
  pid: number | null
}

export interface MemoryShortEntry {
  id: number
  task_id: number
  raw_log: string
  user_score: number | null
  user_note: string | null
  created_at: string
  distilled: boolean
}

export interface HumanMessage {
  id: number
  task_id: number
  direction: 'user_to_cmd' | 'cmd_to_user'
  content: string
  read_by_cmd: boolean
  created_at: string
}

export interface RedLine {
  id: number
  rule: string
  created_at: string
}

export interface ApprenticeSettings {
  commander_model: string
  soldier_model: string
  commander_max_turns: number
  max_cost_usd: number
  github_token: string
  jenkins_url: string
  jenkins_user: string
  jenkins_token: string
  distillation_threshold: number
  distillation_model: string
}

export interface SseEvent {
  event: string
  task_id?: number
  text?: string
  turn_no?: number
  tool_name?: string
  input_preview?: string
  content?: string
  status?: string
  reason?: string
  [key: string]: any
}
