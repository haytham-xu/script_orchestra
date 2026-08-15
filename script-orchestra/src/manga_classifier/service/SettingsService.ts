import { getRequest, putRequest } from '@/basic/RequestService'
import { MANGA_CLASSIFIER_ENDPOINT_SETTINGS } from '@/basic/Constants'
import type { MangaClassifierSettings } from '@/manga_classifier/service/Model'

interface SettingsResponse {
  settings: MangaClassifierSettings
}

export async function getSettings(): Promise<MangaClassifierSettings> {
  const response = await getRequest<SettingsResponse>(MANGA_CLASSIFIER_ENDPOINT_SETTINGS)
  return response.settings
}

export async function updateSettings(
  patch: Partial<MangaClassifierSettings>
): Promise<MangaClassifierSettings> {
  const response = await putRequest<SettingsResponse>(
    MANGA_CLASSIFIER_ENDPOINT_SETTINGS,
    {},
    patch
  )
  return response.settings
}
