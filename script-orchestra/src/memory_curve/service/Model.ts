export type Rating = 'again' | 'hard' | 'good' | 'easy'
export type CardMode = 'qa' | 'single'

export interface MemoryCard {
  id: number
  front: string
  back: string
  deck: string
  created_at: string
  updated_at: string
  interval: number
  ease: number
  reps: number
  due_date: string
  last_reviewed: string | null
  suspended: number
}

export interface MemoryCurveSettings {
  card_mode: CardMode
  daily_new_limit: number
}
