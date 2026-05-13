/**
 * Roadmap Kanban Models
 */

export enum TaskStatus {
  TODO = 'todo',
  IN_PROGRESS = 'in_progress',
  BLOCK = 'block',
  DONE = 'done'
}

export enum TaskPriority {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high'
}

export interface Task {
  id: string
  content: string
  status: TaskStatus
  priority: TaskPriority
  createdAt: string
  order: number
}

export interface Column {
  id: TaskStatus
  name: string
  tasks: Task[]
}
