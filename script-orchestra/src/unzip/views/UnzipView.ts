/**
 * Unzip View Component Logic - Simplified Version
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UnzipService } from '../service/UnzipService'

export function useUnzipView() {
  const inputPath = ref('')
  const isProcessing = ref(false)

  /**
   * Extract archive(s) from input path
   */
  async function extract() {
    const path = inputPath.value.trim()

    if (!path) {
      ElMessage.warning('Please enter a file or folder path')
      return
    }

    console.log('[Unzip] Starting extraction for:', path)
    isProcessing.value = true

    try {
      const response = await UnzipService.extractFromPath(path)
      console.log('[Unzip] Response:', response)

      // Show result message
      if (response.failed === 0 && response.success > 0) {
        ElMessage.success(response.message)
      } else if (response.success === 0 && response.failed > 0) {
        ElMessage.error(response.message)
      } else if (response.success > 0 && response.failed > 0) {
        ElMessage.warning(response.message)
      } else {
        ElMessage.info(response.message)
      }

      // Clear input after successful extraction
      if (response.success > 0) {
        inputPath.value = ''
      }
    } catch (error: any) {
      console.error('[Unzip] Extraction failed:', error)
      ElMessage.error(error.response?.data?.error || 'Extraction failed')
    } finally {
      isProcessing.value = false
    }
  }

  return {
    inputPath,
    isProcessing,
    extract
  }
}
