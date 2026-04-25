/**
 * Unzip Service - API calls for archive extraction
 */
import axios from 'axios'
import { BACKEND_BASE_URL, UNZIP_ENDPOINT_EXTRACT } from '@/basic/Constants'

export interface UnzipSummaryResponse {
  success: number
  failed: number
  message: string
}

export class UnzipService {
  /**
   * Extract archive(s) from a file or folder path
   */
  static async extractFromPath(path: string): Promise<UnzipSummaryResponse> {
    const response = await axios.post<UnzipSummaryResponse>(
      BACKEND_BASE_URL + UNZIP_ENDPOINT_EXTRACT,
      { path },
      {
        headers: {
          'Content-Type': 'application/json'
        }
      }
    )

    return response.data
  }
}
