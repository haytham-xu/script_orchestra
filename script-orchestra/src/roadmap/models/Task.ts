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

export enum TaskSize {
  SMALL = 'S',
  MEDIUM = 'M',
  BIG = 'B'
}

export enum TaskCategory {
  A = 'a',
  B = 'b',
  C = 'c',
  D = 'd'
}

export interface Task {
  id: string
  header: string  // Short title for card display
  content: string  // Full content (shown in popup on click)
  status: TaskStatus
  priority: TaskPriority
  size: TaskSize
  eta: string  // ISO date string
  category: TaskCategory
  createdAt: string
  order: number
  inProgressAt?: string  // ISO date string, when task enters In Progress
  returnedFromInProgress?: boolean  // Flag for tasks auto-returned from In Progress
  returnedAt?: string  // ISO date string, when task was returned from In Progress
  doneAt?: string  // ISO date string, when task enters Done
}

export interface Column {
  id: TaskStatus
  name: string
  tasks: Task[]
}
