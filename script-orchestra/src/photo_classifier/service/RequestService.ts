
import axios from 'axios'
import { ElMessage } from 'element-plus'

import {BACKEND_BASE_URL} from '@/photo_classifier/constants/index.ts'

export async function getRequest<T>(uriPath: string, params = {}): Promise<T> {
  const res = await axios.get(BACKEND_BASE_URL + uriPath, { params })
  if (res.status !== 200) {
    ElMessage.error(`Request Failed: ${res.statusText}`)
    throw new Error(`Request Failed: ${res.statusText}`)
  }
  return res.data as T
}

export async function postRequest(uriPath:string, params = {}, payload = {}) {
    const res = await axios.post(BACKEND_BASE_URL + uriPath, payload, { params })
    if (res.status !== 202) {
        ElMessage.error(`Request Failed: ${res.statusText}`)
        throw new Error(`Request Failed: ${res.statusText}`)
    }
    return res.data
}
