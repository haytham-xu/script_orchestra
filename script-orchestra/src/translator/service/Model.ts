// Translator — TypeScript models. Mirrors backend entity/controller shapes.

export interface Usage {
  model: string           // the model actually used (auto resolves to a real id)
  credits: number         // AI credits consumed (nano-AIU / 1e9)
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
}

export interface LearningPoint {
  id: number
  history_id: number
  original: string      // what the user wrote (awkward / non-idiomatic / typo)
  suggestion: string    // a more idiomatic way to say it
  explanation: string   // short why / what rule
  created_at: string
}

export interface TranslationHistory {
  id: number
  scene: 'zh2en' | 'en2zh'
  source_text: string
  result_text: string          // zh2en=english / en2zh=chinese
  back_translation: string     // zh2en only
  model: string
  created_at: string
  usage: Usage | Record<string, never>   // {} for old rows before usage tracking
  learning_points: LearningPoint[]
}

export interface Zh2EnResult {
  english: string
  back_translation: string
  learning_points: LearningPoint[]
  usage: Usage
  history_id: number
}

export interface En2ZhResult {
  chinese: string
  usage: Usage
  history_id: number
}

export interface SceneUsage {
  count: number
  total_credits: number
  total_input_tokens: number
  total_output_tokens: number
}

export interface UsageSummary extends SceneUsage {
  by_scene: {
    zh2en: SceneUsage
    en2zh: SceneUsage
  }
}

export interface SceneConfig {
  system_prompt: string
  model: string
  learning_prompt?: string   // zh2en only: user preference for learning-point extraction
}

export interface TranslatorSettings {
  zh2en: SceneConfig
  en2zh: SceneConfig
  cleanup_days: number
}

export interface ModelInfo {
  id: string
  name: string
}
