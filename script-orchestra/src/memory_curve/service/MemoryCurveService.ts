import { getRequest, postRequest, putRequest, deleteRequest } from '@/basic/RequestService'
import { MEMORY_CURVE_ENDPOINT } from '@/basic/Constants'
import type { MemoryCard, MemoryCurveSettings, Rating } from './Model'

export async function getCards(): Promise<MemoryCard[]> {
  const res = await getRequest<{ cards: MemoryCard[] }>(`${MEMORY_CURVE_ENDPOINT}/cards`)
  return res.cards
}

export async function getDue(): Promise<MemoryCard[]> {
  const res = await getRequest<{ cards: MemoryCard[] }>(`${MEMORY_CURVE_ENDPOINT}/due`)
  return res.cards
}

export async function createCard(front: string, back = '', deck = ''): Promise<MemoryCard> {
  const res = await postRequest(`${MEMORY_CURVE_ENDPOINT}/cards`, {}, { front, back, deck })
  return (res as { card: MemoryCard }).card
}

export async function updateCard(id: number, patch: Partial<MemoryCard>): Promise<MemoryCard> {
  const res = await putRequest<{ card: MemoryCard }>(`${MEMORY_CURVE_ENDPOINT}/cards/${id}`, {}, patch)
  return res.card
}

export async function deleteCard(id: number) {
  return deleteRequest(`${MEMORY_CURVE_ENDPOINT}/cards/${id}`)
}

export async function reviewCard(id: number, rating: Rating): Promise<MemoryCard> {
  const res = await postRequest(`${MEMORY_CURVE_ENDPOINT}/cards/${id}/review`, {}, { rating })
  return (res as { card: MemoryCard }).card
}

export async function getSettings(): Promise<MemoryCurveSettings> {
  const res = await getRequest<{ settings: MemoryCurveSettings }>(`${MEMORY_CURVE_ENDPOINT}/settings`)
  return res.settings
}

export async function updateSettings(patch: Partial<MemoryCurveSettings>): Promise<MemoryCurveSettings> {
  const res = await putRequest<{ settings: MemoryCurveSettings }>(`${MEMORY_CURVE_ENDPOINT}/settings`, {}, patch)
  return res.settings
}
