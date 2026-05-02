import { getRequest, putRequest } from './http'
import { PHOTO_CLASSIFIER_ENDPOINT_SETTINGS } from '../config/constants'

interface Settings {
  rootPath: string
}

interface SettingsResponse {
  settings: Settings
}

export async function getSettings(): Promise<Settings> {
  const response = await getRequest<SettingsResponse>(PHOTO_CLASSIFIER_ENDPOINT_SETTINGS)
  return response.settings
}

export async function updateSettings(settings: Partial<Settings>): Promise<Settings> {
  const response = await putRequest<SettingsResponse>(
    PHOTO_CLASSIFIER_ENDPOINT_SETTINGS,
    {},
    settings
  )
  return response.settings
}
