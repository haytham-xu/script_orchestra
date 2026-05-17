/**
 * Photo Classifier HTTP Service
 *
 * Independent HTTP service for photo classifier module.
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { BACKEND_BASE_URL } from '../config/constants'

export async function getRequest<T>(uriPath: string, params = {}): Promise<T> {
  const res = await axios.get(BACKEND_BASE_URL + uriPath, { params })
  if (res.status !== 200) {
    ElMessage.error(`Request Failed: ${res.statusText}`)
    throw new Error(`Request Failed: ${res.statusText}`)
  }
  return res.data as T
}

export async function postRequest(uriPath: string, params = {}, payload = {}) {
  const res = await axios.post(BACKEND_BASE_URL + uriPath, payload, { params })
  if (![200, 201, 202].includes(res.status)) {
    ElMessage.error(`Request Failed: ${res.statusText}`)
    throw new Error(`Request Failed: ${res.statusText}`)
  }
  return res.data
}

export async function putRequest<T>(uriPath: string, params = {}, payload = {}): Promise<T> {
  const res = await axios.put(BACKEND_BASE_URL + uriPath, payload, { params })
  if (![200, 202, 204].includes(res.status)) {
    ElMessage.error(`Request Failed: ${res.statusText}`)
    throw new Error(`Request Failed: ${res.statusText}`)
  }
  return (res.status === 204 ? ({} as T) : (res.data as T))
}

export async function deleteRequest<T>(uriPath: string, params = {}): Promise<T> {
  const res = await axios.delete(BACKEND_BASE_URL + uriPath, { params })
  if (![200, 202, 204].includes(res.status)) {
    ElMessage.error(`Request Failed: ${res.statusText}`)
    throw new Error(`Request Failed: ${res.statusText}`)
  }
  return (res.status === 204 ? ({} as T) : (res.data as T))
}
