import { getRequest, postRequest, putRequest, deleteRequest } from '../../basic/RequestService'
import { K8S_CONSOLE_ENDPOINT } from '../../basic/Constants'
import type { K8sInstance, AzStatus, TerminalProvision, CreateInstancePayload } from './Model'

const BASE = K8S_CONSOLE_ENDPOINT

export async function listInstances(): Promise<K8sInstance[]> {
  const r = await getRequest(`${BASE}/instances`)
  return r.instances
}

export async function createInstance(payload: CreateInstancePayload): Promise<K8sInstance> {
  return postRequest(`${BASE}/instances`, {}, payload)
}

export async function updateInstance(id: string, payload: Partial<K8sInstance>): Promise<K8sInstance> {
  return putRequest(`${BASE}/instances/${id}`, {}, payload)
}

export async function deleteInstance(id: string): Promise<void> {
  await deleteRequest(`${BASE}/instances/${id}`)
}

export async function uploadKubeconfig(id: string, kubeconfig: string): Promise<void> {
  await putRequest(`${BASE}/instances/${id}/kubeconfig`, {}, { kubeconfig })
}

export async function removeKubeconfig(id: string): Promise<void> {
  await deleteRequest(`${BASE}/instances/${id}/kubeconfig`)
}

export async function provisionTerminal(id: string): Promise<TerminalProvision> {
  return postRequest(`${BASE}/instances/${id}/terminal`, {}, {})
}

export async function getAzStatus(): Promise<AzStatus> {
  return getRequest(`${BASE}/status/az`)
}

export async function getPublicIp(): Promise<{ ip: string | null }> {
  return getRequest(`${BASE}/status/ip`)
}
