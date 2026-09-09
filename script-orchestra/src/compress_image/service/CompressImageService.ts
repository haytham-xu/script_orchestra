import { postRequest } from '@/basic/RequestService'
import { COMPRESS_IMAGE_ENDPOINT } from '@/basic/Constants'

const BASE = COMPRESS_IMAGE_ENDPOINT

export interface PreviewItem {
  path: string
  name: string
  size_kb: number
  needs_compress: boolean
}

export interface PreviewResult {
  total: number
  eligible: number
  total_size_kb: number
  items: PreviewItem[]
}

export interface ApplyItem {
  name: string
  before_kb: number
  after_kb: number | null
  skipped: boolean
  error: string | null
}

export interface ApplyResult {
  total: number
  compressed: number
  skipped: number
  errors: number
  total_saved_kb: number
  results: ApplyItem[]
}

export async function previewCompress(root_path: string, target_kb: number): Promise<PreviewResult> {
  return await postRequest(`${BASE}/preview`, {}, { root_path, target_kb }) as any
}

export async function applyCompress(params: {
  root_path: string
  target_kb: number
  overwrite: boolean
  output_dir: string
}): Promise<ApplyResult> {
  return await postRequest(`${BASE}/apply`, {}, params) as any
}
